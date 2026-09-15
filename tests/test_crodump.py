# ABOUTME: Tests for the crodump command's subcommands and options, run as subprocesses.
# ABOUTME: Uses the sample database in test_data and databases from tests/cronos_builder.py.
import re
from pathlib import Path

from cli import run_command
from cronos_builder import (
    TEST_DB,
    TEST_TABLE_FIELD_COUNT,
    TEST_TABLE_ID,
    bank_record,
    corrupt_compressed_record,
    database_with_missing_definition,
    database_with_wrong_kod_record_out_of_range,
    key_referencing_a_deleted_record,
    stru_records_from_test_db,
    write_database,
)

from cronos_extract.Database import KOD_HINT, Database
from cronos_extract.koddecoder import INITIAL_KOD, KODcoding


def test_recdump_stops_at_the_last_record_even_with_debug() -> None:
    result = run_command("crodump", ["--debug", "recdump", str(TEST_DB)])

    assert result.returncode == 0, result.stderr
    assert "unpack" not in result.stdout


def test_destruct_type_1_prints_a_database_definition() -> None:
    with Database(str(TEST_DB), False, KODcoding(INITIAL_KOD)) as db:
        assert db.stru is not None
        definition_record = db.stru.readrec(1)
    assert definition_record is not None

    result = run_command("crodump", ["destruct", "-t", "1"], cwd=TEST_DB, stdin=definition_record[1:].hex())

    assert result.returncode == 0, result.stderr
    assert 'BankName             - "nowa"' in result.stdout


def test_global_nokod_applies_to_kodump() -> None:
    datafile = str(TEST_DB / "CroStru.dat")

    global_flag = run_command("crodump", ["--nokod", "kodump", "-s", "1", "-l", "16", datafile])
    subcommand_flag = run_command("crodump", ["kodump", "--nokod", "-s", "1", "-l", "16", datafile])

    assert global_flag.returncode == 0, global_flag.stderr
    assert global_flag.stdout == subcommand_flag.stdout


def test_strudump_stops_with_a_clear_message_without_crostru(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [])
    (Path(dbdir) / "CroStru.dat").unlink()
    (Path(dbdir) / "CroStru.tad").unlink()

    result = run_command("crodump", ["strudump", dbdir])

    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert "CroStru.dat" in result.stderr
    assert dbdir in result.stderr


def test_strudump_stops_with_a_clear_message_for_a_key_referencing_a_deleted_record(tmp_path: Path) -> None:
    dbdir = key_referencing_a_deleted_record(tmp_path / "db", "DanglingKey")

    result = run_command("crodump", ["strudump", dbdir])

    assert result.returncode == 1
    assert result.stderr.splitlines() == [
        'Error: key "DanglingKey" refers to CroStru record 5, which is deleted',
        KOD_HINT,
    ]


def test_strudump_without_the_database_kod_stops_with_a_message() -> None:
    result = run_command("crodump", ["--nokod", "strudump", str(TEST_DB)])

    assert result.returncode == 1
    assert result.stderr.splitlines() == [
        "WARN: expected dbinfo to start with 0x03",
        "Error: the database definition is cut off after 0 keys",
        KOD_HINT,
    ]


def test_strudump_with_a_wrong_kod_reports_a_record_out_of_range(tmp_path: Path) -> None:
    dbdir, wrong_kod_hex = database_with_wrong_kod_record_out_of_range(tmp_path / "db")

    result = run_command("crodump", ["--kod", wrong_kod_hex, "strudump", dbdir])

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    lines = result.stderr.splitlines()
    assert len(lines) == 2
    assert re.fullmatch(
        r'Error: key ".*" refers to CroStru record \d+, which CroStru does not hold \(4 records\)', lines[0]
    )
    assert lines[1] == KOD_HINT


def test_strudump_stops_with_a_clear_message_for_a_deleted_definition_record(tmp_path: Path) -> None:
    stru_records = [None, *stru_records_from_test_db()[1:]]
    dbdir = database_with_missing_definition(tmp_path / "db", stru_records)

    result = run_command("crodump", ["strudump", dbdir])

    assert result.returncode == 1
    assert result.stderr.splitlines() == [
        "Error: CroStru record 1, which holds the database definition, is deleted",
        KOD_HINT,
    ]


def test_strudump_stops_with_a_clear_message_for_no_definition_record(tmp_path: Path) -> None:
    dbdir = database_with_missing_definition(tmp_path / "db", [])

    result = run_command("crodump", ["strudump", dbdir])

    assert result.returncode == 1
    assert result.stderr.splitlines() == [
        "Error: CroStru holds no records, so it has no database definition",
        KOD_HINT,
    ]


def test_crodump_shows_a_corrupt_compressed_record_and_dumps_the_next(tmp_path: Path) -> None:
    fields = [b""] * TEST_TABLE_FIELD_COUNT
    fields[0] = b"good"
    dbdir = write_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, fields), corrupt_compressed_record()])

    result = run_command("crodump", ["crodump", "--ascdump", dbdir])

    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr
    lines = result.stdout.splitlines()
    bank_header = next(i for i, line in enumerate(lines) if line.startswith("hdr: Bank"))
    bank_lines = lines[bank_header + 1 :]
    first, second = [line for line in bank_lines if line.startswith(("    1:", "    2:"))]
    assert "good" in first
    assert second.endswith(" <corrupt compressed data: Error -3 while decompressing data: invalid block type>")
