# ABOUTME: Tests that databases written by tests/cronos_builder.py are read back correctly by cronos_extract.
# ABOUTME: They prove the fixture builder before other tests rely on it to reproduce bugs.
import io
import struct
import zlib
from pathlib import Path

import pytest
from cronos_builder import (
    BLOCKSIZE,
    BUILDER_VERSIONS,
    DAT_PREFIX_SIZE,
    TEST_DB,
    TEST_TABLE_FIELD_COUNT,
    TEST_TABLE_FILE_FIELD_INDEX,
    TEST_TABLE_ID,
    V3_INLINE_BIT,
    bank_record,
    compressed_record,
    database_with_extra_definition_key,
    database_with_files_abbreviation,
    database_with_missing_definition,
    database_without_files_table,
    duplicate_table_name_database,
    erdgeist_table_definition,
    field_definition_with_nul_name,
    file_record,
    file_reference_field,
    key_referencing_a_deleted_record,
    patched_table_definition,
    random_kod,
    record_with_file_field,
    renamed_table_definition,
    stru_records_from_test_db,
    table_definition_without_fields,
    tad_layout,
    write_database,
    write_datafile,
    write_header_only_datafile,
)

import cronos_extract
from cronos_extract._format.header import DatHeader, read_dat_header
from cronos_extract.Database import KOD_HINT, Database
from cronos_extract.Datamodel import TableDefinition
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


def test_write_header_only_datafile_writes_just_the_header(tmp_path: Path) -> None:
    write_header_only_datafile(tmp_path, "Bank", version=b"01.19", encoding=3)

    data = (tmp_path / "CroBank.dat").read_bytes()
    assert len(data) == 19
    assert read_dat_header(io.BytesIO(data), where="CroBank.dat") == DatHeader(
        version=b"01.19", unknown=0, encoding=3, blocksize=BLOCKSIZE
    )
    assert not (tmp_path / "CroBank.tad").exists()


VERSIONS_AND_KODS = [
    (b"01.02", None),
    (b"01.03", None),
    (b"01.04", random_kod(seed=3)),
    (b"01.05", random_kod(seed=3)),
    (b"01.11", random_kod(seed=3)),
]


@pytest.mark.parametrize(
    ("version", "kod"),
    VERSIONS_AND_KODS,
    ids=lambda value: value.decode() if isinstance(value, bytes) else ("kod" if value else "default"),
)
def test_a_database_of_each_version_reads_back_through_database(
    tmp_path: Path, version: bytes, kod: list[int] | None
) -> None:
    record = person_record(b"")
    dbdir = write_database(tmp_path / "db", [record, record], kod, version=version)

    with Database(dbdir, False, KODcoding(kod if kod else INITIAL_KOD)) as db:
        assert db.bank is not None
        assert db.bank.version == version
        assert [db.bank.readrec(recno) for recno in (1, 2)] == [record, record]
        assert [table.tablename for table in db.enumerate_tables()] == ["erdgeist"]


@pytest.mark.parametrize(
    ("version", "header_size", "entry_size"),
    [(b"01.02", 8, 12), (b"01.03", 8, 16), (b"01.04", 8, 12), (b"01.05", 8, 16), (b"01.11", 16, 16)],
)
def test_the_tad_file_has_its_versions_header_and_entry_size(
    tmp_path: Path, version: bytes, header_size: int, entry_size: int
) -> None:
    write_datafile(tmp_path, "Bank", [b"\x01abc", b"\x01de"], version=version)

    assert len((tmp_path / "CroBank.tad").read_bytes()) == header_size + 2 * entry_size


def test_a_v4_tad_header_starts_with_the_marker_real_files_have(tmp_path: Path) -> None:
    write_datafile(tmp_path, "Bank", [], version=b"01.11")

    assert struct.unpack("<4L", (tmp_path / "CroBank.tad").read_bytes()) == (0xFFFFFFFE, 0, 0, 0)


def test_v4_record_flags_are_in_the_top_byte_of_the_offset(tmp_path: Path) -> None:
    write_datafile(tmp_path, "Bank", [b"\x01abc"], version=b"01.11")

    offset, length, _ = struct.unpack("<QLL", (tmp_path / "CroBank.tad").read_bytes()[16:])
    assert (offset >> 56, offset & ((1 << 56) - 1), length) == (0x04, DAT_PREFIX_SIZE, 4)


def test_v3_record_flags_are_in_the_top_byte_of_the_length(tmp_path: Path) -> None:
    write_datafile(tmp_path, "Bank", [b"\x01abc"], version=b"01.03")

    offset, length, _ = struct.unpack("<QLL", (tmp_path / "CroBank.tad").read_bytes()[8:])
    assert (offset, length >> 24, length & 0xFFFFFF) == (DAT_PREFIX_SIZE, 0x80, 4)


@pytest.mark.parametrize("version", [b"01.02", b"01.03"])
def test_the_builder_refuses_a_kod_for_a_version_read_with_the_default_kod(tmp_path: Path, version: bytes) -> None:
    with pytest.raises(ValueError, match="default KOD"):
        write_datafile(tmp_path, "Bank", [b"\x01abc"], kod=random_kod(seed=3), version=version)


def test_the_builder_refuses_a_deleted_v4_record(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="deleted v4 record"):
        write_datafile(tmp_path, "Bank", [None], version=b"01.11")


def test_the_builder_refuses_a_version_it_cannot_write(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cannot write version"):
        write_datafile(tmp_path, "Bank", [], version=b"01.19")


def test_the_builder_versions_are_the_ones_the_spec_names() -> None:
    assert BUILDER_VERSIONS == (b"01.02", b"01.03", b"01.04", b"01.05", b"01.11")


def test_a_patched_table_definition_changes_the_table_id(tmp_path: Path) -> None:
    dbdir = database_with_extra_definition_key(tmp_path / "db", "Base002", patched_table_definition(tableid=300))

    with Database(dbdir, False, KODcoding(INITIAL_KOD)) as db:
        assert [(table.tableid, table.tablename) for table in db.enumerate_tables()] == [
            (1, "erdgeist"),
            (300, "erdgeist"),
        ]


def test_a_patched_table_definition_changes_only_the_table_id_bytes() -> None:
    patched = patched_table_definition(tableid=0x01020304)
    original = erdgeist_table_definition()

    assert len(patched) == len(original)
    assert [index for index in range(len(original)) if patched[index] != original[index]] == [14, 15, 16, 17]


def test_a_table_definition_without_fields_decodes_to_a_table_with_no_fields() -> None:
    messages: list[str] = []

    table = TableDefinition(table_definition_without_fields(tableid=2), warn=messages.append)

    assert (table.tableid, table.tablename, table.abbrev, table.fields, messages) == (2, "erdgeist", "ER", [], [])


def test_an_extra_definition_key_holds_its_value_inline(tmp_path: Path) -> None:
    dbdir = database_with_extra_definition_key(tmp_path / "db", "Extra", b"\x01\x02")

    with Database(dbdir, False, KODcoding(INITIAL_KOD)) as db:
        assert db.read_db_definition()["Extra"] == b"\x01\x02"


def test_a_database_without_a_files_table_has_no_base000_key(tmp_path: Path) -> None:
    dbdir = database_without_files_table(tmp_path / "db")

    with Database(dbdir, False, KODcoding(INITIAL_KOD)) as db:
        keys = db.read_db_definition().keys()
        assert "Base000" not in keys
        assert "Base001" in keys


def test_renamed_table_definition_changes_the_name_and_the_abbreviation(tmp_path: Path) -> None:
    second = renamed_table_definition(patched_table_definition(tableid=2), name=b"other", abbreviation=b"OT")
    dbdir = database_with_extra_definition_key(tmp_path / "db", "Base002", second)

    with cronos_extract.open(dbdir) as bank:
        assert [(table.id, table.name, table.abbreviation) for table in bank.tables] == [
            (1, "erdgeist", "ER"),
            (2, "other", "OT"),
        ]


def test_field_definition_with_nul_name_puts_a_nul_in_the_first_fields_name(tmp_path: Path) -> None:
    definition = field_definition_with_nul_name(patched_table_definition(tableid=2))
    dbdir = database_with_extra_definition_key(tmp_path / "db", "Base002", definition)

    with cronos_extract.open(dbdir) as bank:
        table = next(table for table in bank.tables if table.id == 2)
        assert "\x00" in table.fields[0].name


def test_database_with_files_abbreviation_gives_the_files_table_that_abbreviation(tmp_path: Path) -> None:
    dbdir = database_with_files_abbreviation(tmp_path / "db", "Файлы".encode("cp1251"), [file_record(b"DATA")])

    with cronos_extract.open(dbdir) as bank:
        assert bank.files_abbreviation == "Файлы"
        assert [file.data for file in bank.files()] == [b"DATA"]


def test_duplicate_table_name_database_holds_two_tables_with_one_name(tmp_path: Path) -> None:
    with cronos_extract.open(duplicate_table_name_database(tmp_path / "db")) as bank:
        assert [(table.id, table.name) for table in bank.tables] == [(1, "erdgeist"), (2, "erdgeist")]
        assert [[record.fields[2].text for record in table.records()] for table in bank.tables] == [["one"], ["two"]]


def test_record_with_file_field_puts_the_reference_in_the_file_field(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [record_with_file_field(file_reference_field("scan", "jpg", 7))])

    with cronos_extract.open(dbdir) as bank:
        (record,) = bank.tables[0].records()
        assert record["Entry #6"].value == cronos_extract.FileReference("scan", "jpg", 7)


def test_compressed_record_holds_the_crc_of_each_chunk() -> None:
    record = compressed_record(b"one", b"two", wrong_checksums={1})

    offset = 0
    crcs = []
    while offset < len(record) - 3:
        size, _ = struct.unpack_from(">HH", record, offset)
        (crc,) = struct.unpack_from("<L", record, offset + 4)
        crcs.append(crc)
        offset += size + 2

    assert crcs == [zlib.crc32(b"one"), zlib.crc32(b"two") ^ 0xFFFFFFFF]
    assert record.endswith(b"\x00\x00\x02")


@pytest.mark.parametrize("version", [b"01.02", b"01.03", b"01.04"])
def test_a_v3_inline_record_sets_bit_31_of_its_length(tmp_path: Path, version: bytes) -> None:
    write_datafile(tmp_path, "Bank", [b"hello"], version=version)

    header, entry = tad_layout(version)
    tad = (tmp_path / "CroBank.tad").read_bytes()
    _, length, _ = entry.unpack_from(tad, len(header))

    assert length == 5 | V3_INLINE_BIT


@pytest.mark.parametrize("version", [b"01.02", b"01.03"])
def test_a_database_of_a_default_kod_version_can_be_written_kod_encoded(tmp_path: Path, version: bytes) -> None:
    fields = [b""] * TEST_TABLE_FIELD_COUNT
    fields[0] = b"encoded"
    dbdir = write_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, fields)], version=version, encoded=True)

    assert (Path(dbdir) / "CroBank.dat").read_bytes()[15] & 1
    with cronos_extract.open(dbdir) as bank:
        (record,) = bank.tables[0].records()
        assert record.fields[1].text == "encoded"
