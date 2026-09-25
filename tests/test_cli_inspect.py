# ABOUTME: Tests for the inspect subcommands: their output is crodump's, and they open only the files they read.
# ABOUTME: They run inspect on test_data and on crafted or damaged copies, in this process or as a subprocess.
import io
import shutil
from pathlib import Path
from typing import cast

import pytest
from cli import run_command, run_in_process
from cronos_builder import TEST_DB, write_database

from cronos_extract import NotACronosFile
from cronos_extract._cli import inspect
from cronos_extract._cli.report import Failure
from cronos_extract.Database import KOD_HINT, Database
from cronos_extract.koddecoder import INITIAL_KOD, KODcoding

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
        (["strudump", "-v", "-a", RELATIVE_TEST_DB], "crodump-strudump"),
        (["crodump", "-v", RELATIVE_TEST_DB], "crodump-crodump"),
        (["recdump", RELATIVE_TEST_DB], "crodump-recdump"),
        (["recdump", "--stats", "--stru", RELATIVE_TEST_DB], "crodump-recdump-stats-stru"),
        (["kodump", "-s", "1", "-l", "64", f"{RELATIVE_TEST_DB}/CroStru.dat"], "crodump-kodump-shift1"),
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


def test_a_damaged_file_the_subcommand_does_not_read_is_one_warning(
    damaged_index_db: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(REPO_ROOT)

    assert run_inspect("strudump", "-v", "-a", str(damaged_index_db)) == 0

    captured = capsys.readouterr()
    assert captured.out == golden_stdout("crodump-strudump")
    warnings = [line for line in captured.err.splitlines() if line.startswith("warning: ")]
    assert len(warnings) == 1
    assert warnings[0].startswith("warning: unreadable_file: CroIndex.dat: the file cannot be read and is left out: ")


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
    assert "WARN: expected dbinfo to start with 0x03" in capsys.readouterr().err


def definition_hex() -> str:
    with Database(str(TEST_DB), False, KODcoding(INITIAL_KOD)) as db:
        record = cast(bytes, db.stru.readrec(1))
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


def test_strudump_of_an_undecodable_definition_exits_1_with_two_lines() -> None:
    result = run_command("cli", ["inspect", "strudump", "--nokod", str(TEST_DB)])

    assert result.returncode == 1
    assert result.stderr.splitlines() == [
        "WARN: expected dbinfo to start with 0x03",
        "Error: the database definition is cut off after 0 keys",
        KOD_HINT,
    ]
