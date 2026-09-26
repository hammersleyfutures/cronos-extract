# ABOUTME: Tests for the inspect subcommands: their output matches the golden files, and they open only what they read.
# ABOUTME: They run inspect on test_data and on crafted or damaged copies, in this process or as a subprocess.
import io
import os
import re
import shutil
import struct
from pathlib import Path
from typing import cast

import pytest
from cli import run_command, run_in_process
from cronos_builder import (
    TEST_DB,
    TEST_TABLE_FIELD_COUNT,
    TEST_TABLE_ID,
    bank_record,
    compressed_record,
    corrupt_compressed_record,
    database_with_missing_definition,
    database_with_wrong_kod_record_out_of_range,
    definition_with_extra_key,
    erdgeist_table_definition,
    ignore_problems,
    key_referencing_a_deleted_record,
    stru_records_from_test_db,
    write_database,
    write_datafile,
)

from cronos_extract import NotACronosFile
from cronos_extract._cli import inspect
from cronos_extract._cli.report import Failure
from cronos_extract.Database import KOD_HINT, Database
from cronos_extract.Datafile import Datafile
from cronos_extract.koddecoder import INITIAL_KOD, KODcoding
from cronos_extract.koddecoder import new as new_kod

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
RELATIVE_TEST_DB = "test_data/all_field_types"


def golden_stdout(name: str) -> str:
    return (GOLDEN_DIR / f"{name}.stdout").read_bytes().decode("utf-8")


def run_inspect(*args: str) -> int:
    return run_in_process(inspect.add_parser, ["inspect", *args])


@pytest.mark.parametrize(
    ("args", "golden"),
    [
        (["strudump", "-v", "-a", RELATIVE_TEST_DB], "inspect-strudump"),
        (["crodump", "-v", RELATIVE_TEST_DB], "inspect-crodump"),
        (["recdump", RELATIVE_TEST_DB], "inspect-recdump"),
        (["recdump", "--stats", "--stru", RELATIVE_TEST_DB], "inspect-recdump-stats-stru"),
        (["kodump", "-s", "1", "-l", "64", f"{RELATIVE_TEST_DB}/CroStru.dat"], "inspect-kodump-shift1"),
    ],
    ids=["strudump", "crodump", "recdump", "recdump-stats-stru", "kodump"],
)
def test_inspect_prints_what_crodump_printed(
    args: list[str], golden: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(REPO_ROOT)

    assert run_inspect(*args) == 0

    assert capsys.readouterr().out == golden_stdout(golden)


@pytest.fixture
def damaged_index_db(tmp_path: Path) -> Path:
    """A copy of TEST_DB whose CroIndex.dat is ten bytes long, too short for a file header."""
    dbdir = tmp_path / "db"
    shutil.copytree(TEST_DB, dbdir)
    (dbdir / "CroIndex.dat").write_bytes(bytes(10))
    return dbdir


def test_a_damaged_file_the_subcommand_does_not_read_is_one_unreadable_file_warning(
    damaged_index_db: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(REPO_ROOT)

    assert run_inspect("strudump", "-v", "-a", str(damaged_index_db)) == 0

    captured = capsys.readouterr()
    assert captured.out == golden_stdout("inspect-strudump")
    warnings = [line for line in captured.err.splitlines() if line.startswith("warning: ")]
    assert len(warnings) == 3
    assert warnings[0].startswith("warning: unreadable_file: CroIndex.dat: the file cannot be read and is left out: ")
    # The other two are TEST_DB's own table definition problems, which strudump reports for every copy of it.
    assert warnings[1:] == [
        f"warning: unexpected_structure: CroStru.dat: {key}: FieldDefinition Section 2 not marked with a 2"
        for key in ("Base000", "Base001")
    ]


@pytest.mark.parametrize("args", [["recdump", "--index"], ["crodump"]], ids=["recdump-index", "crodump"])
def test_a_damaged_file_the_subcommand_reads_stops_it(damaged_index_db: Path, args: list[str]) -> None:
    with pytest.raises(NotACronosFile) as failed:
        run_inspect(*args, str(damaged_index_db))

    assert "CroIndex.dat" in str(failed.value)
    assert str(damaged_index_db) in str(failed.value)


def test_strudump_needs_crostru(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [])
    (Path(dbdir) / "CroStru.dat").unlink()
    (Path(dbdir) / "CroStru.tad").unlink()

    with pytest.raises(NotACronosFile) as failed:
        run_inspect("strudump", dbdir)

    assert "CroStru.dat" in str(failed.value)
    assert dbdir in str(failed.value)


def test_strudump_of_an_undecodable_definition_fails_with_the_kod_hint(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(Failure) as failed:
        run_inspect("strudump", "--nokod", str(TEST_DB))

    assert str(failed.value) == f"the database definition is cut off after 0 keys\n{KOD_HINT}"
    assert (
        "warning: unexpected_structure: CroStru.dat record 1: expected dbinfo to start with 0x03"
        in capsys.readouterr().err
    )


def definition_hex() -> str:
    with Database(str(TEST_DB), False, KODcoding(INITIAL_KOD), report=ignore_problems) as db:
        stru = cast(Datafile, db.stru)
        record = cast(bytes, stru.readrec(1))
    return record[1:].hex()


@pytest.mark.parametrize("where", ["argument", "working-directory"])
def test_destruct_type_1_reads_keys_stored_by_reference_from_the_database(
    where: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(definition_hex().encode())))
    if where == "argument":
        args = ["destruct", "-t", "1", str(TEST_DB)]
    else:
        monkeypatch.chdir(TEST_DB)
        args = ["destruct", "-t", "1"]

    assert run_inspect(*args) == 0

    assert 'BankName             - "nowa"' in capsys.readouterr().out


def test_recdump_debug_stops_at_the_last_record(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_inspect("recdump", "--debug", str(TEST_DB)) == 0

    assert "unpack" not in capsys.readouterr().out


def test_kodump_nokod_dumps_the_bytes_undecoded(capsys: pytest.CaptureFixture[str]) -> None:
    datafile = str(TEST_DB / "CroStru.dat")

    run_inspect("kodump", "-s", "1", "-l", "16", datafile)
    decoded = capsys.readouterr().out
    run_inspect("kodump", "--nokod", "-s", "1", "-l", "16", datafile)
    long_option = capsys.readouterr().out
    run_inspect("kodump", "-n", "-s", "1", "-l", "16", datafile)

    assert capsys.readouterr().out == long_option
    assert long_option != decoded


@pytest.mark.parametrize(
    "args", [["sysdump", str(TEST_DB)], ["kodump", "--crack", "strucrack"], ["kodump", "--compact"]]
)
def test_options_and_subcommands_inspect_does_not_have_are_usage_errors(args: list[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        run_inspect(*args)

    assert stopped.value.code == 2


def test_a_damaged_file_the_subcommand_reads_exits_1_without_a_traceback(damaged_index_db: Path) -> None:
    result = run_command("cli", ["inspect", "recdump", "--index", str(damaged_index_db)])

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert result.stderr.splitlines()[-1].startswith("Error: CroIndex.dat in ")


def test_a_damaged_file_the_subcommand_does_not_read_exits_0(damaged_index_db: Path) -> None:
    result = run_command("cli", ["inspect", "strudump", str(damaged_index_db)])

    assert result.returncode == 0, result.stderr


def test_recdump_stops_at_the_last_record_even_with_debug() -> None:
    result = run_command("cli", ["inspect", "recdump", "--debug", str(TEST_DB)])

    assert result.returncode == 0, result.stderr
    assert "unpack" not in result.stdout


def test_destruct_type_1_prints_a_database_definition() -> None:
    with Database(str(TEST_DB), False, KODcoding(INITIAL_KOD), report=ignore_problems) as db:
        assert db.stru is not None
        definition_record = db.stru.readrec(1)
    assert definition_record is not None

    result = run_command("cli", ["inspect", "destruct", "-t", "1"], cwd=TEST_DB, stdin=definition_record[1:].hex())

    assert result.returncode == 0, result.stderr
    assert 'BankName             - "nowa"' in result.stdout


def test_kodump_nokod_and_n_are_the_same_option() -> None:
    datafile = str(TEST_DB / "CroStru.dat")

    long_option = run_command("cli", ["inspect", "kodump", "--nokod", "-s", "1", "-l", "16", datafile])
    short_option = run_command("cli", ["inspect", "kodump", "-n", "-s", "1", "-l", "16", datafile])

    assert long_option.returncode == 0, long_option.stderr
    assert short_option.returncode == 0, short_option.stderr
    assert long_option.stdout == short_option.stdout


def test_kodump_of_a_fifo_exits_1_without_hanging(tmp_path: Path) -> None:
    fifo = tmp_path / "CroStru.dat"
    os.mkfifo(fifo)

    result = run_command("cli", ["inspect", "kodump", str(fifo)], timeout=60)

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert result.stderr.splitlines()[-1] == "Error: CroStru.dat is not a regular file"


def test_strudump_stops_with_a_clear_message_without_crostru(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [])
    (Path(dbdir) / "CroStru.dat").unlink()
    (Path(dbdir) / "CroStru.tad").unlink()

    result = run_command("cli", ["inspect", "strudump", dbdir])

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert "CroStru.dat" in result.stderr
    assert dbdir in result.stderr


def test_strudump_stops_with_a_clear_message_for_a_key_referencing_a_deleted_record(tmp_path: Path) -> None:
    dbdir = key_referencing_a_deleted_record(tmp_path / "db", "DanglingKey")

    result = run_command("cli", ["inspect", "strudump", dbdir])

    assert result.returncode == 1
    assert result.stderr.splitlines() == [
        'Error: key "DanglingKey" refers to CroStru record 5, which is deleted',
        KOD_HINT,
    ]


def test_strudump_without_the_database_kod_stops_with_a_message() -> None:
    result = run_command("cli", ["inspect", "strudump", "--nokod", str(TEST_DB)])

    assert result.returncode == 1
    assert result.stderr.splitlines() == [
        "warning: unexpected_structure: CroStru.dat record 1: expected dbinfo to start with 0x03",
        "Error: the database definition is cut off after 0 keys",
        KOD_HINT,
    ]


def test_strudump_with_a_wrong_kod_reports_a_record_out_of_range(tmp_path: Path) -> None:
    dbdir, wrong_kod_hex = database_with_wrong_kod_record_out_of_range(tmp_path / "db")

    result = run_command("cli", ["inspect", "strudump", "--kod", wrong_kod_hex, dbdir])

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    lines = result.stderr.splitlines()
    assert len(lines) == 2
    assert re.fullmatch(
        r'Error: key ".*" refers to CroStru record \d+, which CroStru does not hold \(4 records\)', lines[0]
    )
    assert lines[1] == KOD_HINT


def test_strudump_stops_with_a_clear_message_for_a_deleted_definition_record(tmp_path: Path) -> None:
    stru_records = [None, *stru_records_from_test_db()[1:]]
    dbdir = database_with_missing_definition(tmp_path / "db", stru_records)

    result = run_command("cli", ["inspect", "strudump", dbdir])

    assert result.returncode == 1
    assert result.stderr.splitlines() == [
        "Error: CroStru record 1, which holds the database definition, is deleted",
        KOD_HINT,
    ]


def test_strudump_stops_with_a_clear_message_for_no_definition_record(tmp_path: Path) -> None:
    dbdir = database_with_missing_definition(tmp_path / "db", [])

    result = run_command("cli", ["inspect", "strudump", dbdir])

    assert result.returncode == 1
    assert result.stderr.splitlines() == [
        "Error: CroStru holds no records, so it has no database definition",
        KOD_HINT,
    ]


def test_inspect_crodump_shows_a_corrupt_compressed_record_and_dumps_the_next(tmp_path: Path) -> None:
    fields = [b""] * TEST_TABLE_FIELD_COUNT
    fields[0] = b"good"
    dbdir = write_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, fields), corrupt_compressed_record()])

    result = run_command("cli", ["inspect", "crodump", "--ascdump", dbdir])

    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr
    lines = result.stdout.splitlines()
    bank_header = next(i for i, line in enumerate(lines) if line.startswith("hdr: Bank"))
    bank_lines = lines[bank_header + 1 :]
    first, second = [line for line in bank_lines if line.startswith(("    1:", "    2:"))]
    assert "good" in first
    assert " <corrupt compressed data: " in second
    assert second.endswith(">")


def test_inspect_crodump_marks_a_record_whose_checksum_does_not_match(tmp_path: Path) -> None:
    fields = [b""] * TEST_TABLE_FIELD_COUNT
    fields[0] = b"good"
    dbdir = write_database(
        tmp_path / "db",
        [compressed_record(bank_record(TEST_TABLE_ID, fields)), compressed_record(b"bad", wrong_checksums={0})],
    )

    result = run_command("cli", ["inspect", "crodump", dbdir])

    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    bank_start = next(i for i, line in enumerate(lines) if line.startswith("hdr: Bank"))
    first, second = [line for line in lines[bank_start + 1 :] if line.startswith(("    1:", "    2:"))]
    assert not first.endswith("<checksum mismatch>")
    assert second.endswith(" <checksum mismatch>")


def test_a_short_ns1_is_reported_as_a_warning_line(tmp_path: Path) -> None:
    stru = stru_records_from_test_db()
    dbinfo = stru[0]
    assert dbinfo is not None
    assert dbinfo.count(b"\x03NS1") == 1
    stru[0] = definition_with_extra_key(dbinfo.replace(b"\x03NS1", b"\x03XS1"), "NS1", b"\x01")
    write_datafile(tmp_path, "Stru", stru)
    write_datafile(tmp_path, "Bank", [])

    result = run_command("cli", ["inspect", "strudump", str(tmp_path)])

    assert result.returncode == 0, result.stderr
    assert "warning: unexpected_structure: CroStru.dat: NS1 is unexpectedly short" in result.stderr.splitlines()


def test_an_ns1_password_holding_an_undefined_cp1251_byte_prints_with_the_replacement_character(
    tmp_path: Path,
) -> None:
    stru = stru_records_from_test_db()
    dbinfo = stru[0]
    assert dbinfo is not None
    password = b"a\x98b"
    decoded_data = struct.pack("<LLL", 0, 0, len(password)) + password
    ns1kod = new_kod()
    ns1_value = struct.pack("<BB", 0, 0) + ns1kod.encode(0, decoded_data)
    stru[0] = definition_with_extra_key(dbinfo.replace(b"\x03NS1", b"\x03XS1"), "NS1", ns1_value)
    write_datafile(tmp_path, "Stru", stru)
    write_datafile(tmp_path, "Bank", [])

    result = run_command("cli", ["inspect", "strudump", str(tmp_path)])

    assert result.returncode == 0, result.stderr
    assert "a�b" in result.stdout


def test_destruct_type_2_reports_problems_as_warning_lines() -> None:
    result = run_command("cli", ["inspect", "destruct", "-t", "2"], stdin=erdgeist_table_definition().hex())

    assert result.returncode == 0, result.stderr
    assert result.stderr.splitlines() == [
        "warning: unexpected_structure: FieldDefinition Section 2 not marked with a 2"
    ]


def test_a_hostile_duplicate_key_is_escaped_on_inspect_stderr(tmp_path: Path) -> None:
    stru = stru_records_from_test_db()
    dbinfo = stru[0]
    assert dbinfo is not None
    once = definition_with_extra_key(dbinfo, "X\x1b[31m", b"a")
    stru[0] = definition_with_extra_key(once, "X\x1b[31m", b"a")
    write_datafile(tmp_path, "Stru", stru)
    write_datafile(tmp_path, "Bank", [])

    result = run_command("cli", ["inspect", "strudump", str(tmp_path)])

    assert result.returncode == 0, result.stderr
    assert "\x1b" not in result.stderr
    assert (
        "warning: unexpected_structure: CroStru.dat record 1: duplicate key: X\\x1b[31m" in result.stderr.splitlines()
    )


def test_recdump_of_an_absent_file_fails_naming_it(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [])

    result = run_command("cli", ["inspect", "recdump", "--sys", dbdir])

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.splitlines() == [f"Error: {dbdir} has no CroSys.dat and CroSys.tad"]
