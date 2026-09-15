# ABOUTME: Tests for crodump subcommands run against crafted databases.
# ABOUTME: They run the real command as a subprocess and check its exit status, stdout and stderr.
import subprocess
import sys
from pathlib import Path

from cronos_builder import write_database


def run_crodump(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "cronos_extract.crodump", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_strudump_stops_with_a_clear_message_without_crostru(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [])
    (Path(dbdir) / "CroStru.dat").unlink()
    (Path(dbdir) / "CroStru.tad").unlink()

    result = run_crodump(["strudump", dbdir])

    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert "CroStru.dat" in result.stderr
    assert dbdir in result.stderr
