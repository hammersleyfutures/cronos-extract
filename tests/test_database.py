# ABOUTME: Tests for cronos_extract.Database: opening and closing a database's files and decoding its definition.
# ABOUTME: Uses the sample database in test_data, small hand-written files and databases from tests/cronos_builder.py.
import argparse
import os
import struct
from pathlib import Path

import pytest
from cli import run_command
from cronos_builder import (
    TEST_DB,
    database_with_extra_definition_key,
    erdgeist_table_definition,
    ignore_problems,
    random_kod,
    stru_records_from_test_db,
    table_definition_key_before_base001,
    write_database,
    write_datafile,
)

from cronos_extract import Diagnostic, DiagnosticKind
from cronos_extract.Database import Database
from cronos_extract.koddecoder import INITIAL_KOD, KODcoding


def test_database_closes_its_files_on_exit() -> None:
    with Database(str(TEST_DB), False, KODcoding(INITIAL_KOD), report=ignore_problems) as db:
        files = [file for datafile in (db.stru, db.index, db.bank) if datafile for file in (datafile.dat, datafile.tad)]
        assert len(files) == 6
        assert not any(file.closed for file in files)

    assert all(file.closed for file in files)


def test_file_without_cronos_magic_is_reported_in_the_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "CroStru.dat").write_bytes(b"NotACronosFile" + bytes(20))
    (tmp_path / "CroStru.tad").write_bytes(bytes(8))

    with pytest.raises(ValueError, match=r"CroStru\.dat is not a Cronos file: unknown magic b'NotACron'"):
        Database(str(tmp_path), False, KODcoding(INITIAL_KOD), report=ignore_problems)

    assert capsys.readouterr().out == ""


def test_unreadable_datafile_leaves_no_open_files(tmp_path: Path) -> None:
    (tmp_path / "CroStru.dat").write_bytes(b"NotACronosFile" + bytes(20))
    (tmp_path / "CroStru.tad").write_bytes(bytes(8))

    with pytest.raises(ValueError, match="is not a Cronos file"):
        Database(str(tmp_path), False, KODcoding(INITIAL_KOD), report=ignore_problems)


def test_read_db_definition_without_crostru_raises_value_error(tmp_path: Path) -> None:
    db = Database(str(tmp_path), False, None, ignore_problems, files=())

    with pytest.raises(ValueError, match="CroStru is not open, so it has no database definition"):
        db.read_db_definition()


def test_decode_db_definition_rejects_a_record_number_crostru_does_not_hold(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [], kod=random_kod(seed=1))

    for seed in range(100, 150):
        with Database(dbdir, False, KODcoding(random_kod(seed=seed)), report=ignore_problems) as db:
            assert db.stru is not None
            dbinfo = db.stru.readrec(1)
            assert dbinfo is not None
            with pytest.raises(ValueError):
                db.decode_db_definition(dbinfo[1:])


def test_export_passes_over_a_fifo_named_like_the_index_instead_of_blocking(tmp_path: Path) -> None:
    dbdir = Path(write_database(tmp_path / "db", []))
    os.mkfifo(dbdir / "CroIndex.dat")
    (dbdir / "CroIndex.tad").write_bytes(bytes(8))

    result = run_command("cli", ["export", "--csv", "-o", str(tmp_path / "out"), str(dbdir)], timeout=60)

    assert result.returncode == 0, result.stderr
    assert "warning: unreadable_file: CroIndex.dat" in result.stderr


def test_a_duplicate_definition_key_is_reported_through_report(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    dbdir = database_with_extra_definition_key(tmp_path / "db", "BankName", b"again")
    problems: list[Diagnostic] = []

    with Database(dbdir, False, KODcoding(INITIAL_KOD), report=problems.append) as db:
        db.read_db_definition()

    assert problems == [
        Diagnostic(DiagnosticKind.UNEXPECTED_STRUCTURE, "duplicate key: BankName", file="CroStru.dat", record=1)
    ]
    assert capfd.readouterr().err == ""


def test_a_reference_record_not_starting_with_4_is_reported(tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    stru = stru_records_from_test_db()
    dbinfo = stru[0]
    assert dbinfo is not None
    stru.append(b"\x05value")
    reference = len(stru)
    name = b"Referenced"
    stru[0] = dbinfo + bytes([len(name)]) + name + struct.pack("<L", reference)
    write_datafile(tmp_path, "Stru", stru)
    write_datafile(tmp_path, "Bank", [])
    problems: list[Diagnostic] = []

    with Database(str(tmp_path), False, KODcoding(INITIAL_KOD), report=problems.append) as db:
        definition = db.read_db_definition()

    assert definition["Referenced"] == b"value"
    assert problems == [
        Diagnostic(
            DiagnosticKind.UNEXPECTED_STRUCTURE,
            "expected refdata to start with 0x04",
            file="CroStru.dat",
            record=reference,
        )
    ]
    assert capfd.readouterr().err == ""


def test_database_opens_only_the_files_it_is_asked_for(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [], index_records=[])

    with Database(dbdir, False, KODcoding(INITIAL_KOD), report=ignore_problems, files=("Stru", "Bank")) as db:
        assert (db.stru is not None, db.bank is not None, db.index, db.sys) == (True, True, None, None)


def test_a_corrupt_index_header_does_not_stop_a_database_that_does_not_open_the_index(tmp_path: Path) -> None:
    dbdir = Path(write_database(tmp_path / "db", []))
    (dbdir / "CroIndex.dat").write_bytes(b"garbage")
    (dbdir / "CroIndex.tad").write_bytes(bytes(8))

    with Database(str(dbdir), False, KODcoding(INITIAL_KOD), report=ignore_problems, files=("Stru", "Bank")) as db:
        assert "Base001" in db.read_db_definition()


def test_a_database_made_from_open_datafiles_reads_its_definition(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [])
    kod = KODcoding(INITIAL_KOD)
    problems: list[Diagnostic] = []
    with Database(dbdir, False, kod, report=problems.append, files=("Stru", "Bank")) as opened:
        assert opened.stru is not None
        assert opened.bank is not None
        db = Database.from_datafiles(dbdir, False, kod, opened.stru, opened.bank, problems.append)

        assert (db.stru, db.bank, db.index, db.sys) == (opened.stru, opened.bank, None, None)
        assert "Base001" in db.read_db_definition()
    assert problems == []


class StopReading(Exception):
    """What a report callback raises to stop a reader."""


def test_a_report_callback_that_raises_once_stops_dump_db_table_defs(tmp_path: Path) -> None:
    dbdir = table_definition_key_before_base001(tmp_path / "db", "Base009", erdgeist_table_definition())
    problems: list[Diagnostic] = []

    def stop_at_base009(diagnostic: Diagnostic) -> None:
        problems.append(diagnostic)
        if diagnostic.message.startswith("Base009: ") and len(problems) == 2:
            raise StopReading

    with Database(dbdir, False, KODcoding(INITIAL_KOD), report=stop_at_base009) as db, pytest.raises(StopReading):
        db.dump_db_table_defs(argparse.Namespace(verbose=False, ascdump=False))

    assert [problem.message for problem in problems] == [
        "Base000: FieldDefinition Section 2 not marked with a 2",
        "Base009: FieldDefinition Section 2 not marked with a 2",
    ]


def test_dump_db_table_defs_reports_a_truncated_table_definition_and_goes_on(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dbdir = table_definition_key_before_base001(tmp_path / "db", "Base009", b"\x01")
    problems: list[Diagnostic] = []

    with Database(dbdir, False, KODcoding(INITIAL_KOD), report=problems.append) as db:
        db.dump_db_table_defs(argparse.Namespace(verbose=False, ascdump=False))

    assert problems[1] == Diagnostic(
        DiagnosticKind.UNDECODABLE_TABLE,
        "Base009 cannot be decoded and is left out: EOFError",
        file="CroStru.dat",
    )
    assert "== Base001 ==" in capsys.readouterr().out
