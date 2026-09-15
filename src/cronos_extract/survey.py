# ABOUTME: Finds CronosPro databases under a directory and reports each file's format version.
# ABOUTME: Reads only the 19-byte .dat header of every file, never a .tad file or a record.
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from ._format.header import DatHeader, read_dat_header


@dataclass(frozen=True)
class SurveyedFile:
    """One Cro*.dat file: its header, or the problem that stopped it being read."""

    name: str
    path: Path
    header: DatHeader | None
    problem: str | None


@dataclass(frozen=True)
class SurveyedDatabase:
    """One directory holding Cro*.dat files, with a surveyed file for each of them."""

    directory: Path
    files: tuple[SurveyedFile, ...]


def is_dat_file(filename: str) -> bool:
    """Whether `filename` is a Cro*.dat file, matched case-insensitively as the readers do."""
    lowered = filename.lower()
    return lowered.startswith("cro") and lowered.endswith(".dat")


def survey_file(path: Path) -> SurveyedFile:
    """Read `path`'s header, returning the problem that stopped it instead of raising."""
    name = path.name[3:-4]
    try:
        with path.open("rb") as file:
            return SurveyedFile(name=name, path=path, header=read_dat_header(file, where=path.name), problem=None)
    except (ValueError, OSError) as e:
        return SurveyedFile(name=name, path=path, header=None, problem=str(e))


def survey_databases(root: Path) -> Iterator[SurveyedDatabase]:
    """
    Yield a SurveyedDatabase for every directory under `root` that holds Cro*.dat files, in path order.

    Symbolic links are not followed, so a link loop cannot make this walk forever.
    """
    for directory, subdirectories, filenames in os.walk(root, followlinks=False):
        subdirectories.sort()
        dat_files = sorted(filename for filename in filenames if is_dat_file(filename))
        if dat_files:
            path = Path(directory)
            yield SurveyedDatabase(directory=path, files=tuple(survey_file(path / filename) for filename in dat_files))
