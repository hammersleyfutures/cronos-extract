# ABOUTME: The export subcommand: opens a database through the cronos_extract API and walks its tables once.
# ABOUTME: It checks and creates the -o target, skips a repeated table, routes diagnostics and prints the summary.
import argparse
import csv
import io
import os
import sys
from collections.abc import Callable
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from typing import NoReturn, Protocol, TextIO, cast

from .._api.bank import Bank, Table
from .._api.bank import open as open_bank
from .._api.diagnostics import Diagnostic
from .._api.errors import CronosError
from .._api.values import Record
from .csv_out import CsvWriter
from .jsonl_out import JsonlWriter
from .options import Subcommands, kod_options, selected_kod
from .report import DUPLICATE_TABLE, STRU_FILE, Failure, Problem, Report, error_message
from .sql_out import SqlWriter

# The exit status of a command stopped by Ctrl-C, as a shell reports it: 128 plus SIGINT's number.
INTERRUPTED_STATUS = 130


class Writer(Protocol):
    """
    An output format. The export calls table() before each table's records, record() for each record, diagnostic()
    for each problem, finish() once every table is written, and close() at the end, finished or not.
    """

    def table(self, table: Table) -> bool:
        """Whether the writer accepted the table; the export reads its records only when it did."""

    def record(self, table: Table, record: Record) -> None:
        """Write one record of a table the writer accepted."""

    def diagnostic(self, problem: Problem) -> None:
        """Write one diagnostic found while exporting."""

    def finish(self) -> None:
        """Finish the output once every table is written."""

    def close(self) -> None:
        """Release the writer's resources, at the end whether the export finished or not."""


class Problems:
    """
    Routes each problem to the report, and to the writer once there is one.

    The writer is made after the database is open, so the problems found while opening it wait, and the writer is
    given them first.
    """

    def __init__(self, report: Report) -> None:
        self._report = report
        self._writer: Writer | None = None
        self._waiting: list[Problem] = []

    def problem(self, problem: Problem) -> None:
        self._report.problem(problem)
        if self._writer is None:
            self._waiting.append(problem)
        else:
            self._writer.diagnostic(problem)

    def diagnostic(self, diagnostic: Diagnostic) -> None:
        """Route an API diagnostic; this is what the export passes to cronos_extract.open as on_diagnostic."""
        self.problem(Problem.from_diagnostic(diagnostic))

    def start(self, writer: Writer) -> None:
        """Give `writer` the problems found so far, and each later one as it is found."""
        self._writer = writer
        for problem in self._waiting:
            writer.diagnostic(problem)
        self._waiting.clear()


def delimiter_argument(text: str) -> str:
    """
    Parse a --delimiter value: one character that the csv module accepts as a delimiter.

    csv.writer on Python 3.12 accepts '"', '\\r' and '\\n' as delimiters, which 3.13 rejects; checking them here
    rejects the same values on every supported Python.
    """
    if text in ('"', "\r", "\n"):
        reason = "it is the quote character or a line break"
        raise argparse.ArgumentTypeError(f"{text!r} cannot be a CSV delimiter: {reason}")
    try:
        csv.writer(io.StringIO(), delimiter=text)
    except (TypeError, ValueError) as e:
        raise argparse.ArgumentTypeError(f"{text!r} cannot be a CSV delimiter: {e}") from e
    return text


def add_parser(subcommands: Subcommands) -> None:
    """Add the export subcommand to `subcommands`."""
    parser = subcommands.add_parser(
        "export",
        parents=[kod_options()],
        help="export every table of a database",
        description="Export every table of the CronosPro database in DBDIR. Each diagnostic is printed on stderr as "
        "it happens, and a count of them at the end.",
    )
    output_format = parser.add_mutually_exclusive_group(required=True)
    output_format.add_argument(
        "--csv", action="store_true", help="create a directory holding a CSV file per table and the stored files"
    )
    output_format.add_argument(
        "--postgres", action="store_true", help="write PostgreSQL CREATE TABLE and INSERT statements"
    )
    output_format.add_argument(
        "--jsonl", action="store_true", help="write JSON Lines: one object per table, record and diagnostic"
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="the directory or file to create, which must not exist; by default --csv creates "
        "cronos-extract-<date and time> in the current directory, and the other formats write to stdout",
    )
    parser.add_argument("--delimiter", type=delimiter_argument, help="the CSV field delimiter; a comma by default")
    parser.add_argument("--no-files", action="store_true", help="with --csv, do not write the stored files")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit with status 1 when any diagnostic was reported; the output is written all the same",
    )
    parser.add_argument("dbdir", help="the database directory, holding the Cro*.dat and Cro*.tad files")
    parser.set_defaults(handler=run_export, command_parser=parser)


def output_target(args: argparse.Namespace) -> Path | None:
    """The directory or file the export creates, or None when it writes to stdout."""
    if args.output is not None:
        return cast(Path, args.output)
    if args.csv:
        return Path(datetime.now().strftime("cronos-extract-%Y-%m-%d-%H-%M-%S-%f"))
    return None


def exists_error(parser: argparse.ArgumentParser, target: Path) -> NoReturn:
    parser.error(f"{target} already exists; export never overwrites, so name an output that does not exist")


def create_directory(directory: Path, parser: argparse.ArgumentParser) -> None:
    """Create `directory`, as a usage error when something has appeared there since the check."""
    try:
        os.mkdir(directory)
    except FileExistsError:
        exists_error(parser, directory)


def open_stream(target: Path | None, parser: argparse.ArgumentParser, stack: ExitStack) -> TextIO:
    """
    The text stream the export writes to: the new file `target`, or stdout, set to UTF-8, when there is no target.

    Unencodable characters are written as backslash escapes. A file that appeared since the check is a usage error.
    """
    if target is None:
        if isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
        return cast(TextIO, sys.stdout)
    try:
        return stack.enter_context(open(target, "x", encoding="utf-8", errors="backslashreplace", newline="\n"))
    except FileExistsError:
        exists_error(parser, target)


def check_format_options(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """Refuse the options that only --csv reads when another format is chosen, so nobody believes they applied."""
    if args.csv:
        return
    if args.no_files:
        parser.error("--no-files applies only to --csv, the one format that writes the stored files")
    if args.delimiter is not None:
        parser.error("--delimiter applies only to --csv")


def run_export(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Export the database in args.dbdir in the format the options choose, returning the exit status."""
    check_format_options(args, parser)
    target = output_target(args)
    if target is not None and os.path.lexists(target):
        exists_error(parser, target)
    report = Report()
    try:
        export(args, parser, target, Problems(report))
    finally:
        report.print_summary()
    return 1 if args.strict and report.total else 0


def export(args: argparse.Namespace, parser: argparse.ArgumentParser, target: Path | None, problems: Problems) -> None:
    """
    Open the database, create the output and write every table to it.

    Once the output exists, a failure or an interruption is raised as a Failure that says where the output is.
    """
    created: Path | None = None
    try:
        with ExitStack() as stack:
            bank = stack.enter_context(
                open_bank(args.dbdir, kod=selected_kod(args), compact=args.compact, on_diagnostic=problems.diagnostic)
            )
            writer, created = make_writer(args, parser, bank, target, problems, stack)
            stack.callback(writer.close)
            problems.start(writer)
            walk(bank, writer, problems.problem)
            writer.finish()
    except BrokenPipeError:
        raise
    except (CronosError, OSError, KeyboardInterrupt) as e:
        if created is None:
            raise
        if isinstance(e, KeyboardInterrupt):
            raise Failure(f"interrupted; the output written so far is in {created}", INTERRUPTED_STATUS) from e
        raise Failure(f"{error_message(e)}; the output written so far is in {created}") from e


def make_writer(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    bank: Bank,
    target: Path | None,
    problems: Problems,
    stack: ExitStack,
) -> tuple[Writer, Path | None]:
    """Create the output of the chosen format, returning its writer and the path created, None for stdout."""
    if args.csv:
        assert target is not None, "--csv always has a target"
        create_directory(target, parser)
        writer = CsvWriter(target, bank, problems.problem, delimiter=args.delimiter or ",", files=not args.no_files)
        return writer, target
    stream = open_stream(target, parser, stack)
    writer: Writer = SqlWriter(stream, problems.problem) if args.postgres else JsonlWriter(stream)
    return writer, target


def walk(bank: Bank, writer: Writer, on_problem: Callable[[Problem], None]) -> None:
    """Give `writer` each table of `bank` and its records, skipping a table whose name and id repeat an earlier one."""
    written: set[tuple[str, int]] = set()
    for table in bank.tables:
        if (table.name, table.id) in written:
            on_problem(
                Problem(
                    DUPLICATE_TABLE,
                    "a table with this name and table id is defined before it, so it is skipped",
                    file=STRU_FILE,
                    table=table.name,
                )
            )
            continue
        written.add((table.name, table.id))
        if not writer.table(table):
            continue
        for record in table.records():
            writer.record(table, record)
