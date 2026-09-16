# ABOUTME: Tests for cronos_extract.Datafile reading records stored in extension blocks, including corrupt ones.
# ABOUTME: Lays out .dat and .tad files byte by byte with tests/cronos_builder.write_raw_datafile.
import struct
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import pytest
from cli import run_command
from cronos_builder import (
    BLOCKSIZE,
    DAT_PREFIX_SIZE,
    INLINE_RECORD_FLAGS,
    corrupt_compressed_record,
    write_datafile,
    write_raw_datafile,
)

from cronos_extract.Datafile import Datafile

FIRST_BLOCK = DAT_PREFIX_SIZE


def extended_header(first_extension_offset: int, length: int) -> bytes:
    return struct.pack("<LL", first_extension_offset, length)


def extension_block(next_offset: int, payload: bytes) -> bytes:
    return (struct.pack("<L", next_offset) + payload).ljust(BLOCKSIZE, b"\x00")


def write_bank_with_extended_record(
    directory: Path, first_block: bytes, extension_blocks: Sequence[tuple[int, bytes]] = ()
) -> None:
    """Write a CroBank whose only record is the extended record `first_block`, plus (offset, block) extensions."""
    body = bytearray(first_block)
    for offset, block in extension_blocks:
        start = offset - DAT_PREFIX_SIZE
        body.extend(bytes(max(0, start + len(block) - len(body))))
        body[start : start + len(block)] = block
    write_raw_datafile(directory, "Bank", bytes(body), [(FIRST_BLOCK, len(first_block))])


@contextmanager
def open_bank(directory: Path) -> Iterator[Datafile]:
    with open(directory / "CroBank.dat", "rb") as dat, open(directory / "CroBank.tad", "rb") as tad:
        yield Datafile("Bank", dat, tad, False, None)


def test_record_spread_over_extension_blocks_is_reassembled(tmp_path: Path) -> None:
    data = bytes(range(100))
    second, third = FIRST_BLOCK + BLOCKSIZE, FIRST_BLOCK + 2 * BLOCKSIZE
    write_bank_with_extended_record(
        tmp_path,
        extended_header(second, len(data)) + data[:20],
        [(second, extension_block(third, data[20:80])), (third, extension_block(0, data[80:]))],
    )

    with open_bank(tmp_path) as bank:
        assert bank.readrec(1) == data


def test_truncated_extended_record_header_is_reported(tmp_path: Path) -> None:
    write_bank_with_extended_record(tmp_path, bytes(4))

    with open_bank(tmp_path) as bank, pytest.raises(ValueError, match="shorter than its 8-byte extended record header"):
        bank.readrec(1)


def test_loop_in_extension_blocks_is_reported(tmp_path: Path) -> None:
    looping = FIRST_BLOCK + BLOCKSIZE
    write_bank_with_extended_record(
        tmp_path, extended_header(looping, 300) + bytes(20), [(looping, extension_block(looping, bytes(60)))]
    )

    with open_bank(tmp_path) as bank, pytest.raises(ValueError, match="loop in its extension blocks"):
        bank.readrec(1)


def test_record_longer_than_the_file_is_reported(tmp_path: Path) -> None:
    write_bank_with_extended_record(tmp_path, extended_header(FIRST_BLOCK + BLOCKSIZE, 0x0FFFFFFF) + bytes(20))

    with open_bank(tmp_path) as bank, pytest.raises(ValueError, match="more than the file holds"):
        bank.readrec(1)


def test_extension_block_past_the_end_of_the_file_is_reported(tmp_path: Path) -> None:
    write_bank_with_extended_record(tmp_path, extended_header(10_000, 100) + bytes(20))

    with open_bank(tmp_path) as bank, pytest.raises(ValueError, match="past the end of the file"):
        bank.readrec(1)


@pytest.mark.parametrize(
    ("offset", "length"), [(FIRST_BLOCK + 10_000, 5), (FIRST_BLOCK, 105)], ids=["past-the-end", "overrunning-the-end"]
)
def test_record_that_the_dat_file_does_not_hold_is_reported(tmp_path: Path, offset: int, length: int) -> None:
    write_raw_datafile(tmp_path, "Bank", bytes(100), [(offset, length | INLINE_RECORD_FLAGS << 24)])

    with open_bank(tmp_path) as bank, pytest.raises(ValueError, match=r"record 1 in CroBank\.dat .* past the end"):
        bank.readrec(1)


def test_record_of_length_zero_is_empty(tmp_path: Path) -> None:
    write_raw_datafile(tmp_path, "Bank", b"", [(FIRST_BLOCK + 10_000, 0)])

    with open_bank(tmp_path) as bank:
        assert bank.readrec(1) == b""


def test_corrupt_compressed_record_is_reported_as_a_value_error(tmp_path: Path) -> None:
    data = corrupt_compressed_record()
    write_raw_datafile(tmp_path, "Bank", data, [(FIRST_BLOCK, len(data) | INLINE_RECORD_FLAGS << 24)])

    with open_bank(tmp_path) as bank, pytest.raises(ValueError, match="corrupt compressed data"):
        bank.readrec(1)


def test_crodump_reports_a_corrupt_record_and_dumps_the_next(tmp_path: Path) -> None:
    corrupt, inline = bytes(4), b"hello"
    write_raw_datafile(
        tmp_path,
        "Bank",
        corrupt + inline,
        [(FIRST_BLOCK, len(corrupt)), (FIRST_BLOCK + len(corrupt), len(inline) | INLINE_RECORD_FLAGS << 24)],
    )

    result = run_command("crodump", ["crodump", str(tmp_path)])

    assert result.returncode == 0, result.stderr
    first, second = [line for line in result.stdout.splitlines() if line.startswith(("    1:", "    2:"))]
    assert "shorter than its 8-byte extended record header" in first
    assert inline.hex() in second


def test_leftover_tad_bytes_are_reported_through_the_warn_hook(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    write_datafile(tmp_path, "Bank", [b"\x01abc"])
    with (tmp_path / "CroBank.tad").open("ab") as tad:
        tad.write(b"\x00")
    messages: list[str] = []

    with (tmp_path / "CroBank.dat").open("rb") as dat, (tmp_path / "CroBank.tad").open("rb") as tad:
        Datafile("Bank", dat, tad, False, None, warn=messages.append)

    assert messages == ["WARN: leftover data in .tad"]
    assert capfd.readouterr().err == ""


def test_leftover_tad_bytes_are_printed_without_a_warn_hook(tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    write_datafile(tmp_path, "Bank", [b"\x01abc"])
    with (tmp_path / "CroBank.tad").open("ab") as tad:
        tad.write(b"\x00")

    with (tmp_path / "CroBank.dat").open("rb") as dat, (tmp_path / "CroBank.tad").open("rb") as tad:
        Datafile("Bank", dat, tad, False, None)

    assert capfd.readouterr().err == "WARN: leftover data in .tad\n"
