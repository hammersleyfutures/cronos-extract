# ABOUTME: Tests for cronos_extract.readers.ByteReader, the sequential decoder used by every structure reader.
# ABOUTME: Covers CP-1251 decoding of names and strings, including bytes undefined in that encoding.
import pytest

from cronos_extract.readers import ByteReader


def test_readname_decodes_cp1251_bytes() -> None:
    data = bytes([8]) + "erdgeist".encode("cp1251")

    assert ByteReader(data).readname() == "erdgeist"


def test_readname_replaces_a_byte_undefined_in_cp1251() -> None:
    data = bytes([2, 0x98, 0x41])

    assert ByteReader(data).readname() == "�A"


def test_readlongstring_decodes_cp1251_bytes() -> None:
    data = (4).to_bytes(4, "little") + "test".encode("cp1251")

    assert ByteReader(data).readlongstring() == "test"


def test_readlongstring_replaces_a_byte_undefined_in_cp1251() -> None:
    data = (2).to_bytes(4, "little") + bytes([0x98, 0x41])

    assert ByteReader(data).readlongstring() == "�A"


def test_readname_raises_eoferror_past_the_end_of_the_buffer() -> None:
    with pytest.raises(EOFError):
        ByteReader(bytes([5]) + b"ab").readname()
