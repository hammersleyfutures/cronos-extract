# ABOUTME: Tests that databases written by tests/cronos_builder.py are read back correctly by cronos_extract.
# ABOUTME: They prove the fixture builder before other tests rely on it to reproduce bugs.
import struct
from pathlib import Path

import pytest
from cronos_builder import (
    TEST_DB,
    TEST_TABLE_FILE_FIELD_INDEX,
    TEST_TABLE_ID,
    bank_record,
    compressed_record,
    database_with_missing_definition,
    file_record,
    file_reference_field,
    key_referencing_a_deleted_record,
    random_kod,
    stru_records_from_test_db,
    write_database,
)

from cronos_extract.Database import KOD_HINT, Database
from cronos_extract.koddecoder import INITIAL_KOD, KODcoding

FIELD_VALUES = [b"42", b"text", "Привет".encode("cp1251"), b"1240315", b"0930", b"", b"seven", b"", b"", b"", b"eleven"]


def person_record(file_field: bytes) -> bytes:
    fields = list(FIELD_VALUES)
    fields[TEST_TABLE_FILE_FIELD_INDEX] = file_field
    return bank_record(TEST_TABLE_ID, fields)


def test_records_round_trip_through_the_reader(tmp_path: Path) -> None:
    dbdir = write_database(
        tmp_path,
        [file_record(b"PDFDATA"), person_record(file_reference_field("отчёт", "pdf", 1)), None],
    )

    with Database(dbdir, False, KODcoding(INITIAL_KOD)) as db:
        (table,) = db.enumerate_tables()
        (record,) = db.enumerate_records(table)
        file_field = record.fields[TEST_TABLE_FILE_FIELD_INDEX + 1]
        stored_file = db.get_record(file_field.filedatarecord)

    assert table.tablename == "erdgeist"
    assert [field.content for field in record.fields] == [
        "2",
        "42",
        "text",
        "Привет",
        "2024-03-15",
        "09:30",
        "отчёт pdf 1",
        "seven",
        "",
        "",
        "",
        "eleven",
    ]
    assert (file_field.filename, file_field.extname, file_field.filedatarecord) == ("отчёт", "pdf", "1")
    assert stored_file == b"PDFDATA"


def test_compressed_record_round_trips_through_the_reader(tmp_path: Path) -> None:
    plain = person_record(b"")
    dbdir = write_database(tmp_path, [compressed_record(plain)])

    with Database(dbdir, False, KODcoding(INITIAL_KOD)) as db:
        (table,) = db.enumerate_tables()
        (record,) = db.enumerate_records(table)

    assert [field.content for field in record.fields][1:3] == ["42", "text"]


def test_key_referencing_a_deleted_record_appends_a_dangling_key(tmp_path: Path) -> None:
    with Database(str(TEST_DB), False, KODcoding(INITIAL_KOD)) as original:
        assert original.stru is not None
        original_dbinfo = original.stru.readrec(1)
    assert original_dbinfo is not None

    dbdir = key_referencing_a_deleted_record(tmp_path, "DanglingKey")

    with Database(dbdir, False, KODcoding(INITIAL_KOD)) as db:
        assert db.stru is not None
        assert db.stru.readrec(1) == original_dbinfo + bytes([11]) + b"DanglingKey" + struct.pack("<L", 5)
        assert db.stru.readrec(5) is None


def test_database_with_missing_definition_deletes_record_1(tmp_path: Path) -> None:
    stru_records = [None, *stru_records_from_test_db()[1:]]
    dbdir = database_with_missing_definition(tmp_path / "db", stru_records)

    with Database(dbdir, False, KODcoding(INITIAL_KOD)) as db:
        assert db.stru is not None
        assert db.stru.readrec(1) is None
        assert db.stru.nrofrecords == len(stru_records)


def test_database_with_missing_definition_holds_no_records(tmp_path: Path) -> None:
    dbdir = database_with_missing_definition(tmp_path / "db", [])

    with Database(dbdir, False, KODcoding(INITIAL_KOD)) as db:
        assert db.stru is not None
        assert db.stru.nrofrecords == 0


def test_encrypted_database_decodes_only_with_its_kod(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    kod = random_kod(seed=1)
    dbdir = write_database(tmp_path, [person_record(b"")], kod=kod)

    with Database(dbdir, False, KODcoding(kod)) as db:
        (table,) = db.enumerate_tables()
    assert table.tablename == "erdgeist"
    capsys.readouterr()

    with Database(dbdir, False, KODcoding(INITIAL_KOD)) as db:
        assert list(db.enumerate_tables()) == []
    assert capsys.readouterr().err.splitlines() == [
        "WARN: expected dbinfo to start with 0x03",
        "ERROR decoding db definition: the database definition is cut off after 0 keys",
        KOD_HINT,
    ]
