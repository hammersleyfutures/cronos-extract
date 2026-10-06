# ABOUTME: Tests for reading records and files through the cronos_extract API: laziness, diagnostics and closing.
# ABOUTME: Also builds the golden records and golden-file JSONL tests/test_api_golden.py checks per builder version.
import datetime
import json
from collections import Counter
from pathlib import Path

import pytest
from cronos_builder import (
    DAT_PREFIX_SIZE,
    TEST_TABLE_FIELD_COUNT,
    TEST_TABLE_FILE_FIELD_INDEX,
    TEST_TABLE_ID,
    V3_INLINE_BIT,
    DeletedRecord,
    bank_record,
    compressed_record,
    corrupt_compressed_record,
    database_with_extra_definition_key,
    database_without_files_table,
    file_record,
    file_reference_field,
    patched_table_definition,
    random_kod,
    renamed_table_definition,
    write_database,
    write_raw_datafile,
)

import cronos_extract
from cronos_extract import DiagnosticKind
from cronos_extract._api.diagnostics import DIAGNOSTICS_KEPT

KOD = random_kod(seed=11)
FIELDS = [b"42", b"Hammersley", "Привет".encode("cp1251"), b"1240315", b"0930", b"", b"seven", b"", b"", b"", b"x"]


def person(*, date: bytes = b"1240315", file_field: bytes = b"") -> bytes:
    fields = list(FIELDS)
    fields[3] = date
    fields[TEST_TABLE_FILE_FIELD_INDEX] = file_field
    return bank_record(TEST_TABLE_ID, fields)


def counts(bank: cronos_extract.Bank, kind: cronos_extract.DiagnosticKind) -> int:
    return bank.diagnostic_counts.get(kind, 0)


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
@pytest.mark.parametrize("extended", [False, True], ids=["inline", "extended"])
def test_a_deleted_v4_record_is_not_read(tmp_path: Path, extended: bool) -> None:
    dbdir = write_database(
        tmp_path / "db", [person(), DeletedRecord(person()), person()], version=b"01.11", extended=extended
    )

    with cronos_extract.open(dbdir) as bank:
        records = list(bank.tables[0].records())
        # A flag-02 entry read as inline would put its extended header in no table, so check the entry itself.
        assert bank._bank_file.read_record(2) is None

    assert [record.number for record in records] == [1, 3]


@pytest.mark.usefixtures("prints_nothing")
@pytest.mark.parametrize(
    ("version", "records", "expected"),
    [
        (b"01.02", [person(), None, person()], 1),
        (b"01.11", [person(), DeletedRecord(person()), person()], 1),
        (b"01.02", [person(), person()], 0),
        (b"01.11", [person(), person()], 0),
    ],
    ids=["v3-one-deleted", "v4-one-deleted", "v3-none-deleted", "v4-none-deleted"],
)
def test_deleted_records_is_the_crobank_tad_header_count(
    tmp_path: Path, version: bytes, records: list[bytes | DeletedRecord | None], expected: int
) -> None:
    dbdir = write_database(tmp_path / "db", records, version=version)

    with cronos_extract.open(dbdir) as bank:
        assert bank.deleted_records == expected
        assert [d for d in bank.diagnostics if d.file == "CroBank.dat"] == []


@pytest.mark.usefixtures("prints_nothing")
def test_a_tad_header_listing_more_deleted_records_than_entries_is_capped_and_reported(tmp_path: Path) -> None:
    dbdir = Path(write_database(tmp_path / "db", []))
    data = person()
    entries = [(DAT_PREFIX_SIZE, len(data) | V3_INLINE_BIT)] * 2
    write_raw_datafile(dbdir, "Bank", data, entries, deleted_count=999)
    seen: list[cronos_extract.Diagnostic] = []

    with cronos_extract.open(dbdir, on_diagnostic=seen.append) as bank:
        assert bank.deleted_records == 2
        assert [record.number for record in bank.tables[0].records()] == [1, 2]

    assert [(d.kind, d.message, d.table, d.record, d.field) for d in seen if d.file == "CroBank.dat"] == [
        (
            cronos_extract.DiagnosticKind.UNEXPECTED_STRUCTURE,
            "the .tad header lists 999 deleted records, more than its 2 entries",
            None,
            None,
            None,
        )
    ]


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
def test_a_record_pointing_far_past_the_end_of_the_file_is_corrupt(tmp_path: Path) -> None:
    # 1 << 50 does not fit a 32-bit offset, so this uses a 64-bit v3 version; on an ordinary disk, seeking that far
    # past the end of the file raises OSError, which readdata must avoid so the record is reported as corrupt
    # instead of stopping the whole export.
    dbdir = Path(write_database(tmp_path / "db", [], version=b"01.03"))
    data = person()
    write_raw_datafile(
        dbdir,
        "Bank",
        data,
        [
            (DAT_PREFIX_SIZE, len(data) | V3_INLINE_BIT),
            (1 << 50, 5 | V3_INLINE_BIT),
        ],
        version=b"01.03",
    )

    with cronos_extract.open(dbdir) as bank:
        assert [record.number for record in bank.tables[0].records()] == [1]
        corrupt = [d for d in bank.diagnostics if d.kind == cronos_extract.DiagnosticKind.CORRUPT_RECORD]

    assert [(d.file, d.record) for d in corrupt] == [("CroBank.dat", 2)]
    assert "past the end" in corrupt[0].message


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


# Table 1 holds records 1, 6 and 9; table 2 records 2 and 7; the Files table records 3 and 8.
# Record 4 is deleted and record 5 is corrupt.
TABLE_1_NUMBERS = [1, 6, 9]
TABLE_2_NUMBERS = [2, 7]


def mixed_database(directory: Path) -> str:
    return database_with_extra_definition_key(
        directory,
        "Base002",
        patched_table_definition(tableid=2),
        [
            person(),
            bank_record(2, FIELDS),
            file_record(b"first"),
            None,
            corrupt_compressed_record(),
            person(date=b"850000"),
            bank_record(2, FIELDS),
            file_record(b"second"),
            person(),
        ],
    )


def record_reads(bank: cronos_extract.Bank, monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Record the number of each CroBank record `bank` reads, delegating every read to the real Datafile."""
    numbers: list[int] = []
    read_record = bank._bank_file.read_record

    def recording_read_record(number: int) -> object:
        numbers.append(number)
        return read_record(number)

    monkeypatch.setattr(bank._bank_file, "read_record", recording_read_record)
    return numbers


def sequential_reads(dbdir: str) -> tuple[list[cronos_extract.Record], list[cronos_extract.Record]]:
    """Table 1's and table 2's records, read one table after the other from a freshly opened bank."""
    with cronos_extract.open(dbdir) as bank:
        first, second = bank.tables
        return list(first.records()), list(second.records())


@pytest.mark.usefixtures("prints_nothing")
def test_the_mixed_database_holds_the_records_its_comment_says(tmp_path: Path) -> None:
    first, second = sequential_reads(mixed_database(tmp_path / "db"))

    assert [record.number for record in first] == TABLE_1_NUMBERS
    assert [record.number for record in second] == TABLE_2_NUMBERS


@pytest.mark.usefixtures("prints_nothing")
def test_a_table_read_after_another_reads_only_its_own_records(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dbdir = mixed_database(tmp_path / "db")
    expected = sequential_reads(dbdir)

    with cronos_extract.open(dbdir) as bank:
        reads = record_reads(bank, monkeypatch)
        first, second = bank.tables
        assert list(first.records()) == expected[0]
        reads.clear()
        assert list(second.records()) == expected[1]

    assert reads == TABLE_2_NUMBERS


@pytest.mark.usefixtures("prints_nothing")
def test_an_export_reads_each_live_record_at_most_twice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dbdir = mixed_database(tmp_path / "db")
    expected = sequential_reads(dbdir)

    with cronos_extract.open(dbdir) as bank:
        reads = record_reads(bank, monkeypatch)
        first, second = bank.tables
        yielded = (list(first.records()), list(second.records()))
        files = list(bank.files())

    assert yielded == expected
    assert files == [
        cronos_extract.EmbeddedFile(3, b"first", None),
        cronos_extract.EmbeddedFile(8, b"second", None),
    ]
    assert max(Counter(reads).values()) <= 2
    assert sorted(set(reads)) == list(range(1, 10))


@pytest.mark.usefixtures("prints_nothing")
def test_interleaved_generators_yield_what_sequential_ones_do(tmp_path: Path) -> None:
    dbdir = mixed_database(tmp_path / "db")
    expected = sequential_reads(dbdir)
    yielded: tuple[list[cronos_extract.Record], list[cronos_extract.Record]] = ([], [])

    with cronos_extract.open(dbdir) as bank:
        generators = [table.records() for table in bank.tables]
        while generators:
            for generator in list(generators):
                record = next(generator, None)
                if record is None:
                    generators.remove(generator)
                else:
                    yielded[record.number in TABLE_2_NUMBERS].append(record)

    assert yielded == expected


@pytest.mark.usefixtures("prints_nothing")
def test_an_abandoned_generator_leaves_the_index_whole(tmp_path: Path) -> None:
    dbdir = mixed_database(tmp_path / "db")
    expected = sequential_reads(dbdir)

    with cronos_extract.open(dbdir) as bank:
        first, second = bank.tables
        abandoned = first.records()
        assert next(abandoned) == expected[0][0]
        del abandoned
        assert list(second.records()) == expected[1]
        assert list(first.records()) == expected[0]


@pytest.mark.usefixtures("prints_nothing")
def test_a_second_pass_reads_no_other_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dbdir = mixed_database(tmp_path / "db")

    with cronos_extract.open(dbdir) as bank:
        reads = record_reads(bank, monkeypatch)
        first, second = bank.tables
        list(first.records())
        list(second.records())
        list(bank.files())
        reads.clear()
        assert [record.number for record in first.records()] == TABLE_1_NUMBERS

    assert reads == TABLE_1_NUMBERS


@pytest.mark.usefixtures("prints_nothing")
def test_a_records_loop_started_from_on_diagnostic_does_not_duplicate_records(tmp_path: Path) -> None:
    dbdir = mixed_database(tmp_path / "db")
    expected = sequential_reads(dbdir)
    opened: list[cronos_extract.Bank] = []
    read_from_on_diagnostic: list[cronos_extract.Record] = []

    def on_diagnostic(diagnostic: cronos_extract.Diagnostic) -> None:
        if diagnostic.kind == DiagnosticKind.CORRUPT_RECORD:
            read_from_on_diagnostic.extend(opened[0].tables[0].records())

    with cronos_extract.open(dbdir, on_diagnostic=on_diagnostic) as bank:
        opened.append(bank)
        first, second = bank.tables
        yielded = (list(first.records()), list(second.records()))
        again = (list(first.records()), list(second.records()))

    assert read_from_on_diagnostic == expected[0]
    assert yielded == expected
    assert again == expected


@pytest.mark.usefixtures("prints_nothing")
def test_a_scan_stopped_by_on_diagnostic_at_a_live_record_still_indexes_it(tmp_path: Path) -> None:
    class StopReading(Exception):
        pass

    def on_diagnostic(diagnostic: cronos_extract.Diagnostic) -> None:
        if diagnostic.kind == DiagnosticKind.CHECKSUM_MISMATCH:
            raise StopReading

    dbdir = database_with_extra_definition_key(
        tmp_path / "db",
        "Base002",
        patched_table_definition(tableid=2),
        [person(), compressed_record(bank_record(2, FIELDS), wrong_checksums={0}), person()],
    )

    with cronos_extract.open(dbdir, on_diagnostic=on_diagnostic) as bank:
        first, second = bank.tables
        with pytest.raises(StopReading):
            list(first.records())
        assert [record.number for record in first.records()] == [1, 3]
        assert [record.number for record in second.records()] == [2]


@pytest.mark.usefixtures("prints_nothing")
def test_bank_records_reads_every_record_once_in_crobank_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dbdir = mixed_database(tmp_path / "db")
    expected = sequential_reads(dbdir)

    with cronos_extract.open(dbdir) as bank:
        reads = record_reads(bank, monkeypatch)
        first, second = bank.tables
        pairs = list(bank.records())

    assert [(table.name, table.id, record.number) for table, record in pairs] == [
        (first.name, first.id, 1),
        (second.name, second.id, 2),
        (first.name, first.id, 6),
        (second.name, second.id, 7),
        (first.name, first.id, 9),
    ]
    assert [record for table, record in pairs if table is first] == expected[0]
    assert [record for table, record in pairs if table is second] == expected[1]
    assert reads == list(range(1, 10))


@pytest.mark.usefixtures("prints_nothing")
def test_bank_records_indexes_crobank_for_the_tables_read_afterwards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dbdir = mixed_database(tmp_path / "db")
    expected = sequential_reads(dbdir)

    with cronos_extract.open(dbdir) as bank:
        first, second = bank.tables
        pairs = bank.records()
        # Stop after record 2, so the tables read the rest of CroBank themselves.
        assert [record.number for _, record in (next(pairs), next(pairs))] == [1, 2]
        reads = record_reads(bank, monkeypatch)
        assert list(second.records()) == expected[1]
        assert reads == [2, *range(3, 10)]
        reads.clear()
        assert list(first.records()) == expected[0]
        assert reads == TABLE_1_NUMBERS
        assert [record.number for _, record in pairs] == [6, 7, 9]


@pytest.mark.usefixtures("prints_nothing")
def test_bank_records_after_the_tables_yields_what_they_did(tmp_path: Path) -> None:
    dbdir = mixed_database(tmp_path / "db")
    expected = sequential_reads(dbdir)

    with cronos_extract.open(dbdir) as bank:
        first, second = bank.tables
        list(first.records())
        pairs = list(bank.records())

    assert [record for table, record in pairs if table is first] == expected[0]
    assert [record for table, record in pairs if table is second] == expected[1]


@pytest.mark.usefixtures("prints_nothing")
def test_bank_records_yields_a_record_once_for_each_table_with_its_id(tmp_path: Path) -> None:
    other = renamed_table_definition(patched_table_definition(tableid=TEST_TABLE_ID), name=b"other")
    dbdir = database_with_extra_definition_key(tmp_path / "db", "Base002", other, [person(), person()])

    with cronos_extract.open(dbdir) as bank:
        pairs = [(table.name, record.number) for table, record in bank.records()]

    assert pairs == [("erdgeist", 1), ("other", 1), ("erdgeist", 2), ("other", 2)]


@pytest.mark.usefixtures("prints_nothing")
def test_bank_records_reports_a_table_with_an_id_above_255_once(tmp_path: Path) -> None:
    dbdir = database_with_extra_definition_key(
        tmp_path / "db", "Base002", patched_table_definition(tableid=300), [person()]
    )

    with cronos_extract.open(dbdir) as bank:
        assert [(table.name, record.number) for table, record in bank.records()] == [("erdgeist", 1)]
        assert list(bank.tables[1].records()) == []
        assert counts(bank, cronos_extract.DiagnosticKind.UNSUPPORTED_TABLE) == 1


@pytest.mark.usefixtures("prints_nothing")
def test_bank_records_refuses_a_closed_bank(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [person(), person()])
    bank = cronos_extract.open(dbdir)
    pairs = bank.records()
    next(pairs)

    bank.close()

    with pytest.raises(ValueError, match="is closed"):
        next(pairs)
    with pytest.raises(ValueError, match="is closed"):
        bank.records()


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
    ("reference", "message"),
    [
        (cronos_extract.FileReference("a", "b", None), "the file cannot be read: its record number is not a number"),
        (
            cronos_extract.FileReference("a", "b", 0),
            "the file in CroBank record 0 cannot be read: CroBank has no such record",
        ),
        (
            cronos_extract.FileReference("a", "b", 99),
            "the file in CroBank record 99 cannot be read: CroBank has no such record",
        ),
        (
            cronos_extract.FileReference("a", "b", 3),
            "the file in CroBank record 3 cannot be read: the record is deleted or corrupt",
        ),
        (
            cronos_extract.FileReference("a", "b", 4),
            "the file in CroBank record 4 cannot be read: the record is deleted or corrupt",
        ),
        (
            cronos_extract.FileReference("a", "b", 1),
            "the file in CroBank record 1 cannot be read: the record is not in the Files table",
        ),
    ],
    ids=["no-number", "zero", "past-the-end", "deleted", "corrupt", "not-a-file"],
)
def test_a_reference_that_cannot_be_resolved_is_reported(
    tmp_path: Path, reference: cronos_extract.FileReference, message: str
) -> None:
    dbdir = write_database(tmp_path / "db", [person(), file_record(b"x"), None, corrupt_compressed_record()])

    with cronos_extract.open(dbdir) as bank:
        assert bank.read_file(reference) is None
        (diagnostic,) = [
            d for d in bank.diagnostics if d.kind == cronos_extract.DiagnosticKind.UNRESOLVED_FILE_REFERENCE
        ]

    assert (diagnostic.file, diagnostic.table, diagnostic.record, diagnostic.field) == ("CroBank.dat", None, None, None)
    assert diagnostic.message == message


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
        assert diagnostic.message == "the file in CroBank record 1 cannot be read: the database has no Files table"


@pytest.mark.usefixtures("prints_nothing")
def test_a_decoded_reference_carries_where_it_was_read(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [person(file_field=file_reference_field("report", "pdf", 99))])

    with cronos_extract.open(dbdir) as bank:
        (record,) = bank.tables[0].records()
        reference = record["Entry #6"].value
        assert reference == cronos_extract.FileReference("report", "pdf", 99, "erdgeist", 1, "Entry #6")
        assert isinstance(reference, cronos_extract.FileReference)
        assert bank.read_file(reference) is None
        unresolved = [d for d in bank.diagnostics if d.kind == DiagnosticKind.UNRESOLVED_FILE_REFERENCE]

    assert unresolved == [
        cronos_extract.Diagnostic(
            DiagnosticKind.UNRESOLVED_FILE_REFERENCE,
            "the file in CroBank record 99 cannot be read: CroBank has no such record",
            file="CroBank.dat",
            table="erdgeist",
            record=1,
            field="Entry #6",
        )
    ]


@pytest.mark.usefixtures("prints_nothing")
def test_a_reference_read_by_the_second_table_read_carries_where_it_was_read(tmp_path: Path) -> None:
    second = renamed_table_definition(patched_table_definition(tableid=2), name=b"other")
    fields = [b""] * TEST_TABLE_FIELD_COUNT
    fields[TEST_TABLE_FILE_FIELD_INDEX] = file_reference_field("scan", "jpg", 99)
    dbdir = database_with_extra_definition_key(
        tmp_path / "db", "Base002", second, [person(), bank_record(2, fields), person()]
    )

    with cronos_extract.open(dbdir) as bank:
        first_table, second_table = bank.tables
        assert [record.number for record in first_table.records()] == [1, 3]
        (record,) = second_table.records()
        reference = record["Entry #6"].value
        assert reference == cronos_extract.FileReference("scan", "jpg", 99, "other", 2, "Entry #6")
        assert isinstance(reference, cronos_extract.FileReference)
        assert bank.read_file(reference) is None
        (diagnostic,) = [d for d in bank.diagnostics if d.kind == DiagnosticKind.UNRESOLVED_FILE_REFERENCE]

    assert (diagnostic.file, diagnostic.table, diagnostic.record, diagnostic.field) == (
        "CroBank.dat",
        "other",
        2,
        "Entry #6",
    )


GOLDEN_CASES = [
    (b"01.02", None),
    (b"01.03", None),
    (b"01.04", None),
    (b"01.04", KOD),
    (b"01.05", KOD),
    (b"01.11", KOD),
]


def golden_records(version: bytes) -> list[bytes | DeletedRecord | None]:
    """The records the golden tests write, including a deleted record: v4 keeps a deleted record's data."""
    records: list[bytes | DeletedRecord | None] = [
        person(),
        person(date=b"850000", file_field=file_reference_field("report", "pdf", 3)),
        file_record(b"%PDF"),
        corrupt_compressed_record(),
        person(date="до 1990".encode("cp1251")),
        bank_record(TEST_TABLE_ID, [b"\x1b\xff\xff\xff\x7f"]),
    ]
    records.insert(3, DeletedRecord(person()) if version == b"01.11" else None)
    return records


def render_api_jsonl(bank: cronos_extract.Bank) -> str:
    """One JSON line per record read through the API, in the order `bank.tables` and `Table.records()` yield them."""
    lines = [
        json.dumps(
            {
                "table_id": table.id,
                "table": table.name,
                "record": record.number,
                "fields": [field.text for field in record.fields],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        for table in bank.tables
        for record in table.records()
    ]
    return "".join(f"{line}\n" for line in lines)


def golden_api_name(version: bytes, kod: list[int] | None, *, extended: bool) -> str:
    return f"api/{version.decode()}-{'kod' if kod else 'default'}-{'extended' if extended else 'inline'}.jsonl"


def golden_case_id(value: bytes | list[int] | None) -> str:
    return value.decode() if isinstance(value, bytes) else ("kod" if value else "default")


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
