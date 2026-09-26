# ABOUTME: Finds a database's Cro*.dat and Cro*.tad pairs by case-insensitive name and opens them as Datafiles.
# ABOUTME: A missing, unopenable, non-Cronos or unsupported CroStru or CroBank raises; CroIndex and CroSys are reported.
import os
from contextlib import ExitStack
from pathlib import Path

from .._format.files import open_regular_file
from .._format.header import read_dat_header
from .._format.tad import tad_layout
from ..Datafile import Datafile
from .diagnostics import Diagnostic, DiagnosticKind, DiagnosticLog
from .errors import NotACronosFile, UnsupportedVersion
from .info import FileInfo, info_from_header, info_from_problem, read_file_info
from .kod import Kod, kod_coder


def database_directory(path: str | os.PathLike[str]) -> Path:
    """`path` as a Path. Raises TypeError for bytes, whose directory listing would hold bytes names that never match."""
    location = os.fspath(path)
    if not isinstance(location, str):
        raise TypeError(f"a database path must be str or os.PathLike[str], not bytes: {location!r}")
    return Path(location)


def list_directory(directory: Path) -> list[str]:
    """The names in `directory`, sorted. OSError propagates, including NotADirectoryError for a file."""
    return sorted(os.listdir(directory))


def find_file(directory: Path, names: list[str], filename: str, log: DiagnosticLog) -> Path | None:
    """
    The path of `filename` among `names`, matched case-insensitively, or None.

    When several names match, the first in sorted order is used and an unexpected_structure diagnostic names it.
    """
    matches = [name for name in names if name.lower() == filename.lower()]
    if not matches:
        return None
    if len(matches) > 1:
        log.record(
            Diagnostic(
                DiagnosticKind.UNEXPECTED_STRUCTURE,
                f"{directory} holds {len(matches)} files named {filename} in different cases; reading {matches[0]}",
                file=filename,
            )
        )
    return directory / matches[0]


def missing_pair_message(
    directory: Path, datname: str, tadname: str, datpath: Path | None, tadpath: Path | None
) -> str:
    """Say which of the `datname` and `tadname` pair `directory` lacks, given the paths found for each."""
    if datpath is not None:
        return f"{directory} has {datname} but no {tadname}"
    if tadpath is not None:
        return f"{directory} has {tadname} but no {datname}"
    return f"{directory} has no {datname} and {tadname}"


def open_datafile(
    directory: Path, names: list[str], base: str, *, compact: bool, kod: Kod | None, log: DiagnosticLog
) -> tuple[Datafile, FileInfo]:
    """
    Open the Cro<base>.dat and Cro<base>.tad pair in `directory`, listed as `names`, as a Datafile with its FileInfo.

    Raises NotACronosFile when the pair is incomplete, a file is not a regular file or cannot be opened, the .dat
    header is short or has an unknown magic, or the .tad is shorter than its header; UnsupportedVersion when the
    version is neither v3 nor v4. Problems the Datafile reports are recorded in `log`.
    """
    datname, tadname = f"Cro{base}.dat", f"Cro{base}.tad"
    datpath = find_file(directory, names, datname, log)
    tadpath = find_file(directory, names, tadname, log)
    if datpath is None or tadpath is None:
        raise NotACronosFile(missing_pair_message(directory, datname, tadname, datpath, tadpath))
    with ExitStack() as stack:
        try:
            dat = stack.enter_context(open_regular_file(datpath))
            tad = stack.enter_context(open_regular_file(tadpath))
        except OSError as e:
            raise NotACronosFile(f"{datname} or {tadname} in {directory} cannot be opened: {e}") from e
        try:
            header = read_dat_header(dat, where=datname)
        except ValueError as e:
            raise NotACronosFile(f"{e}, in {directory}") from e
        layout = tad_layout(header.version)
        if layout is None:
            raise UnsupportedVersion(
                f"{datname} in {directory} is CronosPro version {header.version_text} ({header.generation}), "
                "which this release cannot read"
            )
        if os.fstat(tad.fileno()).st_size < layout.header.size:
            raise NotACronosFile(f"{tadname} in {directory} is shorter than its {layout.header.size}-byte header")
        datafile = Datafile(base, dat, tad, compact, kod_coder(kod), log.record)
        stack.pop_all()
    return datafile, info_from_header(datpath.name[3:-4], datpath, header)


def optional_file_info(directory: Path, names: list[str], base: str, log: DiagnosticLog) -> FileInfo | None:
    """
    The FileInfo of Cro<base>.dat, a file reading tables does not need, or None when neither it nor its .tad exists.

    A pair with a half missing, or a header that cannot be read, gives a FileInfo with a problem, which is also
    recorded in `log` as unreadable_file.
    """
    datname, tadname = f"Cro{base}.dat", f"Cro{base}.tad"
    datpath = find_file(directory, names, datname, log)
    tadpath = find_file(directory, names, tadname, log)
    if datpath is None and tadpath is None:
        return None
    if datpath is None or tadpath is None:
        problem = missing_pair_message(directory, datname, tadname, datpath, tadpath)
        info = info_from_problem(
            base if datpath is None else datpath.name[3:-4], datpath or directory / datname, problem
        )
    else:
        info = read_file_info(datpath.name[3:-4], datpath)
    if info.problem is not None:
        log.record(Diagnostic(DiagnosticKind.UNREADABLE_FILE, info.problem, file=datname))
    return info
