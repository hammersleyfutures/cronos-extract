# ABOUTME: Runs the cronos_extract commands for tests: in a subprocess with the interpreter running pytest, or
# ABOUTME: one subcommand's parser and handler in this process, before the command line assembles them all.
import argparse
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from cronos_extract._cli.options import Subcommands


def run_command(
    module: str, args: list[str], cwd: Path | None = None, stdin: str | None = None, timeout: float | None = None
) -> subprocess.CompletedProcess[str]:
    """Run `python -m cronos_extract.<module> <args>`, feeding it `stdin`, and capture its output as UTF-8 text.

    With `timeout`, the command is killed after that many seconds and subprocess.TimeoutExpired is raised, so a
    test of a command that could block cannot hang the suite.
    """
    return subprocess.run(
        [sys.executable, "-m", f"cronos_extract.{module}", *args],
        cwd=cwd,
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=timeout,
    )


def run_in_process(add_parser: Callable[[Subcommands], None], args: list[str]) -> int:
    """
    Parse `args` with a parser holding only the subcommand that `add_parser` adds, and run its handler here.

    Returns the handler's exit status. Exceptions reach the caller as they would reach cli.main, and argparse's usage
    errors raise SystemExit.
    """
    parser = argparse.ArgumentParser(prog="cronos-extract")
    add_parser(parser.add_subparsers(dest="subcommand", required=True))
    parsed = parser.parse_args(args)
    return int(parsed.handler(parsed, parsed.command_parser))
