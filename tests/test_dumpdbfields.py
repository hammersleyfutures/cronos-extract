# ABOUTME: Tests for the dumpdbfields example script: KOD options and the --maxrecs limit.
# ABOUTME: Runs the script as a subprocess against test_data and databases from tests/cronos_builder.py.
from pathlib import Path

from cli import run_command
from cronos_builder import TEST_DB, TEST_TABLE_ID, bank_record, random_kod, write_database

KOD = random_kod(seed=11)
FIELDS_PER_RECORD = 12


def person_record(name: bytes) -> bytes:
    return bank_record(TEST_TABLE_ID, [b"1", name, b"", b"", b"", b"", b"", b"", b"", b"", b""])


def test_kod_option_decodes_an_encrypted_database(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path, [person_record(b"Hammersley")], kod=KOD)

    result = run_command("dumpdbfields", ["--kod", bytes(KOD).hex(), dbdir])

    assert result.returncode == 0, result.stderr
    assert "-- Hammersley" in result.stdout


def test_nokod_option_reads_records_without_kod_decoding() -> None:
    result = run_command("dumpdbfields", ["--nokod", str(TEST_DB)])

    assert result.returncode == 0, result.stderr
    assert "'erdgeist'" not in result.stdout


def test_maxrecs_limits_the_records_printed_per_table(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path, [person_record(b"A"), person_record(b"B"), person_record(b"C")])

    result = run_command("dumpdbfields", ["--maxrecs", "2", dbdir])

    assert result.returncode == 0, result.stderr
    printed_fields = [line for line in result.stdout.splitlines() if line.startswith(">> ")]
    assert len(printed_fields) == 2 * FIELDS_PER_RECORD
