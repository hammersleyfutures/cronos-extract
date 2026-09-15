# ABOUTME: Runs the cronos_extract commands in a subprocess for tests, using the interpreter running pytest.
# ABOUTME: Shared by every test that runs crodump, croconvert or dumpdbfields.
import subprocess
import sys
from pathlib import Path


def run_command(
    module: str, args: list[str], cwd: Path | None = None, stdin: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run `python -m cronos_extract.<module> <args>`, feeding it `stdin`, and capture its output as UTF-8 text."""
    return subprocess.run(
        [sys.executable, "-m", f"cronos_extract.{module}", *args],
        cwd=cwd,
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
