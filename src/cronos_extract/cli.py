# ABOUTME: The cronos-extract command: the parser for survey, export, inspect and crack, and running one of them.
# ABOUTME: main() is the one place that turns an exception into an Error line and an exit status.
import argparse
import io
import os
import sys
from pathlib import Path

from . import survey
from ._api.errors import CronosError
from ._cli import crack, export, inspect
from ._cli.crack import CrackInputError
from ._cli.options import Subcommands
from ._cli.report import EscapingStream, Failure, error_message, print_error


def add_survey_parser(subcommands: Subcommands) -> None:
    """Add the survey subcommand to `subcommands`."""
    survey_parser = subcommands.add_parser("survey", help="report the CronosPro version of every database found")
    output = survey_parser.add_mutually_exclusive_group()
    output.add_argument(
        "--counts",
        action="store_true",
        help="print only a count of the files of each version and generation, and of those that could not be read, "
        "naming no directories",
    )
    output.add_argument("--jsonl", action="store_true", help="print one JSON object per database")
    survey_parser.add_argument(
        "--list",
        dest="list_file",
        type=Path,
        help="a text file naming directories to survey, one per line; blank lines and lines starting with # are "
        "ignored, and relative paths are taken from the current directory",
    )
    survey_parser.add_argument("directories", nargs="*", type=Path, help="directories to search")
    survey_parser.set_defaults(handler=run_survey, command_parser=survey_parser)


def build_parser() -> argparse.ArgumentParser:
    """Return the cronos-extract argument parser."""
    parser = argparse.ArgumentParser(prog="cronos-extract", description="Read CronosPro databases.")
    subcommands = parser.add_subparsers(dest="subcommand", required=True)
    add_survey_parser(subcommands)
    export.add_parser(subcommands)
    inspect.add_parser(subcommands)
    crack.add_parser(subcommands)
    return parser


def collect_roots(args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[Path]:
    """
    Return the directories to survey, from the arguments and from any --list file, in the order given.

    An argument that is not a directory is a usage error. A line of the list file that is not a directory is
    reported on stderr and skipped: the file is data, which may name a database that has since moved.
    """
    roots: list[Path] = []
    for directory in args.directories:
        if not directory.is_dir():
            parser.error(f"{directory} is not a directory")
        roots.append(directory)
    if args.list_file is not None:
        try:
            listed = survey.read_path_list(args.list_file)
        except OSError as e:
            parser.error(f"cannot read {args.list_file}: {e}")
        else:
            for directory in listed:
                if directory.is_dir():
                    roots.append(directory)
                else:
                    print(f"warning: {directory} is not a directory; skipping it", file=sys.stderr)
    if not roots:
        parser.error("give at least one directory, or --list with a file naming them")
    return roots


def warn_unlistable(problem: OSError) -> None:
    """Report on stderr a directory the survey cannot list."""
    print(f"warning: {problem.filename} cannot be listed: {problem.strerror}; skipping it", file=sys.stderr)


def run_survey(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Survey every directory given, printing the format the options ask for."""
    databases = survey.survey_roots(collect_roots(args, parser), warn_unlistable)
    if args.counts:
        lines = survey.format_counts(databases)
    elif args.jsonl:
        lines = survey.format_jsonl(databases)
    else:
        lines = survey.format_text(databases)
    for line in lines:
        print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the cronos-extract command, returning its exit status."""
    for stream in (sys.stdout, sys.stderr):
        # A path that is not valid UTF-8 reaches here surrogate-escaped, which printing cannot encode. Showing
        # it as escapes keeps the name visible and lets the rest of the survey finish.
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="backslashreplace")
    stderr = sys.stderr
    # Everything written to stderr is escaped, by the internal readers too, so that a database's names cannot reach
    # the terminal as control sequences.
    sys.stderr = EscapingStream(stderr)
    try:
        return run(argv)
    finally:
        sys.stderr = stderr


def run(argv: list[str] | None) -> int:
    """Parse `argv` and run the subcommand, turning the exception it ends with into an Error line and a status."""
    args = build_parser().parse_args(argv)
    try:
        status = int(args.handler(args, args.command_parser))
        # Flushing here lets a closed stdout show up as BrokenPipeError instead of at exit.
        sys.stdout.flush()
    except BrokenPipeError:
        # Whoever read stdout has gone. Pointing stdout at the null device stops the flush at exit failing again.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        os.close(devnull)
        return 1
    except Failure as e:
        print_error(str(e))
        return e.status
    except CrackInputError as e:
        print_error(str(e))
        return 2
    except (CronosError, OSError) as e:
        print_error(error_message(e))
        return 1
    except KeyboardInterrupt:
        return 130
    return status


if __name__ == "__main__":
    sys.exit(main())
