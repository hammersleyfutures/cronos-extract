# ABOUTME: Tests that databases written by tests/cronos_builder.py are read back correctly by cronos_extract.
# ABOUTME: They prove the fixture builder before other tests rely on it to reproduce bugs.
from pathlib import Path

import pytest
from cronos_builder import (
    TEST_TABLE_FILE_FIELD_INDEX,
    TEST_TABLE_ID,
    bank_record,
    file_record,
    file_reference_field,
    random_kod,
    write_database,
)

from cronos_extract.Database import Database
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


def test_encrypted_database_decodes_only_with_its_kod(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    kod = random_kod(seed=1)
    dbdir = write_database(tmp_path, [person_record(b"")], kod=kod)

    with Database(dbdir, False, KODcoding(kod)) as db:
        (table,) = db.enumerate_tables()
    assert table.tablename == "erdgeist"

    with Database(dbdir, False, KODcoding(INITIAL_KOD)) as db:
        assert list(db.enumerate_tables()) == []
    assert "ERROR decoding db definition" in capsys.readouterr().out
