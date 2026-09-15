# ABOUTME: Tests for crodump's inspection subcommands (recdump, destruct) run as subprocesses.
# ABOUTME: Uses the sample database in test_data.
from cli import run_command
from cronos_builder import TEST_DB

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
