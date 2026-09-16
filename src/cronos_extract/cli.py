# ABOUTME: The cronos-extract command: an argparse parser whose subcommands read CronosPro databases.
# ABOUTME: Its survey subcommand reports the format version of every database under the directories given.
import argparse
import io
import sys
from pathlib import Path

from . import survey


def build_parser() -> argparse.ArgumentParser:
    """Return the cronos-extract argument parser."""
    parser = argparse.ArgumentParser(prog="cronos-extract", description="Read CronosPro databases.")
    subcommands = parser.add_subparsers(dest="subcommand", required=True)
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
        for directory in listed:
            if directory.is_dir():
                roots.append(directory)
            else:
                print(f"warning: {directory} is not a directory; skipping it", file=sys.stderr)
    if not roots:
        parser.error("give at least one directory, or --list with a file naming them")
    return roots


def run_survey(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Survey every directory given, printing the format the options ask for."""
    problems: list[OSError] = []
    databases = survey.survey_roots(collect_roots(args, parser), problems)
    for problem in problems:
        print(f"warning: {problem.filename} cannot be listed: {problem.strerror}; skipping it", file=sys.stderr)
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
    parser = build_parser()
    args = parser.parse_args(argv)
    return run_survey(args, parser)


if __name__ == "__main__":
    sys.exit(main())
