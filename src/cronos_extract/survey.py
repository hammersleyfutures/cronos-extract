# ABOUTME: Finds CronosPro databases under a directory and reports each file's format version.
# ABOUTME: Reads only the 19-byte .dat header of every file, never a .tad file or a record.
import json
import os
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from ._api.info import FileInfo, read_file_info


@dataclass(frozen=True)
class SurveyedDatabase:
    """One directory holding Cro*.dat files, with a surveyed file for each of them."""

    directory: Path
    files: tuple[FileInfo, ...]


def is_dat_file(filename: str) -> bool:
    """Whether `filename` is a Cro*.dat file, matched case-insensitively as the readers do."""
    lowered = filename.lower()
    return lowered.startswith("cro") and lowered.endswith(".dat")


def survey_databases(root: Path, problems: list[OSError] | None = None) -> Iterator[SurveyedDatabase]:
    """
    Yield a SurveyedDatabase for every directory under `root` that holds Cro*.dat files.

    Directories are visited depth-first, each one before the subdirectories it holds, and the subdirectories
    of a directory in sorted order. This is not the same as sorted path order: `a/b` comes before `a-b`,
    because the walk descends into `a` before going on to its sibling `a-b`.
    Symbolic links are not followed, so a link loop cannot make this walk forever. A directory that cannot be
    listed is appended to `problems` when one is given; without it such a directory is passed over in silence.
    """
    for directory, subdirectories, filenames in os.walk(
        root, onerror=None if problems is None else problems.append, followlinks=False
    ):
        subdirectories.sort()
        # Subdirectories named like a data file are surveyed too, so that a directory called CroStru.dat is
        # reported as the problem it is instead of being passed over without a word.
        dat_files = sorted((name for name in (*filenames, *subdirectories) if is_dat_file(name)), key=str.lower)
        if dat_files:
            path = Path(directory)
            yield SurveyedDatabase(
                directory=path,
                files=tuple(read_file_info(name[3:-4] or name, path / name) for name in dat_files),
            )


def describe_file(file: FileInfo) -> str:
    """Return the survey line for one file, without its database's directory."""
    if file.problem is not None:
        return f"{file.name:<6}{file.problem}"
    flags = [
        f"{'64' if file.use64bit else '32'}-bit",
        "kod-encoded" if file.kod_encoded else "plain",
        "compressed" if file.compressed else "uncompressed",
    ]
    if file.own_kod:
        flags.append("own-kod")
    return f"{file.name:<6}{file.version}  {file.generation:<7}  " + "  ".join(flags)


def format_text(databases: Iterable[SurveyedDatabase]) -> Iterator[str]:
    """Yield one block of lines per database: its directory, then a line per file."""
    for database in databases:
        yield str(database.directory)
        for file in database.files:
            yield f"  {describe_file(file)}"
        yield ""


def format_counts(databases: Iterable[SurveyedDatabase]) -> Iterator[str]:
    """
    Yield a line per version and generation with the number of files, naming no directories.

    A last line gives the number of files whose header could not be read, when there are any.
    """
    counts: Counter[tuple[str, str]] = Counter()
    problems = 0
    for database in databases:
        for file in database.files:
            if file.version is None or file.generation is None:
                problems += 1
            else:
                counts[(file.version, file.generation)] += 1
    for (version, generation), count in sorted(counts.items()):
        yield f"{version}  {generation:<7}  {count}"
    if problems:
        yield f"unreadable files: {problems}"


def format_jsonl(databases: Iterable[SurveyedDatabase]) -> Iterator[str]:
    """Yield one JSON object per database, with a nested object per file."""
    for database in databases:
        yield json.dumps(
            {
                "directory": str(database.directory),
                "files": [
                    {
                        "name": file.name,
                        "version": file.version,
                        "generation": file.generation,
                        "use64bit": file.use64bit,
                        "kod_encoded": file.kod_encoded,
                        "compressed": file.compressed,
                        "own_kod": file.own_kod,
                        "problem": file.problem,
                    }
                    for file in database.files
                ],
            }
        )


def read_path_list(path: Path) -> list[Path]:
    """
    Return the directories named in `path`, one per line.

    Blank lines and lines starting with # are ignored, surrounding whitespace is stripped, and a relative
    path is taken from the current directory. A name that is not valid UTF-8, as a list written on a Russian
    Windows machine holds, is kept as the bytes on disk. Raises OSError when the list itself cannot be read.
    """
    lines = path.read_text(encoding="utf-8", errors="surrogateescape").splitlines()
    return [Path(entry) for line in lines if (entry := line.strip()) and not entry.startswith("#")]


def survey_roots(roots: Iterable[Path], problems: list[OSError] | None = None) -> list[SurveyedDatabase]:
    """
    Survey every directory in `roots` in order, returning the databases found.

    A database found under more than one root, because the roots overlap or repeat, is returned once.
    Directories that cannot be listed are appended to `problems` when one is given.
    """
    seen: set[Path] = set()
    databases: list[SurveyedDatabase] = []
    for root in roots:
        for database in survey_databases(root, problems):
            resolved = database.directory.resolve()
            if resolved not in seen:
                seen.add(resolved)
                databases.append(database)
    return databases
