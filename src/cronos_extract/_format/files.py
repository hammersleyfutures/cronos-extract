# ABOUTME: Opens Cro*.dat and Cro*.tad files for reading without blocking on FIFOs, and only if they are regular files.
# ABOUTME: A FIFO, socket, device or directory raises NotARegularFile; read_at reads records without a buffer refill.
import os
import stat
from pathlib import Path
from typing import BinaryIO

# Windows has neither O_NONBLOCK nor FIFOs in the file system; elsewhere it stops an open from waiting for a writer.
O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
# Windows opens files in text mode unless O_BINARY is given; elsewhere it does not exist.
O_BINARY = getattr(os, "O_BINARY", 0)
# Windows has no os.pread; read_at then seeks and reads through the file's buffer.
HAS_PREAD = hasattr(os, "pread")


class NotARegularFile(OSError):
    """Raised for a path that is a FIFO, socket, device or directory, which no Cronos file is."""


def open_regular_file(path: str | os.PathLike[str]) -> BinaryIO:
    """
    Open `path` for binary reading, raising NotARegularFile unless it is a regular file.

    The file is opened without blocking, so a FIFO does not wait for a writer, and checked with fstat on the open
    descriptor, so it cannot be swapped for something else between the check and the open. Symbolic links are
    followed. Other failures to open raise the OSError that os.open raises.
    """
    descriptor = os.open(path, os.O_RDONLY | O_NONBLOCK | O_BINARY)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise NotARegularFile(f"{Path(path).name} is not a regular file")
        if O_NONBLOCK:
            os.set_blocking(descriptor, True)
        return os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise


def read_at(file: BinaryIO, offset: int, size: int) -> bytes:
    """
    Read up to `size` bytes of `file` at `offset`, fewer only at the end of the file.

    Where the system has pread, the bytes are read from the file's descriptor at `offset`, past the buffer of the
    BufferedReader that open_regular_file returns, and the file's position does not move. A seek and read through
    that buffer refills the whole buffer, st_blksize bytes, for each record outside it: 128 KiB per record on some
    network file systems, however short the record. Elsewhere, and for a file without a descriptor, it seeks and
    reads.
    """
    if not HAS_PREAD:
        file.seek(offset)
        return file.read(size)
    try:
        descriptor = file.fileno()
    except OSError:
        file.seek(offset)
        return file.read(size)
    first = os.pread(descriptor, size, offset)
    if len(first) == size or not first:
        return first
    # A regular file returns fewer bytes only at its end, or when a signal interrupts a large read.
    chunks = [first]
    done = len(first)
    while done < size:
        chunk = os.pread(descriptor, size - done, offset + done)
        if not chunk:
            break
        chunks.append(chunk)
        done += len(chunk)
    return b"".join(chunks)
