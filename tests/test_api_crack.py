# ABOUTME: Tests for crack_kod, which recovers a database's KOD table from its encrypted records without printing.
# ABOUTME: Uses encrypted databases from tests/cronos_builder.py with a known KOD, and checks the crack command agrees.
from pathlib import Path
from typing import Any, cast

import pytest
from cli import run_command
from cronos_builder import (
    TEST_TABLE_ID,
    UNUSED_TABLE_ID,
    bank_record,
    corrupt_compressed_record,
    crackable_database,
    random_kod,
    write_database,
)

from cronos_extract import Kod, NotACronosFile, crack_kod
from cronos_extract.koddecoder import KODcoding

KOD = random_kod(seed=7)
PERSON_FIELDS = [b"42", b"Hammersley", b"", b"1240315", b"0930", b"", b"", b"", b"", b"", b""]
METHODS = ["strucrack", "dbcrack"]

pytestmark = pytest.mark.usefixtures("prints_nothing")


@pytest.fixture
def encrypted_db(tmp_path: Path) -> str:
    return crackable_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, PERSON_FIELDS)], KOD)


@pytest.mark.parametrize("method", METHODS)
def test_crack_kod_recovers_the_kod_of_an_encrypted_database(encrypted_db: str, method: str) -> None:
    assert crack_kod(encrypted_db, cast(Any, method)) == Kod.from_table(KOD)


@pytest.mark.parametrize("method", METHODS)
def test_crack_kod_agrees_with_the_crack_command(encrypted_db: str, method: str) -> None:
    options = ["--noninteractive"] if method == "strucrack" else []
    result = run_command("cli", ["crack", method, "--silent", *options, encrypted_db])

    kod = crack_kod(Path(encrypted_db), cast(Any, method))

    assert result.returncode == 0
    assert kod is not None
    assert result.stdout == kod.hex() + "\n"


@pytest.mark.parametrize("method", METHODS)
def test_crack_kod_returns_none_when_too_few_records_resolve_the_kod(tmp_path: Path, method: str) -> None:
    dbdir = write_database(
        tmp_path / "db", [bank_record(TEST_TABLE_ID, PERSON_FIELDS)], KOD, index_records=[bytes(12)] * 3
    )

    assert crack_kod(dbdir, cast(Any, method)) is None


def test_dbcrack_returns_none_without_an_index(encrypted_db: str) -> None:
    for name in ("CroIndex.dat", "CroIndex.tad"):
        (Path(encrypted_db) / name).unlink()

    assert crack_kod(encrypted_db, "dbcrack") is None


def test_strucrack_does_not_need_an_index(encrypted_db: str) -> None:
    for name in ("CroIndex.dat", "CroIndex.tad"):
        (Path(encrypted_db) / name).unlink()

    assert crack_kod(encrypted_db, "strucrack") == Kod.from_table(KOD)


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("missing", ["Stru", "Bank"])
def test_crack_kod_needs_stru_and_bank(encrypted_db: str, method: str, missing: str) -> None:
    for extension in ("dat", "tad"):
        (Path(encrypted_db) / f"Cro{missing}.{extension}").unlink()

    with pytest.raises(NotACronosFile, match=f"Cro{missing}"):
        crack_kod(encrypted_db, cast(Any, method))


def test_crack_kod_refuses_an_unknown_method(encrypted_db: str) -> None:
    with pytest.raises(ValueError, match="unknown crack method 'guess'"):
        crack_kod(encrypted_db, cast(Any, "guess"))


def crackable_database_with_a_record_that_looks_compressed(directory: Path) -> str:
    """A crackable database whose last CroStru record, read without a KOD, looks compressed but is not."""
    zero_byte_records = [bytes([UNUSED_TABLE_ID]) + bytes(11)] * 300
    stru_recno = 4 + 8 + 1
    looks_compressed = KODcoding(KOD).decode(stru_recno, corrupt_compressed_record())
    return write_database(
        directory,
        [bank_record(TEST_TABLE_ID, PERSON_FIELDS), *zero_byte_records],
        KOD,
        extra_stru_records=[*[bytes(256)] * 8, looks_compressed],
        index_records=zero_byte_records,
    )


def test_strucrack_skips_a_record_it_cannot_read(tmp_path: Path) -> None:
    dbdir = crackable_database_with_a_record_that_looks_compressed(tmp_path / "db")

    assert crack_kod(dbdir, "strucrack") == Kod.from_table(KOD)
