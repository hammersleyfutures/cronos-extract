# ABOUTME: Builds CronosPro v3 database directories for tests, optionally encrypted with a chosen KOD table.
# ABOUTME: Record layouts follow docs/cronos-research.md as the reader parses them, so tests can craft any database.
import random
import struct
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

DAT_HEADER = struct.Struct("<8sH5sHH")
DAT_HEADER_PADDING = 0xE9
TAD_V3_HEADER = struct.Struct("<2L")
TAD_V3_ENTRY = struct.Struct("<LLL")
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


def write_datafile(
    directory: Path, name: str, records: Sequence[bytes | None], kod: Sequence[int] | None = None
) -> None:
    """Write Cro<name>.dat and Cro<name>.tad holding `records`, where None marks a deleted record.

    With `kod`, each record is KOD-encoded using its record number as the shift and the encoding bit is set.
    """
    coder = KODcoding(list(kod)) if kod is not None else None
    encoding = 1 if coder else 0
    dat = bytearray(DAT_HEADER.pack(b"CroFile\x00", 0, ENCRYPTED_V3_VERSION, encoding, 0x40))
    dat += bytes(DAT_HEADER_PADDING)
    tad = bytearray(TAD_V3_HEADER.pack(0, 0))
    for recno, plain in enumerate(records, start=1):
        if plain is None:
            tad += TAD_V3_ENTRY.pack(0, DELETED_RECORD_LENGTH, 0)
            continue
        stored = coder.encode(recno, plain) if coder else plain
        tad += TAD_V3_ENTRY.pack(len(dat), len(stored) | INLINE_RECORD_FLAGS << 24, 0)
        dat += stored
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"Cro{name}.dat").write_bytes(dat)
    (directory / f"Cro{name}.tad").write_bytes(tad)


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


def write_database(directory: Path, bank_records: Sequence[bytes | None], kod: Sequence[int] | None = None) -> str:
    """Write a database with TEST_DB's table definitions and `bank_records`, returning its directory path."""
    write_datafile(directory, "Stru", stru_records_from_test_db(), kod)
    write_datafile(directory, "Bank", bank_records, kod)
    return str(directory)
