# ABOUTME: The export subcommand: opens a database through the cronos_extract API and walks its tables once.
# ABOUTME: It checks and creates the -o target, skips a repeated table, routes diagnostics and prints the summary.
import argparse
import csv
import io
import os
from collections.abc import Callable
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from typing import NoReturn, Protocol, cast

from .._api.bank import Bank, Table
from .._api.bank import open as open_bank
from .._api.diagnostics import Diagnostic
from .._api.errors import CronosError
from .._api.values import Record
from .csv_out import CsvWriter
from .options import Subcommands, kod_options, selected_kod
from .report import DUPLICATE_TABLE, Failure, Problem, Report, error_message

STRU_FILE = "CroStru.dat"
# The exit status of a command stopped by Ctrl-C, as a shell reports it: 128 plus SIGINT's number.
INTERRUPTED_STATUS = 130


class Writer(Protocol):
    """
    An output format. The export calls table() before each table's records, record() for each record, diagnostic()
    for each problem, finish() once every table is written, and close() at the end, finished or not.
    """

    def table(self, table: Table) -> None: ...

    def record(self, table: Table, record: Record) -> None: ...

    def diagnostic(self, problem: Problem) -> None: ...

    def finish(self) -> None: ...

    def close(self) -> None: ...


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
    """Parse a --delimiter value: one character that the csv module accepts as a delimiter."""
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


def run_export(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Export the database in args.dbdir in the format the options choose, returning the exit status."""
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
            writer, created = make_writer(args, parser, bank, target, problems)
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
    args: argparse.Namespace, parser: argparse.ArgumentParser, bank: Bank, target: Path | None, problems: Problems
) -> tuple[Writer, Path]:
    """Create the output of the chosen format, returning its writer and the path created."""
    assert target is not None, "--csv always has a target"
    create_directory(target, parser)
    writer = CsvWriter(target, bank, problems.problem, delimiter=args.delimiter or ",", files=not args.no_files)
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
        writer.table(table)
        for record in table.records():
            writer.record(table, record)
