# ABOUTME: Tests for cronos_extract.Datafile reading records stored in extension blocks, including corrupt ones.
# ABOUTME: Lays out .dat and .tad files byte by byte with tests/cronos_builder.write_raw_datafile.
import argparse
import struct
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import pytest
from cli import run_command
from cronos_builder import (
    BLOCKSIZE,
    DAT_PREFIX_SIZE,
    V3_INLINE_BIT,
    V4_INLINE_RECORD_FLAGS,
    compressed_record,
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


def inline_tad_entry(version: bytes, offset: int, length: int) -> tuple[int, int]:
    """The (offset field, length field) of an inline record's .tad entry, with the flags where `version` keeps them."""
    if version == b"01.11":
        return (offset | V4_INLINE_RECORD_FLAGS << 56, length)
    return (offset, length | V3_INLINE_BIT)


@pytest.mark.parametrize("version", [b"01.04", b"01.11"], ids=["v3", "v4"])
@pytest.mark.parametrize(
    ("offset", "length"), [(FIRST_BLOCK + 10_000, 5), (FIRST_BLOCK, 105)], ids=["past-the-end", "overrunning-the-end"]
)
def test_record_that_the_dat_file_does_not_hold_is_reported(
    tmp_path: Path, version: bytes, offset: int, length: int
) -> None:
    write_raw_datafile(tmp_path, "Bank", bytes(100), [inline_tad_entry(version, offset, length)], version=version)

    # The message names the offset without its flags, so a v4 offset read with the flags still set fails the match.
    message = rf"record 1 in CroBank\.dat has {length} bytes at offset {offset:#x}, which runs past the end"
    with open_bank(tmp_path) as bank, pytest.raises(ValueError, match=message):
        bank.readrec(1)


def test_record_of_length_zero_is_empty(tmp_path: Path) -> None:
    write_raw_datafile(tmp_path, "Bank", b"", [(FIRST_BLOCK + 10_000, 0)])

    with open_bank(tmp_path) as bank:
        assert bank.readrec(1) == b""


def test_corrupt_compressed_record_is_reported_as_a_value_error(tmp_path: Path) -> None:
    data = corrupt_compressed_record()
    write_raw_datafile(tmp_path, "Bank", data, [(FIRST_BLOCK, len(data) | V3_INLINE_BIT)])

    with open_bank(tmp_path) as bank, pytest.raises(ValueError, match="corrupt compressed data"):
        bank.readrec(1)


def test_inspect_crodump_reports_a_corrupt_record_and_dumps_the_next(tmp_path: Path) -> None:
    corrupt, inline = bytes(4), b"hello"
    write_raw_datafile(
        tmp_path,
        "Bank",
        corrupt + inline,
        [(FIRST_BLOCK, len(corrupt)), (FIRST_BLOCK + len(corrupt), len(inline) | V3_INLINE_BIT)],
    )

    result = run_command("cli", ["inspect", "crodump", str(tmp_path)])

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


def dump_args(**options: object) -> argparse.Namespace:
    return argparse.Namespace(maxrecs=0xFFFFFFFF, verbose=False, ascdump=False, decompress=True, **options)


def test_readrec_reports_a_checksum_mismatch_through_warn(tmp_path: Path) -> None:
    write_datafile(tmp_path, "Stru", [compressed_record(b"definition", wrong_checksums={0})])
    messages: list[str] = []

    with (tmp_path / "CroStru.dat").open("rb") as dat, (tmp_path / "CroStru.tad").open("rb") as tad:
        datafile = Datafile("Stru", dat, tad, False, None, warn=messages.append)
        assert datafile.readrec(1) == b"definition"

    assert messages == ["WARN: record 1 in CroStru.dat has compressed data whose checksum does not match; it is kept"]


def test_read_record_gives_the_mismatched_chunks(tmp_path: Path) -> None:
    write_datafile(tmp_path, "Bank", [compressed_record(b"a", b"b", wrong_checksums={1})])

    with open_bank(tmp_path) as bank:
        parts = bank.read_record(1)

    assert parts is not None
    assert (parts.data, parts.mismatched_chunks) == (b"ab", (1,))


@pytest.mark.parametrize("recno", [0, -1, 2])
def test_a_record_number_outside_the_file_is_a_value_error(tmp_path: Path, recno: int) -> None:
    write_datafile(tmp_path, "Bank", [b"only"])

    with open_bank(tmp_path) as bank, pytest.raises(ValueError, match=f"CroBank.dat has no record {recno}"):
        bank.readrec(recno)


@pytest.mark.parametrize("index", [-1, 1])
def test_an_entry_index_outside_the_file_is_a_value_error(tmp_path: Path, index: int) -> None:
    write_datafile(tmp_path, "Bank", [b"only"])

    with open_bank(tmp_path) as bank, pytest.raises(ValueError, match=f"CroBank.tad has no entry {index}"):
        bank.entry(index)


def test_a_tad_shorter_than_its_header_is_a_value_error(tmp_path: Path) -> None:
    write_datafile(tmp_path, "Bank", [b"x"])
    (tmp_path / "CroBank.tad").write_bytes(b"\x00\x00\x00")

    with pytest.raises(ValueError, match=r"CroBank\.tad is shorter than its 8-byte header"), open_bank(tmp_path):
        pass


def test_dump_prints_the_bytes_of_a_truncated_inline_record(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_raw_datafile(tmp_path, "Bank", b"abc", [(DAT_PREFIX_SIZE, 10 | V3_INLINE_BIT)], version=b"01.02")

    with open_bank(tmp_path) as bank:
        bank.dump(dump_args())

    (line,) = [line for line in capsys.readouterr().out.splitlines() if line.startswith("    1:")]
    assert "616263" in line
    assert "<" not in line
