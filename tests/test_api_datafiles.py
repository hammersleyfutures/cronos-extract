# ABOUTME: Tests for finding a database's Cro file pairs and opening them, including hostile file systems.
# ABOUTME: Uses databases from tests/cronos_builder.py with FIFOs, sockets, symlinks and broken headers put in place.
import os
import socket
from pathlib import Path

import pytest
from cronos_builder import write_database, write_header_only_datafile

from cronos_extract import Diagnostic, DiagnosticKind, NotACronosFile, UnsupportedVersion
from cronos_extract._api.datafiles import (
    database_directory,
    list_directory,
    open_datafile,
    optional_file_info,
    warn_into,
)
from cronos_extract._api.diagnostics import DiagnosticLog
from cronos_extract._format.files import NotARegularFile


def built(tmp_path: Path, version: bytes = b"01.04", index_records: list[bytes | None] | None = None) -> Path:
    return Path(write_database(tmp_path / "db", [], version=version, index_records=index_records))


def open_stru(directory: Path, log: DiagnosticLog | None = None):
    return open_datafile(
        directory, list_directory(directory), "Stru", compact=False, kod=None, log=log or DiagnosticLog(None)
    )


def test_a_pair_opens_as_a_datafile_with_its_file_info(tmp_path: Path) -> None:
    dbdir = built(tmp_path)

    datafile, info = open_stru(dbdir)
    try:
        definition = datafile.readrec(1)
    finally:
        datafile.close()

    assert definition
    assert (datafile.name, datafile.version) == ("Stru", b"01.04")
    assert (info.name, info.path, info.version, info.problem) == ("Stru", dbdir / "CroStru.dat", "01.04", None)


def test_file_names_match_case_insensitively(tmp_path: Path) -> None:
    dbdir = built(tmp_path)
    (dbdir / "CroStru.dat").rename(dbdir / "crostru.DAT")

    datafile, info = open_stru(dbdir)
    datafile.close()

    assert (info.name, info.path) == ("stru", dbdir / "crostru.DAT")


def test_two_names_differing_only_in_case_use_the_first_sorted_and_report_the_other(tmp_path: Path) -> None:
    dbdir = built(tmp_path)
    (dbdir / "CROSTRU.DAT").write_bytes((dbdir / "CroStru.dat").read_bytes())
    log = DiagnosticLog(None)

    datafile, info = open_stru(dbdir, log)
    datafile.close()

    assert info.path == dbdir / "CROSTRU.DAT"
    (diagnostic,) = log.kept
    assert (diagnostic.kind, diagnostic.file) == (DiagnosticKind.UNEXPECTED_STRUCTURE, "CroStru.dat")
    assert "reading CROSTRU.DAT" in diagnostic.message


def test_a_missing_pair_is_not_a_cronos_file(tmp_path: Path) -> None:
    with pytest.raises(NotACronosFile, match=r"has no CroStru\.dat and CroStru\.tad"):
        open_stru(tmp_path)


def test_a_dat_without_its_tad_is_not_a_cronos_file(tmp_path: Path) -> None:
    dbdir = built(tmp_path)
    (dbdir / "CroStru.tad").unlink()

    with pytest.raises(NotACronosFile, match=r"has CroStru\.dat but no CroStru\.tad"):
        open_stru(dbdir)


def test_a_tad_without_its_dat_is_not_a_cronos_file(tmp_path: Path) -> None:
    dbdir = built(tmp_path)
    (dbdir / "CroStru.dat").unlink()

    with pytest.raises(NotACronosFile, match=r"has CroStru\.tad but no CroStru\.dat"):
        open_stru(dbdir)


def test_a_fifo_is_not_a_cronos_file(tmp_path: Path) -> None:
    dbdir = built(tmp_path)
    (dbdir / "CroStru.dat").unlink()
    os.mkfifo(dbdir / "CroStru.dat")

    with pytest.raises(NotACronosFile, match="is not a regular file") as raised:
        open_stru(dbdir)

    assert isinstance(raised.value.__cause__, NotARegularFile)


def test_a_directory_named_like_a_cro_file_is_not_a_cronos_file(tmp_path: Path) -> None:
    dbdir = built(tmp_path)
    (dbdir / "CroStru.tad").unlink()
    (dbdir / "CroStru.tad").mkdir()

    with pytest.raises(NotACronosFile, match="is not a regular file"):
        open_stru(dbdir)


def test_a_socket_is_not_a_cronos_file(tmp_path: Path) -> None:
    dbdir = built(tmp_path)
    (dbdir / "CroStru.tad").unlink()
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(str(dbdir / "CroStru.tad"))

        with pytest.raises(NotACronosFile, match="cannot be opened") as raised:
            open_stru(dbdir)

    assert isinstance(raised.value.__cause__, OSError)


def test_a_dangling_symlink_is_not_a_cronos_file(tmp_path: Path) -> None:
    dbdir = built(tmp_path)
    (dbdir / "CroStru.dat").unlink()
    (dbdir / "CroStru.dat").symlink_to(tmp_path / "missing")

    with pytest.raises(NotACronosFile, match="cannot be opened") as raised:
        open_stru(dbdir)

    assert isinstance(raised.value.__cause__, FileNotFoundError)


@pytest.mark.parametrize(
    ("content", "message"),
    [(b"CroFile\x00", "shorter than its 19-byte header"), (b"NotACronosFile" + bytes(20), "not a Cronos file")],
)
def test_a_broken_header_is_not_a_cronos_file(tmp_path: Path, content: bytes, message: str) -> None:
    dbdir = built(tmp_path)
    (dbdir / "CroStru.dat").write_bytes(content)

    with pytest.raises(NotACronosFile, match=message):
        open_stru(dbdir)


@pytest.mark.parametrize(("version", "generation"), [(b"01.19", "v7"), (b"09.99", "unknown")])
def test_a_version_that_is_not_v3_or_v4_is_unsupported(tmp_path: Path, version: bytes, generation: str) -> None:
    dbdir = built(tmp_path)
    write_header_only_datafile(dbdir, "Stru", version=version)

    with pytest.raises(UnsupportedVersion, match=rf"version {version.decode()} \({generation}\)"):
        open_stru(dbdir)


@pytest.mark.parametrize(("version", "header_size"), [(b"01.04", 8), (b"01.11", 16)])
def test_a_tad_shorter_than_its_header_is_not_a_cronos_file(tmp_path: Path, version: bytes, header_size: int) -> None:
    dbdir = built(tmp_path, version=version)
    (dbdir / "CroStru.tad").write_bytes(bytes(header_size - 1))

    with pytest.raises(NotACronosFile, match=rf"CroStru\.tad in .* is shorter than its {header_size}-byte header"):
        open_stru(dbdir)


def test_leftover_tad_bytes_are_an_unexpected_structure_diagnostic(tmp_path: Path) -> None:
    dbdir = built(tmp_path)
    with (dbdir / "CroStru.tad").open("ab") as tad:
        tad.write(b"\x00")
    log = DiagnosticLog(None)

    datafile, _ = open_stru(dbdir, log)
    datafile.close()

    assert list(log.kept) == [
        Diagnostic(DiagnosticKind.UNEXPECTED_STRUCTURE, "leftover data in .tad", file="CroStru.dat")
    ]


def test_warn_into_strips_the_printed_prefix_and_adds_its_own() -> None:
    log = DiagnosticLog(None)

    warn_into(log, "CroStru.dat", prefix="Base001: ")("Warning: FieldDefinition section not terminated")
    warn_into(log, "CroStru.dat")("WARN: expected dbinfo to start with 0x03")

    assert [diagnostic.message for diagnostic in log.kept] == [
        "Base001: FieldDefinition section not terminated",
        "expected dbinfo to start with 0x03",
    ]


def test_an_optional_file_that_is_absent_has_no_info(tmp_path: Path) -> None:
    dbdir = built(tmp_path)
    log = DiagnosticLog(None)

    assert optional_file_info(dbdir, list_directory(dbdir), "Index", log) is None
    assert list(log.kept) == []


def test_a_readable_optional_file_has_info_even_when_it_is_v7(tmp_path: Path) -> None:
    dbdir = built(tmp_path)
    write_header_only_datafile(dbdir, "Index")
    (dbdir / "CroIndex.tad").write_bytes(bytes(8))
    log = DiagnosticLog(None)

    info = optional_file_info(dbdir, list_directory(dbdir), "Index", log)

    assert info is not None
    assert (info.generation, info.problem) == ("v7", None)
    assert list(log.kept) == []


@pytest.mark.parametrize("hazard", ["garbage", "fifo", "dangling", "no-tad", "no-dat"])
def test_an_unreadable_optional_file_is_reported_as_unreadable(tmp_path: Path, hazard: str) -> None:
    dbdir = built(tmp_path, index_records=[])
    if hazard == "garbage":
        (dbdir / "CroIndex.dat").write_bytes(b"garbage")
    elif hazard == "fifo":
        (dbdir / "CroIndex.dat").unlink()
        os.mkfifo(dbdir / "CroIndex.dat")
    elif hazard == "dangling":
        (dbdir / "CroIndex.dat").unlink()
        (dbdir / "CroIndex.dat").symlink_to(tmp_path / "missing")
    elif hazard == "no-tad":
        (dbdir / "CroIndex.tad").unlink()
    else:
        (dbdir / "CroIndex.dat").unlink()
    log = DiagnosticLog(None)

    info = optional_file_info(dbdir, list_directory(dbdir), "Index", log)

    assert info is not None
    assert info.problem is not None
    (diagnostic,) = log.kept
    assert (diagnostic.kind, diagnostic.file, diagnostic.message) == (
        DiagnosticKind.UNREADABLE_FILE,
        "CroIndex.dat",
        info.problem,
    )


def test_a_bytes_path_is_refused() -> None:
    with pytest.raises(TypeError, match="not bytes"):
        database_directory(b"/some/database")  # ty: ignore[invalid-argument-type]


def test_listing_a_file_raises_not_a_directory(tmp_path: Path) -> None:
    (tmp_path / "file").write_bytes(b"")

    with pytest.raises(NotADirectoryError):
        list_directory(tmp_path / "file")


def test_listing_a_missing_directory_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        list_directory(tmp_path / "missing")
