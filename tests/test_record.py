# ABOUTME: Tests for decoding one record: extension blocks, KOD decoding, CRC checking and the decompression limit.
# ABOUTME: Records are built as bytes and read through a RecordSource over those bytes.
import struct
import tracemalloc
import zlib

import pytest
from cronos_builder import compressed_record, corrupt_compressed_record, random_kod

from cronos_extract._format.record import (
    MAX_DECOMPRESSED_BYTES,
    RecordParts,
    RecordSource,
    decode_record,
    decompress,
    is_compressed,
    read_stored,
)
from cronos_extract._format.tad import TadEntry
from cronos_extract.koddecoder import KODcoding


def source_of(data: bytes, *, blocksize: int = 16, kod: KODcoding | None = None) -> RecordSource:
    """A 32-bit RecordSource reading `data` as the .dat file of CroBank."""
    return RecordSource("Bank", lambda offset, size: data[offset : offset + size], len(data), blocksize, False, kod)


def inline(offset: int, length: int) -> TadEntry:
    return TadEntry(offset, length, 0x80, 0, True, False)


def extended(offset: int, length: int) -> TadEntry:
    return TadEntry(offset, length, 0, 0, False, False)


def test_an_inline_record_is_its_bytes() -> None:
    assert decode_record(source_of(b"xxhelloyy"), 1, inline(2, 5)) == RecordParts(b"hello", 0x80)


def test_a_record_is_kod_decoded_with_its_record_number_as_shift() -> None:
    kod = KODcoding(random_kod(seed=1))
    stored = kod.encode(3, b"hello")

    assert decode_record(source_of(stored, kod=kod), 3, inline(0, 5)).data == b"hello"


def test_a_compressed_record_is_decompressed_and_its_crc_checked() -> None:
    record = compressed_record(b"one", b"two", b"three")

    parts = decode_record(source_of(record), 1, inline(0, len(record)))

    assert (parts.data, parts.compressed, parts.mismatched_chunks) == (b"onetwothree", True, ())


def test_a_crc_mismatch_keeps_the_data_and_names_the_chunk() -> None:
    record = compressed_record(b"one", b"two", b"three", wrong_checksums={1})

    parts = decode_record(source_of(record), 1, inline(0, len(record)))

    assert (parts.data, parts.mismatched_chunks) == (b"onetwothree", (1,))


def test_a_record_in_extension_blocks_is_reassembled() -> None:
    first = struct.pack("<LL", 100, 20) + b"01234567"
    block = struct.pack("<L", 200) + b"89abcdefghij"
    data = first + bytes(100 - len(first)) + block

    parts = decode_record(source_of(data), 1, extended(0, len(first)))

    assert parts == RecordParts(b"0123456789abcdefghij", 0, extended=True, chain=(100, 200), length=20)


def test_a_records_last_extension_block_may_point_back_to_an_earlier_offset() -> None:
    first = struct.pack("<LL", 100, 32) + b"01234567"
    block_at_100 = struct.pack("<L", 116) + b"89abcdefghij"
    block_at_116 = struct.pack("<L", 100) + b"KLMNOPQRSTUV"
    data = first + bytes(100 - len(first)) + block_at_100 + block_at_116

    parts = decode_record(source_of(data), 1, extended(0, len(first)))

    assert parts == RecordParts(b"0123456789abcdefghijKLMNOPQRSTUV", 0, extended=True, chain=(100, 116, 100), length=32)


def test_a_records_last_extension_block_may_point_at_itself() -> None:
    first = struct.pack("<LL", 100, 20) + b"01234567"
    block = struct.pack("<L", 100) + b"89abcdefghij"
    data = first + bytes(100 - len(first)) + block

    parts = decode_record(source_of(data), 1, extended(0, len(first)))

    assert parts == RecordParts(b"0123456789abcdefghij", 0, extended=True, chain=(100, 100), length=20)


def test_a_record_the_file_cuts_short_is_reassembled_as_far_as_it_goes_without_require_whole() -> None:
    data = b"1234"
    entry = extended(0, 9)

    with pytest.raises(ValueError, match="is shorter than its 8-byte extended record header"):
        read_stored(source_of(data), 1, entry, require_whole=False)

    with pytest.raises(ValueError, match="which runs past the end of the file"):
        read_stored(source_of(data), 1, entry, require_whole=True)


@pytest.mark.parametrize(
    ("data", "entry", "message"),
    [
        (b"short", inline(0, 9), "record 1 in CroBank.dat has 9 bytes at offset 0x0, which runs past the end"),
        (b"1234", extended(0, 4), "record 1 in CroBank.dat is shorter than its 8-byte extended record header"),
        (struct.pack("<LL", 0, 999), extended(0, 8), "record 1 in CroBank.dat claims 999 bytes"),
        (struct.pack("<LL", 8, 40) + struct.pack("<L", 8) + bytes(12) + bytes(40), extended(0, 8), "has a loop"),
        (struct.pack("<LL", 900, 40) + bytes(40), extended(0, 8), "has an extension block past the end"),
        (corrupt_compressed_record(), None, "corrupt compressed data: "),
    ],
    ids=["past-the-end", "short-header", "longer-than-file", "loop", "block-past-end", "corrupt-deflate"],
)
def test_a_record_that_cannot_be_decoded_is_a_value_error(data: bytes, entry: TadEntry | None, message: str) -> None:
    with pytest.raises(ValueError, match=message.replace("(", r"\(")):
        decode_record(source_of(data), 1, entry or inline(0, len(data)))


def test_a_chunk_whose_header_is_cut_off_is_kept_as_a_mismatch() -> None:
    hello = compressed_record(b"hello")[: -len(b"\x00\x00\x02")]
    data = hello + b"\x00\x04\x08\x00\x00\x02"
    assert is_compressed(data)

    result, mismatched = decompress(data, "record 1 in CroBank.dat")

    assert (result, mismatched) == (b"hello", (1,))


def test_a_record_that_decompresses_past_the_limit_is_refused_without_holding_it() -> None:
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    chunk_payload = bytes(32 * 1024 * 1024)
    compdata = compressor.compress(chunk_payload) + compressor.flush()
    assert len(compdata) <= 0xFFFF - 6
    chunk = struct.pack(">HH", 6 + len(compdata), 0x800) + struct.pack("<L", zlib.crc32(chunk_payload)) + compdata
    del chunk_payload
    bomb = chunk * 40 + b"\x00\x00\x02"

    tracemalloc.start()
    try:
        with pytest.raises(ValueError, match=f"more than {MAX_DECOMPRESSED_BYTES} bytes"):
            decompress(bomb, "record 1 in CroBank.dat")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    # Forty chunks would decompress to 1.25 GiB; stopping at the limit keeps the peak far below that.
    assert peak < 3 * MAX_DECOMPRESSED_BYTES
