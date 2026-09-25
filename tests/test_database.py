# ABOUTME: Tests for cronos_extract.Database: opening and closing a database's files and decoding its definition.
# ABOUTME: Uses the sample database in test_data, small hand-written files and databases from tests/cronos_builder.py.
import os
from pathlib import Path

import pytest
from cli import run_command
from cronos_builder import TEST_DB, database_with_extra_definition_key, random_kod, write_database

from cronos_extract.Database import Database
from cronos_extract.koddecoder import INITIAL_KOD, KODcoding


def test_database_closes_its_files_on_exit() -> None:
    with Database(str(TEST_DB), False, KODcoding(INITIAL_KOD)) as db:
        files = [file for datafile in (db.stru, db.index, db.bank) if datafile for file in (datafile.dat, datafile.tad)]
        assert len(files) == 6
        assert not any(file.closed for file in files)

    assert all(file.closed for file in files)


def test_file_without_cronos_magic_is_reported_in_the_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "CroStru.dat").write_bytes(b"NotACronosFile" + bytes(20))
    (tmp_path / "CroStru.tad").write_bytes(bytes(8))

    with pytest.raises(ValueError, match=r"CroStru\.dat is not a Cronos file: unknown magic b'NotACron'"):
        Database(str(tmp_path), False, KODcoding(INITIAL_KOD))

    assert capsys.readouterr().out == ""


def test_unreadable_datafile_leaves_no_open_files(tmp_path: Path) -> None:
    (tmp_path / "CroStru.dat").write_bytes(b"NotACronosFile" + bytes(20))
    (tmp_path / "CroStru.tad").write_bytes(bytes(8))

    with pytest.raises(ValueError, match="is not a Cronos file"):
        Database(str(tmp_path), False, KODcoding(INITIAL_KOD))


def test_enumerate_tables_names_the_missing_crostru_files(tmp_path: Path) -> None:
    (tmp_path / "CroBank.dat").write_bytes(b"")
    with Database(str(tmp_path), False, KODcoding(INITIAL_KOD)) as db, pytest.raises(FileNotFoundError) as error:
        list(db.enumerate_tables())

    assert "CroStru.dat" in str(error.value)
    assert str(tmp_path) in str(error.value)


def test_decode_db_definition_rejects_a_record_number_crostru_does_not_hold(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [], kod=random_kod(seed=1))

    for seed in range(100, 150):
        with Database(dbdir, False, KODcoding(random_kod(seed=seed))) as db:
            assert db.stru is not None
            dbinfo = db.stru.readrec(1)
            assert dbinfo is not None
            with pytest.raises(ValueError):
                db.decode_db_definition(dbinfo[1:])


def test_export_passes_over_a_fifo_named_like_the_index_instead_of_blocking(tmp_path: Path) -> None:
    dbdir = Path(write_database(tmp_path / "db", []))
    os.mkfifo(dbdir / "CroIndex.dat")
    (dbdir / "CroIndex.tad").write_bytes(bytes(8))

    result = run_command("cli", ["export", "--csv", "-o", str(tmp_path / "out"), str(dbdir)], timeout=60)

    assert result.returncode == 0, result.stderr
    assert "warning: unreadable_file: CroIndex.dat" in result.stderr


def test_a_duplicate_definition_key_is_reported_through_the_warn_hook(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    dbdir = database_with_extra_definition_key(tmp_path / "db", "BankName", b"again")
    messages: list[str] = []

    with Database(dbdir, False, KODcoding(INITIAL_KOD), warn=messages.append) as db:
        db.read_db_definition()

    assert messages == ["WARN: duplicate key: BankName"]
    assert capfd.readouterr().err == ""


def test_database_opens_only_the_files_it_is_asked_for(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [], index_records=[])

    with Database(dbdir, False, KODcoding(INITIAL_KOD), files=("Stru", "Bank")) as db:
        assert (db.stru is not None, db.bank is not None, db.index, db.sys) == (True, True, None, None)


def test_a_corrupt_index_header_does_not_stop_a_database_that_does_not_open_the_index(tmp_path: Path) -> None:
    dbdir = Path(write_database(tmp_path / "db", []))
    (dbdir / "CroIndex.dat").write_bytes(b"garbage")
    (dbdir / "CroIndex.tad").write_bytes(bytes(8))

    with Database(str(dbdir), False, KODcoding(INITIAL_KOD), files=("Stru", "Bank")) as db:
        assert "Base001" in db.read_db_definition()


def test_a_database_made_from_open_datafiles_reads_its_definition(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [])
    kod = KODcoding(INITIAL_KOD)
    messages: list[str] = []
    with Database(dbdir, False, kod, files=("Stru", "Bank")) as opened:
        assert opened.stru is not None
        assert opened.bank is not None
        db = Database.from_datafiles(dbdir, False, kod, opened.stru, opened.bank, messages.append)

        assert (db.stru, db.bank, db.index, db.sys) == (opened.stru, opened.bank, None, None)
        assert "Base001" in db.read_db_definition()
