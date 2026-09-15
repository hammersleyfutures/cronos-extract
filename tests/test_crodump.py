# ABOUTME: Tests for the crodump command's subcommands and options, run as subprocesses.
# ABOUTME: Uses the sample database in test_data and databases from tests/cronos_builder.py.
from pathlib import Path

from cli import run_command
from cronos_builder import TEST_DB, key_referencing_a_deleted_record, write_database

from cronos_extract.Database import Database
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

    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert 'key "DanglingKey"' in result.stderr
    assert "record 5" in result.stderr
    assert "deleted" in result.stderr
