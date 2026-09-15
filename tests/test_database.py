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


def test_unreadable_datafile_leaves_no_open_files(tmp_path: Path) -> None:
    (tmp_path / "CroStru.dat").write_bytes(b"NotACronosFile" + bytes(20))
    (tmp_path / "CroStru.tad").write_bytes(bytes(8))

    with pytest.raises(Exception, match="not a Crofile"):
        Database(str(tmp_path), False, KODcoding(INITIAL_KOD))
