# ABOUTME: Builds CronosPro v3 database directories for tests, optionally encrypted with a chosen KOD table.
# ABOUTME: Record layouts follow docs/cronos-research.md as the reader parses them, so tests can craft any database.
import random
import struct
import zlib
from collections.abc import Collection, Sequence
from pathlib import Path
from typing import cast

from cronos_extract.Database import Database
from cronos_extract.Datamodel import TableDefinition
from cronos_extract.koddecoder import INITIAL_KOD, KODcoding
from cronos_extract.readers import ByteReader

TEST_DB = Path(__file__).resolve().parent.parent / "test_data" / "all_field_types"

# The table "erdgeist" in TEST_DB: table id 1, eleven fields after the system number,
# of which the sixth ("Entry #6", index 5) is a file reference (field type 6).
TEST_TABLE_ID = 1
TEST_TABLE_FIELD_COUNT = 11
TEST_TABLE_FILE_FIELD_INDEX = 5
FILES_TABLE_ID = 0
# A table id that no table in TEST_DB uses, for records that only exist to feed dbcrack.
UNUSED_TABLE_ID = 0xFE

DAT_HEADER = struct.Struct("<8sH5sHH")
DAT_HEADER_PADDING = 0xE9
TAD_V3_HEADER = struct.Struct("<2L")
TAD_V4_HEADER = struct.Struct("<4L")
# The first dword of every .tad header in Ben's real v4 databases.
TAD_V4_MARKER = 0xFFFFFFFE
TAD_V3_ENTRY = struct.Struct("<LLL")
TAD_64BIT_ENTRY = struct.Struct("<QLL")
BLOCKSIZE = 0x40
# Size of the .dat file header and the padding that follows it; the first record starts here.
DAT_PREFIX_SIZE = DAT_HEADER.size + DAT_HEADER_PADDING
# Version 01.04 is a 32-bit v3 file whose records are decoded with the database's own KOD table.
ENCRYPTED_V3_VERSION = b"01.04"
BUILDER_VERSIONS = (b"01.02", b"01.03", b"01.04", b"01.05", b"01.11")
VERSIONS_64BIT = (b"01.03", b"01.05", b"01.11")
V4_VERSIONS = (b"01.11",)
# Datafile decodes every other version with the default KOD table, whatever table it is given.
OWN_KOD_VERSIONS = (b"01.04", b"01.05", b"01.11")
# A v3 .tad entry keeps its inline flag in bit 31 of the length field; the length is bits 0-30.
V3_INLINE_BIT = 1 << 31
# A v4 .tad keeps the flag byte in the top of the offset; 0x04 marks a record stored inline.
V4_INLINE_RECORD_FLAGS = 0x04
DELETED_RECORD_LENGTH = 0xFFFFFFFF
FIELD_SEPARATOR = b"\x1e"
COMPLEX_FIELD_MARKER = b"\x1b"
# The high bit of a database definition key's length says its value follows inline.
INLINE_DEFINITION_VALUE = 0x80000000
# Offsets in TEST_DB's Base001 definition: the table id, and the number of field definitions after the names.
TABLE_ID_OFFSET = 14
FIELD_COUNT_OFFSET = 34


def random_kod(seed: int) -> list[int]:
    """Return a reproducible random permutation of 0..255 to use as a database's KOD table."""
    kod = list(range(256))
    random.Random(seed).shuffle(kod)
    return kod


def tad_layout(version: bytes) -> tuple[bytes, struct.Struct]:
    """Return the .tad header bytes and the .tad entry format that `version` uses."""
    if version not in BUILDER_VERSIONS:
        raise ValueError(f"the builder cannot write version {version!r}; it writes {BUILDER_VERSIONS!r}")
    if version in V4_VERSIONS:
        return TAD_V4_HEADER.pack(TAD_V4_MARKER, 0, 0, 0), TAD_64BIT_ENTRY
    return TAD_V3_HEADER.pack(0, 0), TAD_64BIT_ENTRY if version in VERSIONS_64BIT else TAD_V3_ENTRY


def write_raw_datafile(
    directory: Path,
    name: str,
    body: bytes,
    tad_entries: Sequence[tuple[int, int]],
    encoding: int = 0,
    version: bytes = ENCRYPTED_V3_VERSION,
) -> None:
    """Write Cro<name>.dat holding `body` after the file header, and Cro<name>.tad with one entry per record.

    Each entry is (offset field, length field), packed as `version` stores them: v3 keeps a record's flags in the
    top byte of the length field, v4 in the top byte of the offset field. The body starts at DAT_PREFIX_SIZE. This
    lets tests lay out inline, extended or corrupt records byte by byte.
    """
    tad_header, tad_entry = tad_layout(version)
    dat = DAT_HEADER.pack(b"CroFile\x00", 0, version, encoding, BLOCKSIZE) + bytes(DAT_HEADER_PADDING)
    tad = tad_header + b"".join(tad_entry.pack(offset, length, 0) for offset, length in tad_entries)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"Cro{name}.dat").write_bytes(dat + body)
    (directory / f"Cro{name}.tad").write_bytes(tad)


def write_header_only_datafile(directory: Path, name: str, version: bytes = b"01.19", encoding: int = 0) -> None:
    """Write Cro<name>.dat holding only a file header, for versions this builder cannot write records for."""
    directory.mkdir(parents=True, exist_ok=True)
    header = DAT_HEADER.pack(b"CroFile\x00", 0, version, encoding, BLOCKSIZE)
    (directory / f"Cro{name}.dat").write_bytes(header)


def write_datafile(
    directory: Path,
    name: str,
    records: Sequence[bytes | None],
    kod: Sequence[int] | None = None,
    version: bytes = ENCRYPTED_V3_VERSION,
    encoded: bool = False,
) -> None:
    """Write Cro<name>.dat and Cro<name>.tad of `version` holding `records` inline, where None marks a deleted record.

    With `kod`, each record is KOD-encoded using its record number as the shift and the encoding bit is set; only
    versions encrypted with their own KOD table take one. With `encoded` and no `kod`, the records are KOD-encoded
    with the default table and the encoding bit is set, as CronosPro stores them in many files of every version.
    Deleted records cannot be written for v4, because how v4 marks them is unsettled.
    """
    tad_layout(version)
    if kod is not None and version not in OWN_KOD_VERSIONS:
        raise ValueError(
            f"version {version!r} is always read with the default KOD, so it cannot be written with another"
        )
    if kod is not None:
        coder = KODcoding(list(kod))
    elif encoded:
        coder = KODcoding(INITIAL_KOD)
    else:
        coder = None
    body = bytearray()
    tad_entries = []
    for recno, plain in enumerate(records, start=1):
        if plain is None:
            if version in V4_VERSIONS:
                raise ValueError("the builder does not write a deleted v4 record: how v4 marks one is unsettled")
            tad_entries.append((0, DELETED_RECORD_LENGTH))
            continue
        stored = coder.encode(recno, plain) if coder else plain
        offset = DAT_PREFIX_SIZE + len(body)
        if version in V4_VERSIONS:
            tad_entries.append((offset | V4_INLINE_RECORD_FLAGS << 56, len(stored)))
        else:
            tad_entries.append((offset, len(stored) | V3_INLINE_BIT))
        body += stored
    write_raw_datafile(directory, name, bytes(body), tad_entries, encoding=1 if coder else 0, version=version)


def stru_records_from_test_db() -> list[bytes | None]:
    """Return the decoded CroStru records of TEST_DB, which define the tables of every built database."""
    with Database(str(TEST_DB), False, KODcoding(INITIAL_KOD)) as db:
        assert db.stru is not None, f"no CroStru file in {TEST_DB}"
        return [db.stru.readrec(recno) for recno in range(1, db.stru.nrofrecords + 1)]


def complex_field(data: bytes) -> bytes:
    """Encode field data as a complex field: 0x1b, a uint32 size, then the data, with no trailing separator."""
    return COMPLEX_FIELD_MARKER + struct.pack("<L", len(data)) + data


def file_reference_field(filename: str, extension: str, file_recno: int | str) -> bytes:
    """Encode a type-6 field that refers to the CroBank record holding a stored file."""
    strings = FIELD_SEPARATOR.join(
        [filename.encode("cp1251"), extension.encode("cp1251"), str(file_recno).encode("cp1251")]
    )
    return complex_field(struct.pack("<LL", 1, len(strings)) + strings)


def file_record(content: bytes) -> bytes:
    """Build a record of the Files table: its table id byte followed by the raw file content."""
    return bytes([FILES_TABLE_ID]) + content


def bank_record(tableid: int, fields: Sequence[bytes]) -> bytes:
    """Build a CroBank record: the table id byte, then each field.

    Plain fields end with a 0x1e separator; fields made with complex_field() carry their own length.
    """
    record = bytearray([tableid])
    for field in fields:
        record += field if field.startswith(COMPLEX_FIELD_MARKER) else field + FIELD_SEPARATOR
    return bytes(record)


def record_with_file_field(file_field: bytes) -> bytes:
    """Build a record of the test table whose fields are empty except for the file reference `file_field`."""
    fields = [b""] * TEST_TABLE_FIELD_COUNT
    fields[TEST_TABLE_FILE_FIELD_INDEX] = file_field
    return bank_record(TEST_TABLE_ID, fields)


def compressed_chunk(compdata: bytes, checksum: int) -> bytes:
    """Encode `compdata` as one chunk of Datafile's compressed record format: size, flag, CRC-32, then the data.

    A compressed record is one or more of these chunks followed by the final marker b"\\x00\\x00\\x02".
    """
    return struct.pack(">HH", 6 + len(compdata), 0x800) + struct.pack("<L", checksum) + compdata


def compressed_record(*payloads: bytes, wrong_checksums: Collection[int] = ()) -> bytes:
    """Compress each of `payloads` into one chunk of Datafile's compressed record format, in order.

    Each chunk holds the CRC-32 of its payload, except those whose index, counted from 0, is in `wrong_checksums`,
    whose CRC-32 is inverted.
    """
    chunks = []
    for index, payload in enumerate(payloads):
        coder = zlib.compressobj(9, zlib.DEFLATED, -15)
        checksum = zlib.crc32(payload) ^ (0xFFFFFFFF if index in wrong_checksums else 0)
        chunks.append(compressed_chunk(coder.compress(payload) + coder.flush(), checksum))
    return b"".join(chunks) + b"\x00\x00\x02"


def corrupt_compressed_record() -> bytes:
    """Return record bytes that pass Datafile's compression check but whose data is not valid deflate output."""
    return compressed_chunk(b"\xff\xff\xff\xff", 0) + b"\x00\x00\x02"


def key_referencing_a_deleted_record(directory: Path, keyname: str, bank_records: Sequence[bytes | None] = ()) -> str:
    """Write a database whose CroStru database definition has an extra key referencing a deleted CroStru record.

    The key is appended after TEST_DB's own database definition keys, referencing a new CroStru record written
    as deleted.
    """
    stru = stru_records_from_test_db()
    dbinfo = stru[0]
    assert dbinfo is not None
    deleted_recno = len(stru) + 1
    name = keyname.encode("cp1251")
    stru[0] = dbinfo + bytes([len(name)]) + name + struct.pack("<L", deleted_recno)
    stru.append(None)
    write_datafile(directory, "Stru", stru)
    write_datafile(directory, "Bank", bank_records)
    return str(directory)


def erdgeist_table_definition() -> bytes:
    """Return the definition bytes of TEST_DB's table "erdgeist", the value of its Base001 key."""
    with Database(str(TEST_DB), False, KODcoding(INITIAL_KOD)) as db:
        return cast(bytes, db.read_db_definition()["Base001"])


def patched_table_definition(*, tableid: int) -> bytes:
    """Return TEST_DB's Base001 definition with its table id replaced."""
    definition = bytearray(erdgeist_table_definition())
    assert struct.unpack_from("<L", definition, TABLE_ID_OFFSET) == (TEST_TABLE_ID,)
    struct.pack_into("<L", definition, TABLE_ID_OFFSET, tableid)
    return bytes(definition)


def files_table_definition() -> bytes:
    """Return the definition bytes of TEST_DB's Files table, the value of its Base000 key."""
    with Database(str(TEST_DB), False, KODcoding(INITIAL_KOD)) as db:
        return cast(bytes, db.read_db_definition()["Base000"])


def renamed_table_definition(
    definition: bytes, *, name: bytes | None = None, abbreviation: bytes | None = None
) -> bytes:
    """Return the table definition `definition` with its name or abbreviation replaced by CP-1251 bytes.

    Both follow the table id, each stored as a length byte and the bytes, so each is at most 255 bytes long.
    """
    name_start = TABLE_ID_OFFSET + 4
    abbreviation_start = name_start + 1 + definition[name_start]
    abbreviation_end = abbreviation_start + 1 + definition[abbreviation_start]
    new_name = definition[name_start:abbreviation_start] if name is None else bytes([len(name)]) + name
    new_abbreviation = (
        definition[abbreviation_start:abbreviation_end]
        if abbreviation is None
        else bytes([len(abbreviation)]) + abbreviation
    )
    return definition[:name_start] + new_name + new_abbreviation + definition[abbreviation_end:]


def field_definition_with_nul_name(definition: bytes, *, field_number: int = 0) -> bytes:
    """Return `definition` with a NUL byte written into the name of the field numbered `field_number`.

    Fields are numbered in file order, in the first section that TableDefinition.decode reads (0 is the first
    one defined, which is usually the system number). A field's name is a length-prefixed CP-1251 string right
    after its type (word) and idx1 (dword); the length is unchanged, so nothing else in `definition` moves.
    """
    header_length = len(TableDefinition(definition, warn=lambda message: None).headerdata)
    reader = ByteReader(definition[header_length:])
    for _ in range(field_number):
        deflen = reader.readword()
        reader.readbytes(deflen)
    name_offset = header_length + reader.o + 2 + 2 + 4 + 1  # deflen, typ (word), idx1 (dword), name length byte
    patched = bytearray(definition)
    patched[name_offset] = 0
    return bytes(patched)


def table_definition_without_fields(*, tableid: int) -> bytes:
    """
    Return a table definition with TEST_DB's Base001 names and `tableid` but no field definitions.

    After the header come an empty first field section, no extra byte strings, a second section marked with a 2
    holding no fields, and the terminator, so it decodes without warnings.
    """
    header = bytearray(patched_table_definition(tableid=tableid)[:FIELD_COUNT_OFFSET])
    empty_sections = struct.pack("<LLL", 0, 0, 0) + b"\x02" + struct.pack("<LLL", 0, 0, 0xFFFFFFFF)
    return bytes(header) + empty_sections


def definition_with_extra_key(dbinfo: bytes, keyname: str, value: bytes) -> bytes:
    """Return the database definition `dbinfo` with the key `keyname` appended, holding `value` inline."""
    name = keyname.encode("cp1251")
    return dbinfo + bytes([len(name)]) + name + struct.pack("<L", len(value) | INLINE_DEFINITION_VALUE) + value


def database_with_extra_definition_key(
    directory: Path, keyname: str, value: bytes, bank_records: Sequence[bytes | None] = ()
) -> str:
    """Write a database whose database definition has an extra key `keyname` holding `value` inline.

    The key is appended after TEST_DB's own keys; a key already there, such as "BankName", becomes a duplicate.
    """
    stru = stru_records_from_test_db()
    dbinfo = stru[0]
    assert dbinfo is not None
    stru[0] = definition_with_extra_key(dbinfo, keyname, value)
    write_datafile(directory, "Stru", stru)
    write_datafile(directory, "Bank", bank_records)
    return str(directory)


def database_with_files_abbreviation(
    directory: Path, abbreviation: bytes, bank_records: Sequence[bytes | None] = ()
) -> str:
    """Write a database whose Files table has the abbreviation `abbreviation`, given in CP-1251.

    TEST_DB's Base000 key is renamed Xase000, which is not a table key, and a Base000 key holding the Files table's
    definition with the new abbreviation is appended.
    """
    stru = stru_records_from_test_db()
    dbinfo = stru[0]
    assert dbinfo is not None
    assert dbinfo.count(b"\x07Base000") == 1
    files_table = renamed_table_definition(files_table_definition(), abbreviation=abbreviation)
    stru[0] = definition_with_extra_key(dbinfo.replace(b"\x07Base000", b"\x07Xase000"), "Base000", files_table)
    write_datafile(directory, "Stru", stru)
    write_datafile(directory, "Bank", bank_records)
    return str(directory)


def duplicate_table_name_database(directory: Path, second_table_name: bytes = b"erdgeist") -> str:
    """Write a database with tables "erdgeist" and `second_table_name`, ids 1 and 2, with records "one" and "two".

    The second table is the first table's definition with its table id and name changed, added to CroStru's
    database definition as an inline Base002 entry.
    """
    fields_one = [b""] * TEST_TABLE_FIELD_COUNT
    fields_one[1] = b"one"
    fields_two = [b""] * TEST_TABLE_FIELD_COUNT
    fields_two[1] = b"two"
    second = renamed_table_definition(patched_table_definition(tableid=2), name=second_table_name)
    return database_with_extra_definition_key(
        directory, "Base002", second, [bank_record(TEST_TABLE_ID, fields_one), bank_record(2, fields_two)]
    )


def database_without_files_table(directory: Path, bank_records: Sequence[bytes | None] = ()) -> str:
    """Write a database whose database definition names its Files table Xase000, so it has no Base000 key."""
    stru = stru_records_from_test_db()
    dbinfo = stru[0]
    assert dbinfo is not None
    assert dbinfo.count(b"\x07Base000") == 1
    stru[0] = dbinfo.replace(b"\x07Base000", b"\x07Xase000")
    write_datafile(directory, "Stru", stru)
    write_datafile(directory, "Bank", bank_records)
    return str(directory)


def write_database(
    directory: Path,
    bank_records: Sequence[bytes | None],
    kod: Sequence[int] | None = None,
    *,
    extra_stru_records: Sequence[bytes] = (),
    index_records: Sequence[bytes | None] | None = None,
    version: bytes = ENCRYPTED_V3_VERSION,
    encoded: bool = False,
) -> str:
    """Write a database of `version` with TEST_DB's table definitions and `bank_records`, returning its directory path.

    `extra_stru_records` are appended to the CroStru records; `index_records`, when given, are written to CroIndex.
    """
    write_datafile(directory, "Stru", [*stru_records_from_test_db(), *extra_stru_records], kod, version, encoded)
    write_datafile(directory, "Bank", bank_records, kod, version, encoded)
    if index_records is not None:
        write_datafile(directory, "Index", index_records, kod, version, encoded)
    return str(directory)


def database_with_missing_definition(directory: Path, stru_records: Sequence[bytes | None]) -> str:
    """Write a database whose CroStru holds `stru_records` in place of TEST_DB's own, and an empty CroBank.

    Used to build databases whose CroStru record 1 (the database definition) is deleted or absent: pass
    `[None, *stru_records_from_test_db()[1:]]` for a deleted record 1, or `[]` for no records at all.
    """
    write_datafile(directory, "Stru", stru_records)
    write_datafile(directory, "Bank", [])
    return str(directory)


def database_with_wrong_kod_record_out_of_range(directory: Path) -> tuple[str, str]:
    """Write a database encrypted with `random_kod(seed=1)` and return it with a wrong KOD table's hex digits.

    The wrong KOD, `random_kod(seed=2622)`, decodes CroStru record 1 into a database definition whose one key
    has a garbage record number that CroStru doesn't hold; 2622 is the smallest seed found whose garbage record
    1 starts with 0x03 (so dump_db_table_defs/enumerate_tables print no "WARN: expected dbinfo" line) and whose
    garbage key name holds no line-break characters (so the error is a single stderr line).
    """
    dbdir = write_database(directory, [], kod=random_kod(seed=1))
    wrong_kod_hex = bytes(random_kod(seed=2622)).hex()
    return dbdir, wrong_kod_hex


def crackable_database(directory: Path, bank_records: Sequence[bytes | None], kod: Sequence[int]) -> str:
    """Write a database encrypted with `kod` that holds enough known zero bytes for strucrack and dbcrack.

    strucrack counts, for every shift, which encrypted byte is most common in CroStru, so all-zero records give
    every shift the right answer. dbcrack reads the fourth byte of CroBank and CroIndex records longer than
    11 bytes, which decodes to zero, so 300 such records cover every shift in both files.
    """
    zero_byte_records = [bytes([UNUSED_TABLE_ID]) + bytes(11)] * 300
    return write_database(
        directory,
        [*bank_records, *zero_byte_records],
        kod,
        extra_stru_records=[bytes(256)] * 8,
        index_records=zero_byte_records,
    )
