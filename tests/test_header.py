# ABOUTME: Tests for cronos_extract._format.header, which parses the 19-byte Cro*.dat file header.
# ABOUTME: Builds headers as raw bytes, including versions this package cannot otherwise produce.
import io
import struct

import pytest

from cronos_extract._format.header import DatHeader, read_dat_header

DAT_HEADER = struct.Struct("<8sH5sHH")


def header_bytes(version: bytes = b"01.04", encoding: int = 1, blocksize: int = 0x40) -> bytes:
    return DAT_HEADER.pack(b"CroFile\x00", 0, version, encoding, blocksize)


def test_read_dat_header_decodes_the_fields() -> None:
    header = read_dat_header(io.BytesIO(header_bytes()), where="CroBank.dat")

    assert header == DatHeader(version=b"01.04", unknown=0, encoding=1, blocksize=0x40)
    assert header.version_text == "01.04"
    assert header.generation == "v3"
    assert header.use64bit is False
    assert header.kod_encoded is True
    assert header.compressed is False
    assert header.own_kod is True


def test_read_dat_header_describes_every_known_generation() -> None:
    generations = {
        b"01.02": ("v3", False),
        b"01.03": ("v3", True),
        b"01.05": ("v3", True),
        b"01.11": ("v4", True),
        b"01.13": ("v4", False),
        b"01.14": ("v4", False),
        b"01.19": ("v7", False),
        b"09.99": ("unknown", False),
    }
    for version, (generation, use64bit) in generations.items():
        header = read_dat_header(io.BytesIO(header_bytes(version=version)), where="CroStru.dat")
        assert (header.generation, header.use64bit) == (generation, use64bit), version


def test_read_dat_header_reports_a_compressed_file() -> None:
    header = read_dat_header(io.BytesIO(header_bytes(encoding=3)), where="CroBank.dat")

    assert (header.kod_encoded, header.compressed) == (True, True)


def test_read_dat_header_rejects_another_file_format() -> None:
    with pytest.raises(ValueError, match=r"CroStru\.dat is not a Cronos file: unknown magic b'NotACron'"):
        read_dat_header(io.BytesIO(b"NotACronosFile" + bytes(20)), where="CroStru.dat")


def test_read_dat_header_rejects_a_file_shorter_than_the_header() -> None:
    with pytest.raises(ValueError, match=r"CroStru\.dat is shorter than its 19-byte header"):
        read_dat_header(io.BytesIO(b"CroFile\x00" + bytes(5)), where="CroStru.dat")


def test_version_text_replaces_bytes_that_are_not_ascii() -> None:
    header = read_dat_header(io.BytesIO(header_bytes(version=b"\xff\xfe.04")), where="CroBank.dat")

    assert header.version_text == "��.04"
    assert header.generation == "unknown"
