# ABOUTME: Tests for recovering a database's KOD table with strucrack and dbcrack, directly and through the commands.
# ABOUTME: Uses encrypted databases from tests/cronos_builder.py whose KOD table is known.
import subprocess
import sys
from pathlib import Path

import pytest
from cronos_builder import TEST_TABLE_ID, bank_record, crackable_database, random_kod, write_database

from cronos_extract.crodump import build_parser, crack_kod, derive_kod_from_bank_and_index, derive_kod_from_stru
from cronos_extract.Database import Database

KOD = random_kod(seed=7)
PERSON_FIELDS = [b"42", b"Hammersley", b"", b"1240315", b"0930", b"", b"", b"", b"", b"", b""]
CRACK_FLAGS = ["--strucrack", "--dbcrack"]


@pytest.fixture
def encrypted_db(tmp_path: Path) -> str:
    return crackable_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, PERSON_FIELDS)], KOD)


@pytest.fixture
def uncrackable_db(tmp_path: Path) -> str:
    """A database with too few records for either crack method to resolve every KOD entry."""
    return write_database(
        tmp_path / "db", [bank_record(TEST_TABLE_ID, PERSON_FIELDS)], KOD, index_records=[bytes(12)] * 3
    )


def derive_from_stru(dbdir: str, *options: str):
    """Run derive_kod_from_stru on `dbdir` with strucrack's `options`, returning the KOD table or None."""
    args = build_parser().parse_args(["strucrack", *options, dbdir])
    with Database(dbdir, False, None) as db:
        return derive_kod_from_stru(db, args)


def derive_from_bank_and_index(dbdir: str, *options: str):
    """Run derive_kod_from_bank_and_index on `dbdir` with dbcrack's `options`, returning the KOD table or None."""
    args = build_parser().parse_args(["dbcrack", *options, dbdir])
    with Database(dbdir, False, None) as db:
        return derive_kod_from_bank_and_index(db, args)


def fix_switch(entry: int, shift: int, plain: int) -> str:
    """Return a -f value that forces KOD[entry] so that `entry` decodes to `plain` at `shift`."""
    return f"{entry:02x}{shift:02x}{plain:02x}"


def test_strucrack_rejects_a_kod_with_duplicate_values(encrypted_db: str, capsys: pytest.CaptureFixture[str]) -> None:
    # Force KOD[0] to the value of KOD[1], so two entries map to the same value.
    duplicate_fix = fix_switch(0, 0, KOD[1])

    assert derive_from_stru(encrypted_db, "-f", duplicate_fix) is None
    output = capsys.readouterr().out
    assert "Use the following database key" not in output
    assert "entries unsolved" in output


def test_strucrack_returns_none_when_entries_stay_unresolved(uncrackable_db: str) -> None:
    assert derive_from_stru(uncrackable_db) is None


def test_dbcrack_returns_none_when_the_kod_is_not_a_permutation(
    uncrackable_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert derive_from_bank_and_index(uncrackable_db) is None
    assert "entries unsolved" in capsys.readouterr().out


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


def test_strucrack_applies_a_fix_given_as_a_character(encrypted_db: str) -> None:
    # Force KOD[5] to its true value, so that encrypted byte 05 decodes to "A" at this shift.
    shift = (KOD[5] - ord("A")) % 256

    assert derive_from_stru(encrypted_db, "-f", f"05{shift:02x}=A") == KOD


@pytest.mark.parametrize(
    ("fix", "message"),
    [
        ("0000=中", "can't be encoded as CP-1251"),
        ("0000zz", "Non-hexadecimal digit"),
        ("00000", "expected 6 characters"),
    ],
)
def test_strucrack_rejects_an_invalid_fix(encrypted_db: str, fix: str, message: str) -> None:
    result = run_command("crodump", ["strucrack", "-f", fix, encrypted_db])

    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert message in result.stderr


def test_crodump_crack_flag_needs_a_database_subcommand() -> None:
    result = run_command("crodump", ["--strucrack", "kodump", "--help"])

    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("flag", CRACK_FLAGS)
def test_dumpdbfields_crack_flags_do_not_crash(encrypted_db: str, flag: str) -> None:
    result = run_command("dumpdbfields", [flag, encrypted_db])

    assert "has no attribute" not in result.stdout
    assert "Traceback" not in result.stderr
