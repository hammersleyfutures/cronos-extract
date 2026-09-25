# ABOUTME: Tests for the cronos-extract command as a whole: dispatch, usage errors, exit statuses and stream handling.
# ABOUTME: They run the real command in a subprocess.
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from cli import run_command
from cronos_builder import TEST_DB, TEST_TABLE_FIELD_COUNT, TEST_TABLE_ID, bank_record, write_database


@pytest.mark.parametrize("args", [[], ["inspect"], ["crack"]], ids=["no-subcommand", "inspect", "crack"])
def test_a_missing_subcommand_is_a_usage_error(args: list[str]) -> None:
    result = run_command("cli", args)

    assert result.returncode == 2
    assert "usage: cronos-extract" in result.stderr
    assert "Traceback" not in result.stderr


def test_survey_usage_errors_name_the_survey_subcommand() -> None:
    result = run_command("cli", ["survey"])

    assert result.returncode == 2
    assert result.stderr.startswith("usage: cronos-extract survey")


def test_a_closed_stdout_exits_1_without_a_message() -> None:
    process = subprocess.Popen(
        [sys.executable, "-m", "cronos_extract.cli", "inspect", "kodump", str(TEST_DB / "CroStru.dat")],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None and process.stderr is not None
    process.stdout.readline()
    process.stdout.close()
    stderr = process.stderr.read()
    process.stderr.close()

    assert process.wait(timeout=60) == 1
    assert stderr == b""


def test_an_interrupted_export_says_where_its_output_is(tmp_path: Path) -> None:
    fields = [b"x" * 40] + [b""] * (TEST_TABLE_FIELD_COUNT - 1)
    dbdir = write_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, fields)] * 50_000)
    output = tmp_path / "out.jsonl"
    process = subprocess.Popen(
        [sys.executable, "-m", "cronos_extract.cli", "export", "--jsonl", "-o", str(output), dbdir],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    deadline = time.monotonic() + 60
    while not output.exists() and time.monotonic() < deadline and process.poll() is None:
        time.sleep(0.01)
    process.send_signal(signal.SIGINT)
    _, stderr = process.communicate(timeout=60)

    assert process.returncode == 130
    assert "Traceback" not in stderr
    assert stderr.splitlines()[-1] == f"Error: interrupted; the output written so far is in {output}"


def test_a_path_that_is_not_utf8_is_escaped_in_the_error(tmp_path: Path) -> None:
    dbdir = tmp_path / os.fsdecode(b"db\xff")
    dbdir.mkdir()

    result = run_command("cli", ["export", "--jsonl", str(dbdir)])

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert result.stderr.splitlines()[-1].startswith("Error: ")
    assert "db\\xff" in result.stderr.splitlines()[-1]


def test_export_writes_utf8_whatever_the_locale(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "cronos_extract.cli", "export", "--postgres", str(TEST_DB)],
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONIOENCODING": "latin-1"},
    )

    assert result.returncode == 0
    assert '"Системный номер" TEXT' in result.stdout.decode("utf-8")
