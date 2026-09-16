# ABOUTME: Tests for cronos_extract._format.files, which opens Cro files without blocking and only if they are regular.
# ABOUTME: Uses real FIFOs, sockets, directories and symlinks made in a temporary directory.
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from cronos_extract._format.files import NotARegularFile, open_regular_file


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
