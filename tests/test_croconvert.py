# ABOUTME: Tests for the croconvert command's HTML, PostgreSQL and CSV exports of crafted and sample databases.
# ABOUTME: They run the real command as a subprocess and check its stdout, stderr and output files.
import subprocess
import sys
from pathlib import Path

from cronos_builder import TEST_DB


def run_croconvert(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "cronos_extract.croconvert", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_table_definition_warnings_go_to_stderr_not_into_the_sql() -> None:
    result = run_croconvert(["-t", "postgres", str(TEST_DB)])

    assert result.returncode == 0, result.stderr
    assert "Warning" not in result.stdout
    assert "Warning: FieldDefinition Section 2 not marked with a 2" in result.stderr


def test_db_definition_errors_go_to_stderr_not_into_the_sql() -> None:
    result = run_croconvert(["--nokod", "-t", "postgres", str(TEST_DB)])

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert "WARN: expected dbinfo to start with 0x03" in result.stderr
    assert "ERROR decoding db definition" in result.stderr
