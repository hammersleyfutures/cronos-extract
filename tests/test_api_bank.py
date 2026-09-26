# ABOUTME: Tests for reading records and files through the cronos_extract API: laziness, diagnostics and closing.
# ABOUTME: Compares the API with Database.enumerate_records on every version tests/cronos_builder.py writes.
import datetime
from pathlib import Path

import pytest
from cronos_builder import (
    DAT_PREFIX_SIZE,
    TEST_TABLE_FILE_FIELD_INDEX,
    TEST_TABLE_ID,
    V3_INLINE_BIT,
    bank_record,
    compressed_record,
    corrupt_compressed_record,
    database_with_extra_definition_key,
    database_without_files_table,
    file_record,
    file_reference_field,
    patched_table_definition,
    random_kod,
    write_database,
    write_raw_datafile,
)

import cronos_extract
from cronos_extract import DiagnosticKind
from cronos_extract._api.diagnostics import DIAGNOSTICS_KEPT
from cronos_extract.Database import Database
from cronos_extract.koddecoder import INITIAL_KOD, KODcoding

KOD = random_kod(seed=11)
FIELDS = [b"42", b"Hammersley", "Привет".encode("cp1251"), b"1240315", b"0930", b"", b"seven", b"", b"", b"", b"x"]


def person(*, date: bytes = b"1240315", file_field: bytes = b"") -> bytes:
    fields = list(FIELDS)
    fields[3] = date
    fields[TEST_TABLE_FILE_FIELD_INDEX] = file_field
    return bank_record(TEST_TABLE_ID, fields)


def counts(bank: cronos_extract.Bank, kind: cronos_extract.DiagnosticKind) -> int:
    return bank.diagnostic_counts.get(kind, 0)


@pytest.fixture
def prints_nothing(capfd: pytest.CaptureFixture[str]):
    yield
    captured = capfd.readouterr()
    assert (captured.out, captured.err) == ("", "")


@pytest.mark.usefixtures("prints_nothing")
def test_records_are_read_in_crobank_order_skipping_other_tables_and_deleted_records(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [person(), file_record(b"file"), None, person(date=b"850000")])

    with cronos_extract.open(dbdir) as bank:
        records = list(bank.tables[0].records())

    assert [record.number for record in records] == [1, 4]
    assert records[0]["Entry #4"].value == datetime.date(2024, 3, 15)
    assert records[1]["Entry #4"].value == "1985-00-00"
    assert records[0]["Entry #2"].text == "Hammersley"


@pytest.mark.usefixtures("prints_nothing")
def test_records_are_read_one_crobank_record_per_step(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [person(), corrupt_compressed_record(), person()])

    with cronos_extract.open(dbdir) as bank:
        records = bank.tables[0].records()
        assert next(records).number == 1
        assert counts(bank, cronos_extract.DiagnosticKind.CORRUPT_RECORD) == 0
        assert next(records).number == 3
        assert counts(bank, cronos_extract.DiagnosticKind.CORRUPT_RECORD) == 1


@pytest.mark.usefixtures("prints_nothing")
def test_records_the_dat_file_does_not_hold_are_corrupt(tmp_path: Path) -> None:
    dbdir = Path(write_database(tmp_path / "db", []))
    data = person()
    inline = V3_INLINE_BIT
    write_raw_datafile(
        dbdir,
        "Bank",
        data,
        [
            (DAT_PREFIX_SIZE, len(data) | inline),
            (DAT_PREFIX_SIZE + 10_000, len(data) | inline),
            (DAT_PREFIX_SIZE, (len(data) + 100) | inline),
            (DAT_PREFIX_SIZE, len(data) | inline),
        ],
    )

    with cronos_extract.open(dbdir) as bank:
        assert [record.number for record in bank.tables[0].records()] == [1, 4]
        corrupt = [d for d in bank.diagnostics if d.kind == cronos_extract.DiagnosticKind.CORRUPT_RECORD]

    assert [(d.file, d.record) for d in corrupt] == [("CroBank.dat", 2), ("CroBank.dat", 3)]
    assert all("past the end" in d.message for d in corrupt)


@pytest.mark.usefixtures("prints_nothing")
def test_a_corrupt_record_is_reported_once_however_many_tables_are_read(tmp_path: Path) -> None:
    dbdir = database_with_extra_definition_key(
        tmp_path / "db",
        "Base002",
        patched_table_definition(tableid=2),
        [person(), corrupt_compressed_record(), bank_record(2, FIELDS)],
    )

    with cronos_extract.open(dbdir) as bank:
        first, second = bank.tables
        assert [record.number for record in first.records()] == [1]
        assert [record.number for record in second.records()] == [3]
        assert [record.number for record in first.records()] == [1]
        corrupt = [d for d in bank.diagnostics if d.kind == cronos_extract.DiagnosticKind.CORRUPT_RECORD]

    (diagnostic,) = corrupt
    assert (diagnostic.file, diagnostic.record, diagnostic.table, diagnostic.field) == ("CroBank.dat", 2, None, None)
    assert "CroBank record 2 is corrupt" in diagnostic.message


@pytest.mark.usefixtures("prints_nothing")
def test_record_diagnostics_are_recorded_each_time_a_record_is_decoded(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [person(date=b"851301")])

    with cronos_extract.open(dbdir) as bank:
        (record,) = bank.tables[0].records()
        list(bank.tables[0].records())

        assert [d.kind for d in record.diagnostics] == [cronos_extract.DiagnosticKind.INVALID_VALUE]
        assert counts(bank, cronos_extract.DiagnosticKind.INVALID_VALUE) == 2


@pytest.mark.usefixtures("prints_nothing")
def test_a_table_with_an_id_above_255_yields_nothing_and_is_reported_once(tmp_path: Path) -> None:
    dbdir = database_with_extra_definition_key(tmp_path / "db", "Base002", patched_table_definition(tableid=300))

    with cronos_extract.open(dbdir) as bank:
        table = bank.tables[1]
        assert list(table.records()) == []
        assert list(table.records()) == []
        (diagnostic,) = [d for d in bank.diagnostics if d.kind == cronos_extract.DiagnosticKind.UNSUPPORTED_TABLE]

    assert (diagnostic.table, diagnostic.file) == ("erdgeist", "CroStru.dat")
    assert "255" in diagnostic.message


@pytest.mark.usefixtures("prints_nothing")
def test_the_bank_keeps_the_first_diagnostics_and_counts_them_all(tmp_path: Path) -> None:
    corrupt_records = DIAGNOSTICS_KEPT + 1
    dbdir = write_database(tmp_path / "db", [corrupt_compressed_record()] * corrupt_records)
    seen: list[cronos_extract.Diagnostic] = []

    with cronos_extract.open(dbdir, on_diagnostic=seen.append) as bank:
        assert list(bank.tables[0].records()) == []

        assert len(bank.diagnostics) == DIAGNOSTICS_KEPT
        assert counts(bank, cronos_extract.DiagnosticKind.CORRUPT_RECORD) == corrupt_records
        assert sum(bank.diagnostic_counts.values()) == corrupt_records + 2
        assert len(seen) == corrupt_records + 2


@pytest.mark.usefixtures("prints_nothing")
def test_a_diagnostic_kind_that_never_occurred_counts_zero_but_is_not_a_key(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [person()])

    with cronos_extract.open(dbdir) as bank:
        counts = bank.diagnostic_counts
        assert counts[cronos_extract.DiagnosticKind.CORRUPT_RECORD] == 0
        assert cronos_extract.DiagnosticKind.CORRUPT_RECORD not in counts
        assert dict(counts) == {cronos_extract.DiagnosticKind.UNEXPECTED_STRUCTURE: 2}


@pytest.mark.usefixtures("prints_nothing")
def test_an_exception_from_on_diagnostic_stops_reading_and_the_bank_still_closes(tmp_path: Path) -> None:
    class StopReading(Exception):
        pass

    def on_diagnostic(diagnostic: cronos_extract.Diagnostic) -> None:
        if diagnostic.kind == cronos_extract.DiagnosticKind.CORRUPT_RECORD:
            raise StopReading

    dbdir = write_database(tmp_path / "db", [person(), corrupt_compressed_record(), person()])

    with cronos_extract.open(dbdir, on_diagnostic=on_diagnostic) as bank:
        records = bank.tables[0].records()
        assert next(records).number == 1
        with pytest.raises(StopReading):
            next(records)


@pytest.mark.usefixtures("prints_nothing")
def test_a_later_records_pass_records_diagnostics_after_on_diagnostic_stopped_one(tmp_path: Path) -> None:
    class StopReading(Exception):
        pass

    seen: list[cronos_extract.Diagnostic] = []

    def on_diagnostic(diagnostic: cronos_extract.Diagnostic) -> None:
        seen.append(diagnostic)
        if diagnostic.kind == cronos_extract.DiagnosticKind.CORRUPT_RECORD:
            raise StopReading

    dbdir = write_database(tmp_path / "db", [corrupt_compressed_record(), person(date=b"851301")])

    with cronos_extract.open(dbdir, on_diagnostic=on_diagnostic) as bank:
        with pytest.raises(StopReading):
            list(bank.tables[0].records())
        assert counts(bank, cronos_extract.DiagnosticKind.CORRUPT_RECORD) == 1

        (record,) = bank.tables[0].records()

        assert record.number == 2
        assert counts(bank, cronos_extract.DiagnosticKind.CORRUPT_RECORD) == 1
        assert counts(bank, cronos_extract.DiagnosticKind.INVALID_VALUE) == 1
        assert [d.kind for d in bank.diagnostics][-1] == cronos_extract.DiagnosticKind.INVALID_VALUE
        assert seen[-1].kind == cronos_extract.DiagnosticKind.INVALID_VALUE


@pytest.mark.usefixtures("prints_nothing")
def test_a_generator_stops_with_value_error_once_its_bank_is_closed(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [person(), person()])
    bank = cronos_extract.open(dbdir)
    records = bank.tables[0].records()
    next(records)

    bank.close()

    with pytest.raises(ValueError, match="is closed"):
        next(records)
    assert counts(bank, cronos_extract.DiagnosticKind.CORRUPT_RECORD) == 0


@pytest.mark.usefixtures("prints_nothing")
def test_files_and_read_file_refuse_a_closed_bank(tmp_path: Path) -> None:
    bank = cronos_extract.open(write_database(tmp_path / "db", []))
    bank.close()

    with pytest.raises(ValueError, match="is closed"):
        bank.files()
    with pytest.raises(ValueError, match="is closed"):
        bank.read_file(cronos_extract.FileReference("a", "b", 1))


@pytest.mark.usefixtures("prints_nothing")
def test_generators_from_two_tables_can_be_interleaved(tmp_path: Path) -> None:
    dbdir = database_with_extra_definition_key(
        tmp_path / "db",
        "Base002",
        patched_table_definition(tableid=2),
        [person(), bank_record(2, FIELDS), person(), bank_record(2, FIELDS)],
    )

    with cronos_extract.open(dbdir) as bank:
        first, second = (table.records() for table in bank.tables)
        numbers = [next(first).number, next(second).number, next(first).number, next(second).number]

    assert numbers == [1, 2, 3, 4]


@pytest.mark.usefixtures("prints_nothing")
def test_files_yields_the_files_table_records_without_names(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [person(), file_record(b"first"), None, file_record(b"second")])

    with cronos_extract.open(dbdir) as bank:
        assert list(bank.files()) == [
            cronos_extract.EmbeddedFile(2, b"first", None),
            cronos_extract.EmbeddedFile(4, b"second", None),
        ]


@pytest.mark.usefixtures("prints_nothing")
@pytest.mark.parametrize(("extension", "name"), [("pdf", "report.pdf"), ("", "report")])
def test_read_file_follows_a_reference_and_names_the_file(tmp_path: Path, extension: str, name: str) -> None:
    reference = file_reference_field("report", extension, 2)
    dbdir = write_database(tmp_path / "db", [person(file_field=reference), file_record(b"%PDF")])

    with cronos_extract.open(dbdir) as bank:
        (record,) = bank.tables[0].records()
        value = record["Entry #6"].value
        assert isinstance(value, cronos_extract.FileReference)
        assert bank.read_file(value) == cronos_extract.EmbeddedFile(2, b"%PDF", name)


@pytest.mark.usefixtures("prints_nothing")
@pytest.mark.parametrize(
    ("reference", "reason"),
    [
        (cronos_extract.FileReference("a", "b", None), "its record number is not a number"),
        (cronos_extract.FileReference("a", "b", 0), "CroBank has no record 0"),
        (cronos_extract.FileReference("a", "b", 99), "CroBank has no record 99"),
        (cronos_extract.FileReference("a", "b", 3), "CroBank record 3 is deleted or corrupt"),
        (cronos_extract.FileReference("a", "b", 4), "CroBank record 4 is deleted or corrupt"),
        (cronos_extract.FileReference("a", "b", 1), "CroBank record 1 is not a record of the Files table"),
    ],
    ids=["no-number", "zero", "past-the-end", "deleted", "corrupt", "not-a-file"],
)
def test_a_reference_that_cannot_be_resolved_is_reported(
    tmp_path: Path, reference: cronos_extract.FileReference, reason: str
) -> None:
    dbdir = write_database(tmp_path / "db", [person(), file_record(b"x"), None, corrupt_compressed_record()])

    with cronos_extract.open(dbdir) as bank:
        assert bank.read_file(reference) is None
        (diagnostic,) = [
            d for d in bank.diagnostics if d.kind == cronos_extract.DiagnosticKind.UNRESOLVED_FILE_REFERENCE
        ]

    assert (diagnostic.file, diagnostic.record) == ("CroBank.dat", reference.record)
    assert diagnostic.message.endswith(reason)


@pytest.mark.usefixtures("prints_nothing")
def test_a_database_without_a_files_table_has_no_files(tmp_path: Path) -> None:
    dbdir = database_without_files_table(tmp_path / "db", [file_record(b"x")])

    with cronos_extract.open(dbdir) as bank:
        assert bank.files_abbreviation is None
        assert list(bank.files()) == []
        assert bank.read_file(cronos_extract.FileReference("a", "b", 1)) is None
        (diagnostic,) = [
            d for d in bank.diagnostics if d.kind == cronos_extract.DiagnosticKind.UNRESOLVED_FILE_REFERENCE
        ]
        assert diagnostic.message.endswith("the database has no Files table")


PARITY_CASES = [
    (b"01.02", None),
    (b"01.03", None),
    (b"01.04", None),
    (b"01.04", KOD),
    (b"01.05", KOD),
    (b"01.11", KOD),
]


@pytest.mark.parametrize(
    ("version", "kod"),
    PARITY_CASES,
    ids=lambda value: value.decode() if isinstance(value, bytes) else ("kod" if value else "default"),
)
def test_field_text_matches_database_enumerate_records(
    tmp_path: Path, capfd: pytest.CaptureFixture[str], version: bytes, kod: list[int] | None
) -> None:
    records = [
        person(),
        person(date=b"850000", file_field=file_reference_field("report", "pdf", 3)),
        file_record(b"%PDF"),
        corrupt_compressed_record(),
        person(date="до 1990".encode("cp1251")),
        bank_record(TEST_TABLE_ID, [b"\x1b\xff\xff\xff\x7f"]),
    ]
    if version != b"01.11":
        records.insert(3, None)
    dbdir = write_database(tmp_path / "db", records, kod, version=version)

    with Database(dbdir, False, KODcoding(kod if kod else INITIAL_KOD)) as db:
        expected_tables = {(table.tableid, table.tablename) for table in db.enumerate_tables()}
        expected = [
            (record.recno, [field.content for field in record.fields])
            for table in db.enumerate_tables()
            for record in db.enumerate_records(table)
        ]
    capfd.readouterr()

    with cronos_extract.open(
        dbdir, kod=cronos_extract.Kod.from_table(kod) if kod else cronos_extract.Kod.default()
    ) as bank:
        assert {(table.id, table.name) for table in bank.tables} == expected_tables
        actual = [
            (record.number, [field.text for field in record.fields])
            for table in bank.tables
            for record in table.records()
        ]

    assert actual == expected
    assert len(actual) == 4
    captured = capfd.readouterr()
    assert (captured.out, captured.err) == ("", "")


def test_a_checksum_mismatch_keeps_the_record_and_is_reported_once(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [compressed_record(person(), wrong_checksums={0})])

    with cronos_extract.open(dbdir) as bank:
        first = list(bank.tables[0].records())
        second = list(bank.tables[0].records())
        counts = bank.diagnostic_counts[DiagnosticKind.CHECKSUM_MISMATCH]
        diagnostics = [d for d in bank.diagnostics if d.kind == DiagnosticKind.CHECKSUM_MISMATCH]

    assert len(first) == len(second) == 1
    assert counts == 1
    assert diagnostics[0].record == 1
    assert diagnostics[0].file == "CroBank.dat"
    assert diagnostics[0].message == (
        "CroBank record 1 has 1 compressed chunk whose checksum does not match; the record is kept as it decompressed"
    )
