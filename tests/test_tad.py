# ABOUTME: Tests for the .tad layouts: where each generation keeps a record's offset, length and flags.
# ABOUTME: Entries are built as bytes, as CronosPro writes them.
import struct

import pytest

from cronos_extract._format.tad import DELETED_LENGTH, V3_INLINE_BIT, TadEntry, tad_layout

V3_32 = struct.Struct("<LLL")
ENTRY_64 = struct.Struct("<QLL")


@pytest.mark.parametrize(
    ("version", "header_size", "entry_size"),
    [(b"01.02", 8, 12), (b"01.03", 8, 16), (b"01.04", 8, 12), (b"01.05", 8, 16), (b"01.11", 16, 16)],
)
def test_each_version_has_its_header_and_entry_size(version: bytes, header_size: int, entry_size: int) -> None:
    layout = tad_layout(version)

    assert layout is not None
    assert (layout.header.size, layout.entry.size) == (header_size, entry_size)


@pytest.mark.parametrize("version", [b"01.19", b"99.99"])
def test_a_version_this_release_cannot_read_has_no_layout(version: bytes) -> None:
    assert tad_layout(version) is None


def test_a_v3_inline_entry_has_its_flag_in_bit_31() -> None:
    layout = tad_layout(b"01.02")
    assert layout is not None

    assert layout.parse(V3_32.pack(0x100, 5 | V3_INLINE_BIT, 7)) == TadEntry(0x100, 5, 0x80, 7, True, False)


def test_a_v3_entry_without_bit_31_is_extended() -> None:
    layout = tad_layout(b"01.02")
    assert layout is not None

    assert layout.parse(V3_32.pack(0x100, 20, 0)) == TadEntry(0x100, 20, 0, 0, False, False)


def test_bits_24_to_30_of_a_v3_length_are_length() -> None:
    layout = tad_layout(b"01.03")
    assert layout is not None

    entry = layout.parse(ENTRY_64.pack(0x100, 0x7F000001 | V3_INLINE_BIT, 0))

    assert (entry.length, entry.inline) == (0x7F000001, True)


def test_a_v4_entry_keeps_its_flags_in_the_top_byte_of_the_offset() -> None:
    layout = tad_layout(b"01.11")
    assert layout is not None

    assert layout.parse(ENTRY_64.pack(0x04 << 56 | 0x100, 9, 3)) == TadEntry(0x100, 9, 0x04, 3, True, False)
    assert layout.parse(ENTRY_64.pack(0x100, 9, 3)) == TadEntry(0x100, 9, 0, 3, False, False)


@pytest.mark.parametrize(("version", "entry"), [(b"01.02", V3_32), (b"01.11", ENTRY_64)])
def test_a_deleted_entry_keeps_its_raw_fields(version: bytes, entry: struct.Struct) -> None:
    layout = tad_layout(version)
    assert layout is not None

    parsed = layout.parse(entry.pack(0x1234, DELETED_LENGTH, 0x55))

    assert parsed == TadEntry(0x1234, DELETED_LENGTH, 0, 0x55, False, True)


def test_the_header_gives_the_deleted_record_counts() -> None:
    v3, v4 = tad_layout(b"01.02"), tad_layout(b"01.11")
    assert v3 is not None and v4 is not None

    assert v3.deleted_counts(struct.pack("<2L", 3, 40)) == (3, 40)
    assert v4.deleted_counts(struct.pack("<4L", 0xFFFFFFFE, 3, 40, 0)) == (3, 40)
