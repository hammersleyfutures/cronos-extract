# ABOUTME: Opens Cro*.dat and Cro*.tad files for reading without blocking on FIFOs, and only if they are regular files.
# ABOUTME: A FIFO, socket, device or directory raises NotARegularFile, an OSError, instead of hanging or being read.
import os
import stat
from pathlib import Path
from typing import BinaryIO

# Windows has neither O_NONBLOCK nor FIFOs in the file system; elsewhere it stops an open from waiting for a writer.
O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
# Windows opens files in text mode unless O_BINARY is given; elsewhere it does not exist.
O_BINARY = getattr(os, "O_BINARY", 0)


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
