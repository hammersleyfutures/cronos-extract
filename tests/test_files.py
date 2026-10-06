# ABOUTME: Tests for cronos_extract._format.files, which opens Cro files without blocking and only if they are regular.
# ABOUTME: Uses real FIFOs, sockets, directories and symlinks made in a temporary directory; also tests read_at.
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from cronos_extract._format import files
from cronos_extract._format.files import NotARegularFile, open_regular_file, read_at


def test_a_regular_file_opens_for_binary_reading(tmp_path: Path) -> None:
    (tmp_path / "CroStru.dat").write_bytes(b"CroFile\x00")

    with open_regular_file(tmp_path / "CroStru.dat") as file:
        assert file.read() == b"CroFile\x00"


def test_a_fifo_is_refused_without_waiting_for_a_writer(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "CroStru.dat")
    code = (
        "import sys\n"
        "from cronos_extract._format.files import NotARegularFile, open_regular_file\n"
        "try:\n"
        "    open_regular_file(sys.argv[1])\n"
        "except NotARegularFile as e:\n"
        "    print(e)\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path / "CroStru.dat")],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.stdout == "CroStru.dat is not a regular file\n"
    assert result.stderr == ""


def test_a_directory_is_refused(tmp_path: Path) -> None:
    (tmp_path / "CroStru.dat").mkdir()

    with pytest.raises(NotARegularFile, match=r"^CroStru\.dat is not a regular file$"):
        open_regular_file(tmp_path / "CroStru.dat")


def test_a_socket_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "s"
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(str(path))

        with pytest.raises(OSError):
            open_regular_file(path)


def test_a_dangling_symlink_raises_file_not_found(tmp_path: Path) -> None:
    (tmp_path / "CroStru.dat").symlink_to(tmp_path / "missing")

    with pytest.raises(FileNotFoundError):
        open_regular_file(tmp_path / "CroStru.dat")


def test_a_symlink_to_a_regular_file_is_followed(tmp_path: Path) -> None:
    (tmp_path / "real").write_bytes(b"data")
    (tmp_path / "CroStru.dat").symlink_to(tmp_path / "real")

    with open_regular_file(tmp_path / "CroStru.dat") as file:
        assert file.read() == b"data"


def test_not_a_regular_file_is_an_os_error() -> None:
    assert issubclass(NotARegularFile, OSError)


DATA = bytes(range(256)) * 64


@pytest.mark.parametrize("pread", [True, False], ids=["pread", "seek-and-read"])
@pytest.mark.parametrize(
    ("offset", "size", "expected"),
    [(100, 10, DATA[100:110]), (len(DATA) - 4, 10, DATA[-4:]), (len(DATA), 10, b""), (len(DATA) + 50, 10, b"")],
    ids=["inside", "across-the-end", "at-the-end", "past-the-end"],
)
def test_read_at_reads_up_to_size_bytes_at_the_offset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pread: bool, offset: int, size: int, expected: bytes
) -> None:
    monkeypatch.setattr(files, "HAS_PREAD", pread and hasattr(os, "pread"))
    (tmp_path / "CroBank.dat").write_bytes(DATA)

    with open_regular_file(tmp_path / "CroBank.dat") as file:
        assert read_at(file, offset, size) == expected


@pytest.mark.skipif(not hasattr(os, "pread"), reason="the system has no pread")
def test_read_at_reads_only_the_bytes_asked_for(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "CroBank.dat").write_bytes(DATA)
    asked: list[int] = []
    real_pread = os.pread

    def counting_pread(descriptor: int, size: int, offset: int) -> bytes:
        asked.append(size)
        return real_pread(descriptor, size, offset)

    monkeypatch.setattr(os, "pread", counting_pread)
    with open_regular_file(tmp_path / "CroBank.dat") as file:
        file.read(3)
        assert [read_at(file, offset, 7) for offset in (9000, 50, 12000)] == [
            DATA[9000:9007],
            DATA[50:57],
            DATA[12000:12007],
        ]
        # The file's own position and buffer are untouched, so a buffered read goes on where it was.
        assert file.read(3) == DATA[3:6]

    # A seek and read through the buffer would refill st_blksize bytes for each record outside it.
    assert asked == [7, 7, 7]


@pytest.mark.skipif(not hasattr(os, "pread"), reason="the system has no pread")
def test_read_at_goes_on_after_a_short_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "CroBank.dat").write_bytes(DATA)
    real_pread = os.pread

    def short_pread(descriptor: int, size: int, offset: int) -> bytes:
        return real_pread(descriptor, min(size, 5), offset)

    monkeypatch.setattr(os, "pread", short_pread)
    with open_regular_file(tmp_path / "CroBank.dat") as file:
        assert read_at(file, 1000, 23) == DATA[1000:1023]
