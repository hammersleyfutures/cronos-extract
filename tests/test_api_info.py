# ABOUTME: Tests for FileInfo, the per-file version and encoding flags that bank.info and the survey report.
# ABOUTME: Reads headers of databases from tests/cronos_builder.py and of broken, FIFO and missing files.
import dataclasses
import os
from pathlib import Path

import pytest
from cronos_builder import random_kod, write_database, write_header_only_datafile

from cronos_extract._api.info import FileInfo, read_file_info


def test_file_info_reports_a_v3_header(tmp_path: Path) -> None:
    dbdir = Path(write_database(tmp_path / "db", []))

    info = read_file_info("Stru", dbdir / "CroStru.dat")

    assert info == FileInfo(
        name="Stru",
        path=dbdir / "CroStru.dat",
        version="01.04",
        generation="v3",
        use64bit=False,
        kod_encoded=False,
        compressed=False,
        own_kod=True,
        problem=None,
    )


def test_file_info_reports_a_kod_encoded_v4_header(tmp_path: Path) -> None:
    dbdir = Path(write_database(tmp_path / "db", [], random_kod(seed=1), version=b"01.11"))

    info = read_file_info("Bank", dbdir / "CroBank.dat")

    assert (info.version, info.generation, info.use64bit, info.kod_encoded, info.own_kod, info.problem) == (
        "01.11",
        "v4",
        True,
        True,
        True,
        None,
    )


def test_file_info_reports_a_v7_header_without_a_problem(tmp_path: Path) -> None:
    write_header_only_datafile(tmp_path, "Bank", encoding=3)

    info = read_file_info("Bank", tmp_path / "CroBank.dat")

    assert (info.version, info.generation, info.compressed, info.problem) == ("01.19", "v7", True, None)


@pytest.mark.parametrize(
    ("content", "problem"),
    [(b"CroFile\x00", "shorter than its 19-byte header"), (b"NotACronosFile" + bytes(20), "not a Cronos file")],
)
def test_file_info_reports_a_header_problem_with_no_flags(tmp_path: Path, content: bytes, problem: str) -> None:
    (tmp_path / "CroStru.dat").write_bytes(content)

    info = read_file_info("Stru", tmp_path / "CroStru.dat")

    assert info.problem is not None
    assert problem in info.problem
    assert (info.version, info.generation, info.use64bit, info.kod_encoded, info.compressed, info.own_kod) == (
        None,
        None,
        None,
        None,
        None,
        None,
    )


def test_file_info_reports_a_fifo_as_not_a_regular_file(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "CroStru.dat")

    assert read_file_info("Stru", tmp_path / "CroStru.dat").problem == "CroStru.dat is not a regular file"


def test_file_info_reports_a_missing_file(tmp_path: Path) -> None:
    problem = read_file_info("Stru", tmp_path / "CroStru.dat").problem

    assert problem is not None
    assert "No such file or directory" in problem


def test_file_info_is_frozen_and_hashable(tmp_path: Path) -> None:
    info = read_file_info("Stru", tmp_path / "CroStru.dat")

    assert hash(info) == hash(dataclasses.replace(info))
    with pytest.raises(dataclasses.FrozenInstanceError):
        info.name = "Bank"  # ty: ignore[invalid-assignment]
