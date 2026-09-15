# ABOUTME: Tests for cronos_extract.Database: opening and closing the files of a database directory.
# ABOUTME: Uses the sample database in test_data and small hand-written files.
from pathlib import Path

import pytest
from cronos_builder import TEST_DB

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
