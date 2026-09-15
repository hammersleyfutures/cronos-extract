# ABOUTME: Tests for recovering a database's KOD table with strucrack and dbcrack, directly and through the commands.
# ABOUTME: Uses encrypted databases from tests/cronos_builder.py whose KOD table is known.
import subprocess
import sys
from pathlib import Path

import pytest
from cronos_builder import TEST_TABLE_ID, bank_record, crackable_database, random_kod

from cronos_extract.crodump import crack_kod

KOD = random_kod(seed=7)
PERSON_FIELDS = [b"42", b"Hammersley", b"", b"1240315", b"0930", b"", b"", b"", b"", b"", b""]
CRACK_FLAGS = ["--strucrack", "--dbcrack"]


@pytest.fixture
def encrypted_db(tmp_path: Path) -> str:
    return crackable_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, PERSON_FIELDS)], KOD)


def run_command(module: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", f"cronos_extract.{module}", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


@pytest.mark.parametrize("method", ["strucrack", "dbcrack"])
def test_crack_kod_recovers_the_database_kod(encrypted_db: str, method: str) -> None:
    assert crack_kod(method, encrypted_db, False) == KOD


@pytest.mark.parametrize("flag", CRACK_FLAGS)
def test_croconvert_decodes_with_a_cracked_kod(encrypted_db: str, flag: str) -> None:
    result = run_command("croconvert", [flag, "-t", "postgres", encrypted_db])

    assert result.returncode == 0, result.stderr
    assert "'Hammersley'" in result.stdout


@pytest.mark.parametrize("flag", CRACK_FLAGS)
def test_crodump_decodes_with_a_cracked_kod(encrypted_db: str, flag: str) -> None:
    result = run_command("crodump", [flag, "strudump", encrypted_db])

    assert result.returncode == 0, result.stderr
    assert "'erdgeist'" in result.stdout


def test_crodump_crack_flag_needs_a_database_subcommand() -> None:
    result = run_command("crodump", ["--strucrack", "kodump", "--help"])

    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("flag", CRACK_FLAGS)
def test_dumpdbfields_crack_flags_do_not_crash(encrypted_db: str, flag: str) -> None:
    result = run_command("dumpdbfields", [flag, encrypted_db])

    assert "has no attribute" not in result.stdout
    assert "Traceback" not in result.stderr
