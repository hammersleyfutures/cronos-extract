# ABOUTME: FileInfo: one Cro*.dat file's format version and encoding flags, or the problem that stopped them being read.
# ABOUTME: Shared by bank.info and the survey, which report files the same way; reads only the 19-byte header.
from dataclasses import dataclass
from pathlib import Path

from .._format.files import open_regular_file
from .._format.header import DatHeader, Generation, read_dat_header


@dataclass(frozen=True)
class FileInfo:
    """
    One Cro*.dat file, as its header describes it.

    `name` is the part of the file name between "Cro" and ".dat", as spelt on disk, such as "Stru", and `path` the
    file's path. When `problem` is None every other field is set; when the header could not be read, `problem`
    says why and the version and flag fields are None.
    """

    name: str
    path: Path
    version: str | None
    generation: Generation | None
    use64bit: bool | None
    kod_encoded: bool | None
    compressed: bool | None
    own_kod: bool | None
    problem: str | None


def info_from_header(name: str, path: Path, header: DatHeader) -> FileInfo:
    """The FileInfo of the file at `path`, whose header is `header`."""
    return FileInfo(
        name=name,
        path=path,
        version=header.version_text,
        generation=header.generation,
        use64bit=header.use64bit,
        kod_encoded=header.kod_encoded,
        compressed=header.compressed,
        own_kod=header.own_kod,
        problem=None,
    )


def info_from_problem(name: str, path: Path, problem: str) -> FileInfo:
    """The FileInfo of the file at `path`, whose header could not be read because of `problem`."""
    return FileInfo(
        name=name,
        path=path,
        version=None,
        generation=None,
        use64bit=None,
        kod_encoded=None,
        compressed=None,
        own_kod=None,
        problem=problem,
    )


def read_file_info(name: str, path: Path) -> FileInfo:
    """
    Read the header of the .dat file at `path`, returning the problem that stopped it instead of raising.

    Only a regular file is opened, and without blocking, so a FIFO named like a Cro file is reported, not waited on.
    """
    try:
        with open_regular_file(path) as file:
            return info_from_header(name, path, read_dat_header(file, where=path.name))
    except (ValueError, OSError) as e:
        return info_from_problem(name, path, str(e))
