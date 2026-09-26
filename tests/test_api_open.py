# ABOUTME: Tests for cronos_extract's open(): what it raises, the tables and file information it reads, and diagnostics.
# ABOUTME: Uses real databases from tests/cronos_builder.py, and checks that opening prints nothing.
import os
from pathlib import Path

import pytest
from cronos_builder import (
    DAT_PREFIX_SIZE,
    TEST_TABLE_FIELD_COUNT,
    TEST_TABLE_ID,
    UNUSED_TABLE_ID,
    V3_INLINE_BIT,
    bank_record,
    database_with_extra_definition_key,
    database_with_missing_definition,
    database_with_own_kod_v4_bank,
    database_with_wrong_kod_record_out_of_range,
    patched_table_definition,
    random_kod,
    stru_records_from_test_db,
    table_definition_without_fields,
    write_database,
    write_datafile,
    write_raw_datafile,
)

import cronos_extract
from cronos_extract.koddecoder import INITIAL_KOD

SECTION_2_WARNINGS = [
    cronos_extract.Diagnostic(
        cronos_extract.DiagnosticKind.UNEXPECTED_STRUCTURE,
        f"{key}: FieldDefinition Section 2 not marked with a 2",
        file="CroStru.dat",
    )
    for key in ("Base000", "Base001")
]


class StopReading(Exception):
    pass


# Every test here also asserts that opening and reading printed nothing.
pytestmark = pytest.mark.usefixtures("prints_nothing")


def kinds(bank: cronos_extract.Bank) -> list[cronos_extract.DiagnosticKind]:
    return [diagnostic.kind for diagnostic in bank.diagnostics]


def test_open_reads_the_tables_of_a_database(tmp_path: Path) -> None:
    with cronos_extract.open(write_database(tmp_path / "db", [])) as bank:
        (table,) = bank.tables
        assert (table.id, table.name, table.abbreviation) == (1, "erdgeist", "ER")
        assert table.fields[0] == cronos_extract.FieldDefinition("Системный номер", 0)
        assert table.fields[4] == cronos_extract.FieldDefinition("Entry #4", 4)
        assert len(table.fields) == 12
        assert bank.files_abbreviation == "FL"


def test_open_reports_the_section_2_warning_of_each_table_definition(tmp_path: Path) -> None:
    with cronos_extract.open(write_database(tmp_path / "db", [])) as bank:
        assert list(bank.diagnostics) == SECTION_2_WARNINGS
        assert dict(bank.diagnostic_counts) == {cronos_extract.DiagnosticKind.UNEXPECTED_STRUCTURE: 2}


def test_open_accepts_a_path_object(tmp_path: Path) -> None:
    with cronos_extract.open(Path(write_database(tmp_path / "db", []))) as bank:
        assert [table.name for table in bank.tables] == ["erdgeist"]


def test_open_reads_a_record_spread_over_many_extension_blocks(tmp_path: Path) -> None:
    fields = [b""] * TEST_TABLE_FIELD_COUNT
    fields[1] = b"x" * (2 * 1024 * 1024)
    dbdir = write_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, fields)], extended=True)

    with cronos_extract.open(dbdir) as bank:
        (table,) = bank.tables
        (record,) = list(table.records())
        assert record["Entry #2"].text == fields[1].decode()


def test_open_with_compact_reads_the_indexes_from_disk(tmp_path: Path) -> None:
    fields = [b""] * TEST_TABLE_FIELD_COUNT
    fields[1] = b"one"
    dbdir = write_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, fields)])

    with cronos_extract.open(dbdir, compact=True) as bank:
        (table,) = bank.tables
        (record,) = list(table.records())
        assert record["Entry #2"].text == "one"


def test_bank_info_lists_the_files_found_in_order(tmp_path: Path) -> None:
    dbdir = Path(write_database(tmp_path / "db", [], index_records=[]))

    with cronos_extract.open(dbdir) as bank:
        assert [(info.name, info.path, info.version, info.problem) for info in bank.info] == [
            ("Stru", dbdir / "CroStru.dat", "01.04", None),
            ("Bank", dbdir / "CroBank.dat", "01.04", None),
            ("Index", dbdir / "CroIndex.dat", "01.04", None),
        ]


@pytest.mark.parametrize("version", [b"01.02", b"01.03", b"01.04", b"01.05", b"01.11"])
def test_open_reads_every_version_the_builder_writes(tmp_path: Path, version: bytes) -> None:
    with cronos_extract.open(write_database(tmp_path / "db", [], version=version)) as bank:
        assert [table.name for table in bank.tables] == ["erdgeist"]
        assert bank.info[0].version == version.decode()


def test_an_unreadable_index_is_reported_and_reading_goes_on(tmp_path: Path) -> None:
    dbdir = Path(write_database(tmp_path / "db", [], index_records=[]))
    (dbdir / "CroIndex.dat").write_bytes(b"NotACronosFile" + bytes(20))

    with cronos_extract.open(dbdir) as bank:
        assert [table.name for table in bank.tables] == ["erdgeist"]
        assert bank.info[2].problem is not None
        assert kinds(bank) == [cronos_extract.DiagnosticKind.UNREADABLE_FILE, *(d.kind for d in SECTION_2_WARNINGS)]


def test_a_directory_name_that_is_not_valid_utf8_opens(tmp_path: Path) -> None:
    dbdir = tmp_path / os.fsdecode(b"db-\xff\xfe")
    write_database(dbdir, [])

    with cronos_extract.open(dbdir) as bank:
        assert [table.name for table in bank.tables] == ["erdgeist"]
        assert bank.info[0].path == dbdir / "CroStru.dat"


def test_a_missing_directory_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        cronos_extract.open(tmp_path / "missing")


def test_a_file_path_raises_not_a_directory(tmp_path: Path) -> None:
    (tmp_path / "file").write_bytes(b"")

    with pytest.raises(NotADirectoryError):
        cronos_extract.open(tmp_path / "file")


def test_a_bytes_path_raises_type_error(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        cronos_extract.open(bytes(tmp_path))  # ty: ignore[invalid-argument-type]


def test_a_directory_without_a_stru_is_not_a_cronos_file(tmp_path: Path) -> None:
    (tmp_path / "CroBank.dat").write_bytes(b"")

    with pytest.raises(cronos_extract.NotACronosFile, match=r"no CroStru\.dat and CroStru\.tad") as error:
        cronos_extract.open(tmp_path)

    assert str(tmp_path) in str(error.value)


def test_a_directory_without_a_bank_is_not_a_cronos_file(tmp_path: Path) -> None:
    dbdir = Path(write_database(tmp_path / "db", []))
    (dbdir / "CroBank.dat").unlink()
    (dbdir / "CroBank.tad").unlink()

    with pytest.raises(cronos_extract.NotACronosFile, match=r"no CroBank\.dat and CroBank\.tad"):
        cronos_extract.open(dbdir)


def test_a_v7_bank_is_unsupported(tmp_path: Path) -> None:
    dbdir = Path(write_database(tmp_path / "db", []))
    data = bytearray((dbdir / "CroBank.dat").read_bytes())
    data[10:15] = b"01.19"
    (dbdir / "CroBank.dat").write_bytes(bytes(data))

    with pytest.raises(cronos_extract.UnsupportedVersion, match=r"01\.19 \(v7\)"):
        cronos_extract.open(dbdir)


def test_a_database_without_records_in_stru_has_no_definition(tmp_path: Path) -> None:
    dbdir = database_with_missing_definition(tmp_path / "db", [])

    with pytest.raises(cronos_extract.DatabaseDefinitionError, match=r"holds no records.*cronos_extract\.crack_kod"):
        cronos_extract.open(dbdir)


def test_a_deleted_definition_record_is_a_definition_error(tmp_path: Path) -> None:
    dbdir = database_with_missing_definition(tmp_path / "db", [None, *stru_records_from_test_db()[1:]])

    with pytest.raises(cronos_extract.DatabaseDefinitionError, match="is deleted"):
        cronos_extract.open(dbdir)


def test_a_stru_file_cut_to_its_header_is_a_definition_error(tmp_path: Path) -> None:
    dbdir = Path(write_database(tmp_path / "db", []))
    entries = [(DAT_PREFIX_SIZE, len(record or b"") | V3_INLINE_BIT) for record in stru_records_from_test_db()]
    write_raw_datafile(dbdir, "Stru", b"", entries)

    with pytest.raises(cronos_extract.DatabaseDefinitionError, match=r"record 1 in CroStru\.dat .* past the end"):
        cronos_extract.open(dbdir)


def test_a_wrong_kod_is_a_definition_error(tmp_path: Path) -> None:
    dbdir, wrong_kod_hex = database_with_wrong_kod_record_out_of_range(tmp_path / "db")

    with pytest.raises(cronos_extract.DatabaseDefinitionError, match="does not hold"):
        cronos_extract.open(dbdir, kod=cronos_extract.Kod.from_hex(wrong_kod_hex))


def test_a_table_definition_that_cannot_be_decoded_is_left_out(tmp_path: Path) -> None:
    dbdir = database_with_extra_definition_key(tmp_path / "db", "Base002", b"\x00")

    with cronos_extract.open(dbdir) as bank:
        assert [table.name for table in bank.tables] == ["erdgeist"]
        (diagnostic,) = [d for d in bank.diagnostics if d.kind == cronos_extract.DiagnosticKind.UNDECODABLE_TABLE]
        assert (diagnostic.file, diagnostic.message.startswith("Base002 cannot be decoded")) == ("CroStru.dat", True)


def test_a_table_without_the_system_number_field_is_left_out(tmp_path: Path) -> None:
    dbdir = database_with_extra_definition_key(tmp_path / "db", "Base002", table_definition_without_fields(tableid=2))

    with cronos_extract.open(dbdir) as bank:
        assert [table.id for table in bank.tables] == [1]
        (diagnostic,) = [d for d in bank.diagnostics if d.kind == cronos_extract.DiagnosticKind.UNDECODABLE_TABLE]
        assert (diagnostic.table, diagnostic.message) == (
            "erdgeist",
            "Base002 is left out: it does not start with the system number field",
        )


def test_a_table_with_an_id_above_255_is_kept(tmp_path: Path) -> None:
    dbdir = database_with_extra_definition_key(tmp_path / "db", "Base002", patched_table_definition(tableid=300))

    with cronos_extract.open(dbdir) as bank:
        assert [table.id for table in bank.tables] == [1, 300]


def test_a_duplicate_definition_key_is_an_unexpected_structure(tmp_path: Path) -> None:
    dbdir = database_with_extra_definition_key(tmp_path / "db", "BankName", b"again")

    with cronos_extract.open(dbdir) as bank:
        assert cronos_extract.Diagnostic(
            cronos_extract.DiagnosticKind.UNEXPECTED_STRUCTURE, "duplicate key: BankName", file="CroStru.dat", record=1
        ) in list(bank.diagnostics)


OTHER_KOD = cronos_extract.Kod.from_table(random_kod(seed=1))
KOD_KINDS = (cronos_extract.DiagnosticKind.UNUSED_KOD, cronos_extract.DiagnosticKind.MISMATCHED_KOD)
UNUSED_IN_BOTH = [
    (cronos_extract.DiagnosticKind.UNUSED_KOD, "CroStru.dat"),
    (cronos_extract.DiagnosticKind.UNUSED_KOD, "CroBank.dat"),
]
MISMATCHED_IN_BOTH = [
    (cronos_extract.DiagnosticKind.MISMATCHED_KOD, "CroStru.dat"),
    (cronos_extract.DiagnosticKind.MISMATCHED_KOD, "CroBank.dat"),
]


@pytest.mark.parametrize(
    ("version", "written_with", "opened_with", "reported"),
    [
        (b"01.04", None, OTHER_KOD, UNUSED_IN_BOTH),
        (b"01.02", None, OTHER_KOD, UNUSED_IN_BOTH),
        (b"01.04", random_kod(seed=1), OTHER_KOD, []),
        (b"01.04", None, cronos_extract.Kod.from_table(INITIAL_KOD), []),
        (b"01.04", None, None, []),
        (b"01.04", random_kod(seed=1), cronos_extract.Kod.default(), MISMATCHED_IN_BOTH),
        (b"01.04", random_kod(seed=1), None, MISMATCHED_IN_BOTH),
    ],
    ids=[
        "unencoded-own-kod-version",
        "default-kod-version",
        "encoded-with-it",
        "default-table",
        "no-kod",
        "own-kod-read-with-the-default",
        "own-kod-read-without-kod",
    ],
)
def test_each_file_reports_a_kod_that_does_not_fit_it(
    tmp_path: Path,
    version: bytes,
    written_with: list[int] | None,
    opened_with: cronos_extract.Kod | None,
    reported: list[tuple[cronos_extract.DiagnosticKind, str]],
) -> None:
    dbdir = write_database(tmp_path / "db", [], written_with, version=version)
    seen: list[cronos_extract.Diagnostic] = []

    if reported == MISMATCHED_IN_BOTH:
        # Its records do not decode, so neither does the database definition.
        with pytest.raises(cronos_extract.DatabaseDefinitionError):
            cronos_extract.open(dbdir, kod=opened_with, on_diagnostic=seen.append)
    else:
        with cronos_extract.open(dbdir, kod=opened_with, on_diagnostic=seen.append):
            pass

    assert [(diagnostic.kind, diagnostic.file) for diagnostic in seen if diagnostic.kind in KOD_KINDS] == reported


def a_record() -> bytes:
    fields = [b""] * TEST_TABLE_FIELD_COUNT
    fields[0] = b"42"
    return bank_record(TEST_TABLE_ID, fields)


@pytest.mark.parametrize("given", [False, True], ids=["left-out", "given"])
def test_an_own_kod_v4_bank_is_refused_with_the_default_kod(tmp_path: Path, given: bool) -> None:
    dbdir = database_with_own_kod_v4_bank(tmp_path / "db", [a_record(), a_record()])
    seen: list[cronos_extract.Diagnostic] = []
    kod = {"kod": cronos_extract.Kod.default()} if given else {}

    with pytest.raises(cronos_extract.OwnKodRequired) as refused:
        cronos_extract.open(dbdir, on_diagnostic=seen.append, **kod)

    assert str(refused.value) == (
        f"CroBank.dat in {dbdir} is encrypted with the database's own KOD, which the default KOD would decode as "
        'garbage. cronos_extract.crack_kod(path, "dbcrack") can recover the database\'s KOD.'
    )
    # The warning comes while CroBank is opened, so before the refusal; the definition is never decoded.
    assert [(diagnostic.kind, diagnostic.file) for diagnostic in seen] == [
        (cronos_extract.DiagnosticKind.MISMATCHED_KOD, "CroBank.dat")
    ]


def test_an_own_kod_v4_bank_opens_with_its_own_kod(tmp_path: Path) -> None:
    dbdir = database_with_own_kod_v4_bank(tmp_path / "db", [a_record(), a_record()])

    with cronos_extract.open(dbdir, kod=OTHER_KOD) as bank:
        assert [record["Entry #1"].text for table in bank.tables for record in table.records()] == ["42", "42"]


def test_an_own_kod_v4_bank_read_without_kod_decoding_is_not_refused(tmp_path: Path) -> None:
    dbdir = database_with_own_kod_v4_bank(tmp_path / "db", [a_record(), a_record()])
    seen: list[cronos_extract.Diagnostic] = []

    # CroStru is KOD-encoded too, so without KOD decoding the database definition does not decode either.
    with pytest.raises(cronos_extract.DatabaseDefinitionError):
        cronos_extract.open(dbdir, kod=None, on_diagnostic=seen.append)

    assert [(diagnostic.kind, diagnostic.file) for diagnostic in seen if diagnostic.kind in KOD_KINDS] == [
        (cronos_extract.DiagnosticKind.MISMATCHED_KOD, "CroStru.dat"),
        (cronos_extract.DiagnosticKind.MISMATCHED_KOD, "CroBank.dat"),
    ]


@pytest.mark.parametrize(
    ("version", "encoded"),
    [(b"01.04", True), (b"01.11", False)],
    ids=["v3-own-kod-version-encoded-with-the-default", "unencoded-v4"],
)
def test_a_bank_that_is_not_an_encoded_v4_bank_is_not_refused_with_the_default_kod(
    tmp_path: Path, version: bytes, encoded: bool
) -> None:
    dbdir = write_database(tmp_path / "db", [a_record()], version=version, encoded=encoded)

    with cronos_extract.open(dbdir) as bank:
        assert [record["Entry #1"].text for table in bank.tables for record in table.records()] == ["42"]


def test_crack_kod_recovers_the_kod_of_an_own_kod_v4_bank_that_open_refuses(tmp_path: Path) -> None:
    # dbcrack reads the fourth byte of CroBank and CroIndex records longer than 11 bytes, which decodes to zero.
    zero_byte_records = [bytes([UNUSED_TABLE_ID]) + bytes(11)] * 300
    dbdir = database_with_own_kod_v4_bank(tmp_path / "db", zero_byte_records)
    write_datafile(tmp_path / "db", "Index", zero_byte_records, kod=random_kod(seed=1), version=b"01.11")

    assert cronos_extract.crack_kod(dbdir, "dbcrack") == OTHER_KOD


def test_an_exception_from_on_diagnostic_during_open_reaches_the_caller(tmp_path: Path) -> None:
    def on_diagnostic(diagnostic: cronos_extract.Diagnostic) -> None:
        raise StopReading

    with pytest.raises(StopReading):
        cronos_extract.open(write_database(tmp_path / "db", []), on_diagnostic=on_diagnostic)


def test_an_exception_from_a_table_definition_warning_reaches_the_caller(tmp_path: Path) -> None:
    seen: list[cronos_extract.Diagnostic] = []

    def on_diagnostic(diagnostic: cronos_extract.Diagnostic) -> None:
        seen.append(diagnostic)
        if len(seen) == 1:
            raise StopReading

    with pytest.raises(StopReading):
        cronos_extract.open(write_database(tmp_path / "db", []), on_diagnostic=on_diagnostic)
    assert seen == SECTION_2_WARNINGS[:1]


def test_an_exception_from_a_database_definition_warning_reaches_the_caller(tmp_path: Path) -> None:
    dbdir = database_with_extra_definition_key(tmp_path / "db", "BankName", b"again")

    def on_diagnostic(diagnostic: cronos_extract.Diagnostic) -> None:
        if diagnostic.message == "duplicate key: BankName":
            raise StopReading

    with pytest.raises(StopReading):
        cronos_extract.open(dbdir, on_diagnostic=on_diagnostic)


def test_on_diagnostic_receives_the_diagnostics_of_open(tmp_path: Path) -> None:
    seen: list[cronos_extract.Diagnostic] = []

    with cronos_extract.open(write_database(tmp_path / "db", []), on_diagnostic=seen.append):
        assert seen == SECTION_2_WARNINGS


def test_closing_twice_is_harmless_and_a_closed_bank_refuses_to_read(tmp_path: Path) -> None:
    bank = cronos_extract.open(write_database(tmp_path / "db", []))
    table = bank.tables[0]

    bank.close()
    bank.close()

    with pytest.raises(ValueError, match="is closed"):
        table.records()
