# ABOUTME: Decodes one record of a Cro*.dat file: reassembles extension blocks, KOD-decodes, checks and decompresses.
# ABOUTME: Every reader of records goes through decode_record; a record may decompress to at most 256 MiB.
import struct
import zlib
from collections.abc import Callable
from dataclasses import dataclass, replace

from ..koddecoder import KODcoding
from .tad import TadEntry

# The most bytes a record may decompress to; a crafted record could otherwise exhaust memory.
MAX_DECOMPRESSED_BYTES = 256 * 1024 * 1024
# A compressed record ends with a chunk of size 0 followed by 2.
COMPRESSED_END = b"\x00\x00\x02"
# Each chunk starts with a big-endian size (of flag, CRC and data) and flag, then a little-endian CRC-32 of the
# chunk's decompressed data.
CHUNK_HEADER = struct.Struct(">HH")
CHUNK_CRC = struct.Struct("<L")
CHUNK_PREFIX_SIZE = CHUNK_HEADER.size + CHUNK_CRC.size


@dataclass(frozen=True)
class RecordSource:
    """What decoding a record needs from a .dat file: its name, a way to read it, its size and layout, and its KOD."""

    name: str
    read: Callable[[int, int], bytes]
    size: int
    blocksize: int
    use64bit: bool
    kod: KODcoding | None

    @property
    def filename(self) -> str:
        return f"Cro{self.name}.dat"


@dataclass(frozen=True)
class RecordParts:
    """
    A record as decoding found it.

    `data` is the decoded record, decompressed when `compressed`. `flags` is its .tad entry's flag byte. For an
    `extended` record, `chain` holds the first block's offset from the record header, then the next-block offset
    read from each block, `length` is the length the header gives, and `tail` holds the bytes read past the record's
    end. `mismatched_chunks` lists the compressed chunks, counted from 0, whose CRC-32 does not match their data.
    """

    data: bytes
    flags: int
    extended: bool = False
    chain: tuple[int, ...] = ()
    length: int = 0
    tail: bytes = b""
    compressed: bool = False
    mismatched_chunks: tuple[int, ...] = ()


def read_stored(source: RecordSource, recno: int, entry: TadEntry, *, require_whole: bool = True) -> RecordParts:
    """
    Record `recno` as stored: its bytes, reassembled from extension blocks and KOD-decoded, not decompressed.

    Raises ValueError naming the record when it cannot be read; with `require_whole` false, a record the file cuts
    short is returned or reassembled as far as it goes, as inspect crodump shows it.
    """
    where = f"record {recno} in {source.filename}"
    data = source.read(entry.offset, entry.length)
    if len(data) < entry.length and require_whole:
        raise ValueError(
            f"{where} has {entry.length} bytes at offset {entry.offset:#x}, which runs past the end of the file"
        )
    # An empty record is returned as it is: there is nothing to reassemble from extension blocks.
    parts = RecordParts(data, entry.flags)
    if data and not entry.inline:
        parts = read_extended(source, where, data, entry.flags)
    if source.kod is not None:
        parts = replace(parts, data=source.kod.decode(recno, parts.data))
    return parts


def read_extended(source: RecordSource, where: str, first: bytes, flags: int) -> RecordParts:
    """
    Reassemble a record from extension blocks, given `first`, the record's first block.

    The first block holds the offset of the first extension block, the record length, then data; each
    extension block starts with the offset of the next one. Raises ValueError when the header is truncated,
    the length exceeds the file, the blocks loop, or a block lies past the end of the file.
    """
    headersize, pointersize, pointerformat = (12, 8, "<Q") if source.use64bit else (8, 4, "<L")
    if len(first) < headersize:
        raise ValueError(f"{where} is shorter than its {headersize}-byte extended record header")
    extofs, extlen = struct.unpack("<QL" if source.use64bit else "<LL", first[:headersize])
    if extlen > source.size:
        raise ValueError(f"{where} claims {extlen} bytes, more than the file holds")

    data = bytearray(first[headersize:])
    chain = [extofs]
    seen: set[int] = set()
    while len(data) < extlen:
        if extofs in seen:
            raise ValueError(f"{where} has a loop in its extension blocks at offset {extofs:#x}")
        seen.add(extofs)
        block = source.read(extofs, source.blocksize)
        if len(block) <= pointersize:
            raise ValueError(f"{where} has an extension block past the end of the file at offset {extofs:#x}")
        (extofs,) = struct.unpack(pointerformat, block[:pointersize])
        chain.append(extofs)
        data += block[pointersize:]
    return RecordParts(
        bytes(data[:extlen]), flags, extended=True, chain=tuple(chain), length=extlen, tail=bytes(data[extlen:])
    )


def is_compressed(data: bytes) -> bool:
    """
    Check if this record looks like a compressed record.
    """
    if len(data) < 11:
        return False
    if data[-3:] != b"\x00\x00\x02":
        return False
    o = 0
    while o < len(data) - 3:
        size, flag = struct.unpack_from(">HH", data, o)
        if flag != 0x800 and flag != 0x008:
            return False
        o += size + 2
    return True


def decompress(data: bytes, where: str) -> tuple[bytes, tuple[int, ...]]:
    """
    Decompress a record, returning its data and the chunks, counted from 0, whose CRC-32 does not match.

    Compressed records can have several chunks of compressed data.
    Note that the compression header uses a mix of big-endian and little numbers.

    each chunk has the following format:
        size  - big endian uint16, size of flag + crc + compdata
        flag  - big endian uint16 - always 0x800
        crc   - little endian uint32, crc32 of the decompressed data
    the final chunk has only 3 bytes: a zero size followed by a 2.

    the crc algorithm is the one labeled 'crc-32' on this page:
        http://crcmod.sourceforge.net/crcmod.predefined.html

    Raises ValueError when the data is not valid deflate output, or ValueError naming `where` when the record would
    decompress to more than MAX_DECOMPRESSED_BYTES; decompression stops at that limit. A chunk whose 8-byte header
    (size, flag and CRC) runs past the end of the data is not decompressed and is counted as a mismatched chunk.
    """
    result = bytearray()
    mismatched = []
    offset = 0
    chunk = 0
    while offset < len(data) - len(COMPRESSED_END):
        if offset + CHUNK_PREFIX_SIZE > len(data):
            mismatched.append(chunk)
            # is_compressed walks the same offsets, so decode_record and dump never reach fewer than 4 header
            # bytes here; this guards a caller that calls decompress directly, without is_compressed first.
            if offset + CHUNK_HEADER.size > len(data):
                break
            size, _ = CHUNK_HEADER.unpack_from(data, offset)
            chunk += 1
            offset += size + 2
            continue
        # note the mix of bigendian and little endian numbers here.
        size, _ = CHUNK_HEADER.unpack_from(data, offset)
        (crc,) = CHUNK_CRC.unpack_from(data, offset + CHUNK_HEADER.size)
        room = MAX_DECOMPRESSED_BYTES - len(result)
        try:
            out = zlib.decompressobj(-15).decompress(data[offset + CHUNK_PREFIX_SIZE : offset + 2 + size], room + 1)
        except zlib.error as e:
            raise ValueError(f"corrupt compressed data: {e}") from e
        if len(out) > room:
            raise ValueError(
                f"{where} decompresses to more than {MAX_DECOMPRESSED_BYTES} bytes, the most a record may hold"
            )
        if zlib.crc32(out) != crc:
            mismatched.append(chunk)
        result += out
        chunk += 1
        offset += size + 2
    return bytes(result), tuple(mismatched)


def decode_record(source: RecordSource, recno: int, entry: TadEntry) -> RecordParts:
    """Record `recno`, whose .tad entry is `entry`, read, reassembled, KOD-decoded, checked and decompressed."""
    parts = read_stored(source, recno, entry)
    if not is_compressed(parts.data):
        return parts
    data, mismatched = decompress(parts.data, f"record {recno} in {source.filename}")
    return replace(parts, data=data, compressed=True, mismatched_chunks=mismatched)
