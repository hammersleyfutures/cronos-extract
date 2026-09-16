# ABOUTME: Builds CronosPro v3 database directories for tests, optionally encrypted with a chosen KOD table.
# ABOUTME: Record layouts follow docs/cronos-research.md as the reader parses them, so tests can craft any database.
import random
import struct
import zlib
from collections.abc import Sequence
from pathlib import Path

from cronos_extract.Database import Database
from cronos_extract.koddecoder import INITIAL_KOD, KODcoding

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
TAD_V3_ENTRY = struct.Struct("<LLL")
BLOCKSIZE = 0x40
# Size of the .dat file header and the padding that follows it; the first record starts here.
DAT_PREFIX_SIZE = DAT_HEADER.size + DAT_HEADER_PADDING
# Version 01.04 is a 32-bit v3 file whose records are decoded with the database's own KOD table.
ENCRYPTED_V3_VERSION = b"01.04"
# A non-zero flag byte in the top of a v3 .tad length marks a record stored inline, not in extension blocks.
INLINE_RECORD_FLAGS = 0x80
DELETED_RECORD_LENGTH = 0xFFFFFFFF
FIELD_SEPARATOR = b"\x1e"
COMPLEX_FIELD_MARKER = b"\x1b"


def random_kod(seed: int) -> list[int]:
    """Return a reproducible random permutation of 0..255 to use as a database's KOD table."""
    kod = list(range(256))
    random.Random(seed).shuffle(kod)
    return kod


def write_raw_datafile(
    directory: Path, name: str, body: bytes, tad_entries: Sequence[tuple[int, int]], encoding: int = 0
) -> None:
    """Write Cro<name>.dat holding `body` after the file header, and Cro<name>.tad with one entry per record.

    Each entry is (absolute file offset, length field); the body starts at DAT_PREFIX_SIZE. This lets tests lay
    out inline, extended or corrupt records byte by byte.
    """
    dat = DAT_HEADER.pack(b"CroFile\x00", 0, ENCRYPTED_V3_VERSION, encoding, BLOCKSIZE) + bytes(DAT_HEADER_PADDING)
    tad = TAD_V3_HEADER.pack(0, 0) + b"".join(TAD_V3_ENTRY.pack(offset, length, 0) for offset, length in tad_entries)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"Cro{name}.dat").write_bytes(dat + body)
    (directory / f"Cro{name}.tad").write_bytes(tad)


def write_header_only_datafile(directory: Path, name: str, version: bytes = b"01.19", encoding: int = 0) -> None:
    """Write Cro<name>.dat holding only a file header, for versions this builder cannot write records for."""
    directory.mkdir(parents=True, exist_ok=True)
    header = DAT_HEADER.pack(b"CroFile\x00", 0, version, encoding, BLOCKSIZE)
    (directory / f"Cro{name}.dat").write_bytes(header)


def write_datafile(
    directory: Path, name: str, records: Sequence[bytes | None], kod: Sequence[int] | None = None
) -> None:
    """Write Cro<name>.dat and Cro<name>.tad holding `records` inline, where None marks a deleted record.

    With `kod`, each record is KOD-encoded using its record number as the shift and the encoding bit is set.
    """
    coder = KODcoding(list(kod)) if kod is not None else None
    body = bytearray()
    tad_entries = []
    for recno, plain in enumerate(records, start=1):
        if plain is None:
            tad_entries.append((0, DELETED_RECORD_LENGTH))
            continue
        stored = coder.encode(recno, plain) if coder else plain
        tad_entries.append((DAT_PREFIX_SIZE + len(body), len(stored) | INLINE_RECORD_FLAGS << 24))
        body += stored
    write_raw_datafile(directory, name, bytes(body), tad_entries, encoding=1 if coder else 0)


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


def compressed_chunk(compdata: bytes) -> bytes:
    """Encode `compdata` as one chunk of Datafile's compressed record format: size, flag, crc, then the data.

    A compressed record is one or more of these chunks followed by the final marker b"\\x00\\x00\\x02".
    """
    return struct.pack(">HH", 6 + len(compdata), 0x800) + struct.pack("<L", 0) + compdata


def compressed_record(payload: bytes) -> bytes:
    """Compress `payload` into Datafile's compressed record format, as a single chunk."""
    coder = zlib.compressobj(9, zlib.DEFLATED, -15)
    return compressed_chunk(coder.compress(payload) + coder.flush()) + b"\x00\x00\x02"


def corrupt_compressed_record() -> bytes:
    """Return record bytes that pass Datafile.iscompressed() but whose data is not valid deflate output."""
    return compressed_chunk(b"\xff\xff\xff\xff") + b"\x00\x00\x02"


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


def write_database(
    directory: Path,
    bank_records: Sequence[bytes | None],
    kod: Sequence[int] | None = None,
    *,
    extra_stru_records: Sequence[bytes] = (),
    index_records: Sequence[bytes | None] | None = None,
) -> str:
    """Write a database with TEST_DB's table definitions and `bank_records`, returning its directory path.

    `extra_stru_records` are appended to the CroStru records; `index_records`, when given, are written to CroIndex.
    """
    write_datafile(directory, "Stru", [*stru_records_from_test_db(), *extra_stru_records], kod)
    write_datafile(directory, "Bank", bank_records, kod)
    if index_records is not None:
        write_datafile(directory, "Index", index_records, kod)
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
