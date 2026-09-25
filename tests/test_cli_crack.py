# ABOUTME: Tests for the crack subcommands, strucrack and dbcrack, which recover a database's KOD table.
# ABOUTME: They crack encrypted databases from tests/cronos_builder.py whose KOD is known, here or as a subprocess.
import argparse
from pathlib import Path

import pytest
from cli import run_command, run_in_process
from cronos_builder import (
    TEST_TABLE_ID,
    UNUSED_TABLE_ID,
    bank_record,
    corrupt_compressed_record,
    crackable_database,
    random_kod,
    write_database,
    write_datafile,
)

from cronos_extract import NotACronosFile
from cronos_extract._cli import crack
from cronos_extract.koddecoder import KODcoding

KOD = random_kod(seed=7)
KOD_LINE = bytes(KOD).hex() + "\n"
PERSON_FIELDS = [b"42", b"Hammersley", b"", b"1240315", b"0930", b"", b"", b"", b"", b"", b""]


@pytest.fixture
def encrypted_db(tmp_path: Path) -> str:
    return crackable_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, PERSON_FIELDS)], KOD)


@pytest.fixture
def uncrackable_db(tmp_path: Path) -> str:
    """A database with too few records for either crack method to resolve every KOD entry."""
    return write_database(
        tmp_path / "db", [bank_record(TEST_TABLE_ID, PERSON_FIELDS)], KOD, index_records=[bytes(12)] * 3
    )


def run_crack(*args: str) -> int:
    return run_in_process(crack.add_parser, ["crack", *args])


def crack_args(*args: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="cronos-extract")
    crack.add_parser(parser.add_subparsers(required=True))
    return parser.parse_args(["crack", *args])


def derive_from_stru(dbdir: str, *options: str) -> list[int] | None:
    """Run derive_kod_from_stru on `dbdir` with strucrack's `options`, returning the KOD table or None."""
    args = crack_args("strucrack", *options, dbdir)
    with crack.raw_datafile(dbdir, "Sys" if args.sys else "Stru") as table:
        return crack.derive_kod_from_stru(table, args)


def fix_switch(entry: int, shift: int, plain: int) -> str:
    """Return a -f value that forces KOD[entry] so that `entry` decodes to `plain` at `shift`."""
    return f"{entry:02x}{shift:02x}{plain:02x}"


def test_strucrack_prints_the_dump_and_kod_on_stdout_and_the_key_message_on_stderr(
    encrypted_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_crack("strucrack", "--noninteractive", encrypted_db) == 0

    captured = capsys.readouterr()
    assert "Processing record number" in captured.out
    assert captured.out.endswith(KOD_LINE)
    assert captured.err == (
        "Pass the following database key to cronos-extract export --kod or inspect --kod to decrypt the database:\n"
    )


@pytest.mark.parametrize("method", ["strucrack", "dbcrack"])
def test_silent_prints_only_the_kod(encrypted_db: str, method: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_crack(method, "--silent", encrypted_db) == 0

    assert capsys.readouterr() == (KOD_LINE, "")


def test_an_unresolved_interactive_strucrack_prints_the_estimate_on_stderr_and_exits_0(
    uncrackable_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_crack("strucrack", "--color", uncrackable_db) == 0

    captured = capsys.readouterr()
    assert "Processing record number" in captured.out
    assert "Ambiguous result when cracking." in captured.err
    assert "KOD estimate:" in captured.err
    assert "cronos-extract crack strucrack -f f103=B  -f f10342" in captured.err
    assert "\x1b" not in captured.err
    assert "Ambiguous" not in captured.out


def test_an_unresolved_noninteractive_strucrack_exits_1(
    uncrackable_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_crack("strucrack", "--noninteractive", uncrackable_db) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Automatic cracking failed" in captured.err
    assert "cronos-extract crack strucrack without --noninteractive" in captured.err


def test_an_unresolved_silent_noninteractive_strucrack_prints_nothing(
    uncrackable_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_crack("strucrack", "--noninteractive", "--silent", uncrackable_db) == 1

    assert capsys.readouterr() == ("", "")


def test_an_unresolved_dbcrack_exits_1_with_the_message_on_stderr(
    uncrackable_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_crack("dbcrack", uncrackable_db) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Ambiguous result when cracking." in captured.err
    assert "too few CroBank/CroIndex records" in captured.err


def test_strucrack_reads_only_crostru(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dbdir = tmp_path / "db"
    write_datafile(dbdir, "Stru", [bytes(256)] * 8, KOD)
    (dbdir / "CroIndex.dat").write_bytes(bytes(10))
    (dbdir / "CroIndex.tad").write_bytes(bytes(8))

    assert run_crack("strucrack", "--silent", str(dbdir)) == 0

    assert capsys.readouterr().out == KOD_LINE


def test_dbcrack_needs_croindex(tmp_path: Path) -> None:
    write_datafile(tmp_path / "db", "Bank", [bank_record(TEST_TABLE_ID, PERSON_FIELDS)], KOD)

    with pytest.raises(NotACronosFile) as failed:
        run_crack("dbcrack", str(tmp_path / "db"))

    assert "CroIndex" in str(failed.value)


def test_strucrack_sys_needs_crosys(encrypted_db: str) -> None:
    with pytest.raises(NotACronosFile) as failed:
        run_crack("strucrack", "--sys", encrypted_db)

    assert "CroSys" in str(failed.value)


def test_the_interactive_dump_skips_a_record_it_cannot_read(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    zero_byte_records = [bytes([UNUSED_TABLE_ID]) + bytes(11)] * 300
    looks_compressed = KODcoding(KOD).decode(4 + 8 + 1, corrupt_compressed_record())
    dbdir = write_database(
        tmp_path / "db",
        [bank_record(TEST_TABLE_ID, PERSON_FIELDS), *zero_byte_records],
        KOD,
        extra_stru_records=[*[bytes(256)] * 8, looks_compressed],
        index_records=zero_byte_records,
    )

    assert run_crack("strucrack", dbdir) == 0

    captured = capsys.readouterr()
    assert "Processing record number" in captured.out
    assert captured.out.endswith(KOD_LINE)


def test_text_that_does_not_fit_the_database_raises_crack_input_error(tmp_path: Path) -> None:
    write_datafile(tmp_path / "db", "Stru", [bytes(256)] * 8, KOD)

    with pytest.raises(crack.CrackInputError) as failed:
        derive_from_stru(str(tmp_path / "db"), "--text=99:0:0:a")

    assert "record 99 doesn't exist" in str(failed.value)


def test_a_fix_that_cannot_be_parsed_is_a_usage_error(encrypted_db: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        run_crack("strucrack", "-f", "0000zz", encrypted_db)

    assert stopped.value.code == 2
    assert "Non-hexadecimal digit" in capsys.readouterr().err


def test_a_resolved_crack_exits_0_with_only_the_kod_on_stdout(encrypted_db: str) -> None:
    result = run_command("cli", ["crack", "dbcrack", "--silent", encrypted_db])

    assert result.returncode == 0
    assert (result.stdout, result.stderr) == (KOD_LINE, "")


@pytest.mark.parametrize(
    "args",
    [["strucrack", "--noninteractive"], ["dbcrack"], ["dbcrack", "--silent"]],
    ids=["strucrack", "dbcrack", "silent"],
)
def test_a_crack_that_fails_exits_1(uncrackable_db: str, args: list[str]) -> None:
    result = run_command("cli", ["crack", *args, uncrackable_db])

    assert result.returncode == 1
    assert result.stdout == ""


def test_a_crack_missing_its_file_exits_1_with_an_error_line(tmp_path: Path) -> None:
    write_datafile(tmp_path / "db", "Bank", [bank_record(TEST_TABLE_ID, PERSON_FIELDS)], KOD)

    result = run_command("cli", ["crack", "dbcrack", "--silent", str(tmp_path / "db")])

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith("Error: ")
    assert "CroIndex" in result.stderr


@pytest.mark.parametrize(
    "args", [["-f", "0000zz"], ["--text=99:0:0:a"], ["--width", "0"]], ids=["fix", "text", "width"]
)
def test_crack_input_that_does_not_fit_exits_2(encrypted_db: str, args: list[str]) -> None:
    result = run_command("cli", ["crack", "strucrack", *args, encrypted_db])

    assert result.returncode == 2
    assert "Traceback" not in result.stderr
