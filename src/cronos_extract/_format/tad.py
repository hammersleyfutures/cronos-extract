# ABOUTME: The layout of a Cro*.tad index for each CronosPro generation: its header and its entries.
# ABOUTME: A TadLayout turns a raw entry into a TadEntry: where a record is, how long, and whether inline or deleted.
import struct
from dataclasses import dataclass
from typing import Literal

from .header import V3_VERSIONS, V4_VERSIONS, VERSIONS_64BIT

# The length field of a deleted record's entry.
DELETED_LENGTH = 0xFFFFFFFF
# A v3 entry keeps its inline flag in bit 31 of the length field and the length in bits 0-30.
V3_INLINE_BIT = 1 << 31
# The flag byte of an inline v3 entry: the top byte of its length field, which holds only bit 31.
V3_INLINE_FLAGS = 0x80
# A v4 entry keeps its flags in the top byte of the offset field. The research notes say 04 marks data (compressed
# v3-style), 02 and 03 a deleted record and 00 an extended record; 3d checks 02 and 03 against real databases.
V4_FLAG_SHIFT = 56
V3_HEADER = struct.Struct("<2L")
V4_HEADER = struct.Struct("<4L")
# 01.03, 01.05 and 01.11 have 64-bit file offsets; 01.02 and 01.04 have 32-bit ones.
ENTRY_64BIT = struct.Struct("<QLL")
ENTRY_32BIT = struct.Struct("<LLL")


@dataclass(frozen=True)
class TadEntry:
    """
    One entry of a .tad index: where a record's data starts in the .dat file, how many bytes it has, and how it is
    stored.

    `flags` is the entry's flag byte. An `inline` record is stored whole at `offset`; any other starts with an
    extended-record header and continues in extension blocks. A `deleted` entry keeps its raw fields.
    """

    offset: int
    length: int
    flags: int
    checksum: int
    inline: bool
    deleted: bool


@dataclass(frozen=True)
class TadLayout:
    """How one generation lays out its .tad header and entries."""

    header: struct.Struct
    entry: struct.Struct
    generation: Literal["v3", "v4"]

    def deleted_counts(self, data: bytes) -> tuple[int, int]:
        """The number of deleted records and the offset of the first deleted entry, from the .tad header `data`."""
        fields = self.header.unpack(data)
        if self.generation == "v3":
            return int(fields[0]), int(fields[1])
        return int(fields[1]), int(fields[2])

    def parse(self, data: bytes) -> TadEntry:
        """The entry that the raw .tad entry `data` describes."""
        offset, length, checksum = self.entry.unpack(data)
        if length == DELETED_LENGTH:
            return TadEntry(offset, length, 0, checksum, inline=False, deleted=True)
        if self.generation == "v3":
            inline = bool(length & V3_INLINE_BIT)
            flags = V3_INLINE_FLAGS if inline else 0
            return TadEntry(offset, length & ~V3_INLINE_BIT, flags, checksum, inline=inline, deleted=False)
        flags = offset >> V4_FLAG_SHIFT
        offset &= (1 << V4_FLAG_SHIFT) - 1
        return TadEntry(offset, length, flags, checksum, inline=flags != 0, deleted=False)


def tad_layout(version: bytes) -> TadLayout | None:
    """The .tad layout of files of `version`, or None for a version whose .tad this release cannot read."""
    entry = ENTRY_64BIT if version in VERSIONS_64BIT else ENTRY_32BIT
    if version in V3_VERSIONS:
        return TadLayout(V3_HEADER, entry, "v3")
    if version in V4_VERSIONS:
        return TadLayout(V4_HEADER, entry, "v4")
    return None
