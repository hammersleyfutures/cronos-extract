# ABOUTME: Tests for the crack subcommands, strucrack and dbcrack, which recover a database's KOD table.
# ABOUTME: They crack encrypted databases from tests/cronos_builder.py whose KOD is known, here or as a subprocess.
import argparse
import json
from pathlib import Path
from typing import Any, cast

import pytest
from cli import run_command, run_in_process
from cronos_builder import (
    TEST_TABLE_ID,
    UNUSED_TABLE_ID,
    bank_record,
    compressed_record,
    corrupt_compressed_record,
    crackable_database,
    random_kod,
    stru_records_from_test_db,
    write_database,
    write_datafile,
)

from cronos_extract import Kod, NotACronosFile, crack_kod
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


def derive_from_bank_and_index(dbdir: str, *options: str) -> list[int] | None:
    """Run derive_kod_from_bank_and_index on `dbdir` with dbcrack's `options`, returning the KOD table or None."""
    args = crack_args("dbcrack", *options, dbdir)
    with crack.raw_datafile(dbdir, "Bank") as bank, crack.raw_datafile(dbdir, "Index") as index:
        return crack.derive_kod_from_bank_and_index(bank, index, args)


def kod_estimate(output: str) -> str:
    """Return the hex KOD estimate that strucrack prints on stderr when entries stay unresolved."""
    lines = output.splitlines()
    return lines[lines.index("KOD estimate:") + 1]


def test_strucrack_rejects_a_kod_with_duplicate_values(encrypted_db: str, capsys: pytest.CaptureFixture[str]) -> None:
    # Force KOD[0] to the value of KOD[1], so two entries map to the same value.
    duplicate_fix = fix_switch(0, 0, KOD[1])

    assert derive_from_stru(encrypted_db, "-f", duplicate_fix) is None
    captured = capsys.readouterr()
    assert "Pass the following database key" not in captured.err
    assert "entries unsolved" in captured.err


@pytest.fixture
def db_with_counts_of_255(tmp_path: Path) -> str:
    """A database whose CroStru makes every shift see its zero byte exactly 255 times."""
    write_datafile(tmp_path / "db", "Stru", [bytes(255 * 256)], KOD)
    return str(tmp_path / "db")


def test_strucrack_does_not_treat_a_count_of_255_as_forced(
    db_with_counts_of_255: str, capsys: pytest.CaptureFixture[str]
) -> None:
    # Force KOD[0] to the value of KOD[1]; entry 1 was only counted, so it is the duplicate that is unsolved.
    assert derive_from_stru(db_with_counts_of_255, "-f", fix_switch(0, 0, KOD[1])) is None

    err = capsys.readouterr().err
    assert "Ambiguous result when cracking. 1 entries unsolved" in err
    assert "[01] =>" in err


def test_strucrack_colours_only_forced_entries_as_forced(
    db_with_counts_of_255: str, capsys: pytest.CaptureFixture[str]
) -> None:
    forced_colour = "\033[32m"

    assert derive_from_stru(db_with_counts_of_255, "--color") == KOD
    assert forced_colour not in capsys.readouterr().out


def test_strucrack_returns_none_when_entries_stay_unresolved(uncrackable_db: str) -> None:
    assert derive_from_stru(uncrackable_db) is None


def test_strucrack_noninteractive_stops_with_a_message_when_cracking_fails(uncrackable_db: str) -> None:
    result = run_command("cli", ["crack", "strucrack", "--noninteractive", uncrackable_db])

    assert result.returncode == 1
    assert "Processing record number" not in result.stdout
    assert "entries unsolved" in result.stderr


def test_strucrack_noninteractive_prints_nothing_when_silent(
    uncrackable_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert derive_from_stru(uncrackable_db, "--silent", "--noninteractive") is None
    assert capsys.readouterr() == ("", "")


def test_strucrack_keeps_entries_that_shift_rows_without_data_do_not_claim(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # 200 zero bytes in record 1 cover shifts 1..200 only, and KOD[0] is one of them.
    assert 1 <= KOD[0] <= 200
    write_datafile(tmp_path / "db", "Stru", [bytes(200)], KOD)

    assert derive_from_stru(str(tmp_path / "db")) is None
    assert kod_estimate(capsys.readouterr().err)[0:2] == f"{KOD[0]:02x}"


def test_strucrack_keeps_the_stronger_of_two_shift_rows_claiming_one_entry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    strong_shift, weak_shift = 100, 230
    entry = KOD.index(strong_shift)
    # Records 1..8 hold 200 zero bytes, so shift 100 sees `entry` 8 times. Record 9 puts one byte on shift 230
    # that also encrypts to `entry`, so shift 230's most common byte is `entry` with a count of 1.
    weak_claim = bytes(weak_shift - 9) + bytes([(strong_shift - weak_shift) % 256])
    write_datafile(tmp_path / "db", "Stru", [*[bytes(200)] * 8, weak_claim], KOD)

    assert derive_from_stru(str(tmp_path / "db")) is None
    assert kod_estimate(capsys.readouterr().err)[2 * entry : 2 * entry + 2] == f"{strong_shift:02x}"


def test_dbcrack_returns_none_when_the_kod_is_not_a_permutation(
    uncrackable_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert derive_from_bank_and_index(uncrackable_db) is None
    assert "entries unsolved" in capsys.readouterr().err


def test_dbcrack_reads_the_last_record_of_each_file(tmp_path: Path) -> None:
    # dbcrack reads the fourth byte of record i for shift i + 3. CroBank records 1..253 cover shifts 4..255 and 0,
    # and the last three CroIndex records, 254..256, cover shifts 1..3, so every shift is covered exactly once.
    dbdir = write_database(tmp_path / "db", [bytes(12)] * 253, KOD, index_records=[None] * 253 + [bytes(12)] * 3)

    assert derive_from_bank_and_index(dbdir, "--silent") == KOD


@pytest.mark.parametrize(
    ("options", "expected"),
    [([], (KOD_LINE, "")), (["-f", fix_switch(0, 0, KOD[1])], ("", ""))],
    ids=["cracked", "duplicate-fix"],
)
def test_silent_strucrack_prints_only_a_resolved_kod(
    encrypted_db: str, options: list[str], expected: tuple[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    derive_from_stru(encrypted_db, "--silent", *options)

    assert capsys.readouterr() == expected


def test_strucrack_missing_stru_file_raises_even_when_silent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_datafile(tmp_path / "db", "Bank", [bank_record(TEST_TABLE_ID, PERSON_FIELDS)], KOD)

    with pytest.raises(NotACronosFile):
        derive_from_stru(str(tmp_path / "db"), "--silent")
    assert capsys.readouterr().out == ""


def test_dbcrack_missing_index_file_raises_even_when_silent(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dbdir = write_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, PERSON_FIELDS)], KOD)

    with pytest.raises(NotACronosFile):
        derive_from_bank_and_index(dbdir, "--silent")
    assert capsys.readouterr().out == ""


def test_export_output_holds_no_cracking_dump(encrypted_db: str) -> None:
    result = run_command("cli", ["export", "--postgres", "--crack", "strucrack", encrypted_db])

    assert result.returncode == 0, result.stderr
    assert "Processing record number" not in result.stdout


@pytest.mark.parametrize("method", ["strucrack", "dbcrack"])
def test_crack_kod_recovers_the_database_kod(encrypted_db: str, method: str) -> None:
    assert crack_kod(encrypted_db, cast(Any, method)) == Kod.from_table(KOD)


@pytest.mark.parametrize("method", ["strucrack", "dbcrack"])
def test_export_decodes_with_a_cracked_kod(encrypted_db: str, method: str) -> None:
    result = run_command("cli", ["export", "--postgres", "--crack", method, encrypted_db])

    assert result.returncode == 0, result.stderr
    assert "'Hammersley'" in result.stdout


@pytest.mark.parametrize("method", ["strucrack", "dbcrack"])
def test_inspect_decodes_with_a_cracked_kod(encrypted_db: str, method: str) -> None:
    result = run_command("cli", ["inspect", "strudump", "--crack", method, encrypted_db])

    assert result.returncode == 0, result.stderr
    assert "'erdgeist'" in result.stdout


def test_strucrack_text_plaintext_may_contain_colons(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_datafile(tmp_path / "db", "Stru", [bytes(256)] * 8, KOD)

    derive_from_stru(str(tmp_path / "db"), "-t", "0:0:0:a:b")

    assert "00000 a:b" in capsys.readouterr().out


def suggested_switches(output: str, found: str) -> list[str]:
    """Return the -f values strucrack suggests after the line that starts with `found`."""
    lines = output.splitlines()
    start = next(n for n, line in enumerate(lines) if line.startswith(found))
    return lines[start + 2].split()[1::2]


@pytest.mark.parametrize(
    ("record", "found", "switch_count"),
    [
        # "Version" is suggested from one byte before the match, which lies before the record.
        (b"Versiox" + bytes(20), "Found Versiox", 7),
        # "Системный номер" is suggested from 7 bytes before to 5 bytes after the match, past the record's end.
        (bytes(10) + "Системный номеж".encode("cp1251"), "Found Системный", 25 - 3),
    ],
    ids=["match-at-record-start", "match-at-record-end"],
)
def test_strucrack_suggests_switches_only_for_bytes_inside_the_record(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], record: bytes, found: str, switch_count: int
) -> None:
    write_datafile(tmp_path / "db", "Stru", [*[bytes(256)] * 8, record], KOD)

    derive_from_stru(str(tmp_path / "db"))

    assert len(suggested_switches(capsys.readouterr().out, found)) == switch_count


def test_strucrack_applies_a_fix_given_as_a_character(encrypted_db: str) -> None:
    # Force KOD[5] to its true value, so that encrypted byte 05 decodes to "A" at this shift.
    shift = (KOD[5] - ord("A")) % 256

    assert derive_from_stru(encrypted_db, "-f", f"05{shift:02x}=A") == KOD


@pytest.mark.parametrize(
    ("fix", "message"),
    [
        ("0000=中", "can't be encoded as CP-1251"),
        ("0000zz", "Non-hexadecimal digit"),
        ("00000", "expected 6 characters"),
    ],
)
def test_strucrack_rejects_an_invalid_fix(encrypted_db: str, fix: str, message: str) -> None:
    result = run_command("cli", ["crack", "strucrack", "-f", fix, encrypted_db])

    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert message in result.stderr


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("0:0:0", "invalid text '0:0:0'"),
        ("0:0:x:abc", "invalid text '0:0:x:abc'"),
        ("-1:0:0:a", "invalid text '-1:0:0:a'"),
        ("0:0:0:中", "can't be encoded as CP-1251"),
        ("99:0:0:a", "record 99 doesn't exist"),
        ("8:0:0:a", "record 8 is deleted or empty"),
        ("9:0:0:a", "record 9 is deleted or empty"),
        ("0:250:0:abcdefgh", "runs past the end of record 0"),
    ],
    ids=["no-plaintext", "not-a-number", "negative", "not-cp1251", "no-such-record", "deleted", "empty", "too-long"],
)
def test_strucrack_rejects_text_that_does_not_fit_the_database(tmp_path: Path, text: str, message: str) -> None:
    # Records 0..7 hold 256 zero bytes each, record 8 is deleted and record 9 is empty.
    write_datafile(tmp_path / "db", "Stru", [*[bytes(256)] * 8, None, b""], KOD)

    # --text=value, so that argparse takes a value starting with "-" as the value, not as an option
    result = run_command("cli", ["crack", "strucrack", f"--text={text}", str(tmp_path / "db")])

    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert message in result.stderr


@pytest.mark.parametrize("width", ["0", "-3"])
def test_strucrack_rejects_a_width_that_is_not_positive(encrypted_db: str, width: str) -> None:
    result = run_command("cli", ["crack", "strucrack", "--width", width, encrypted_db])

    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert "must be a positive number" in result.stderr


def test_kodump_has_no_crack_option() -> None:
    result = run_command("cli", ["inspect", "kodump", "--crack", "strucrack"])

    assert result.returncode == 2
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("method", ["strucrack", "dbcrack"])
def test_jsonl_export_decodes_with_a_cracked_kod(encrypted_db: str, method: str) -> None:
    result = run_command("cli", ["export", "--jsonl", "--crack", method, encrypted_db])

    assert result.returncode == 0, result.stderr
    records = [json.loads(line) for line in result.stdout.splitlines()]
    assert any(
        field["value"] == "Hammersley" for record in records if record["type"] == "record" for field in record["fields"]
    ), result.stdout


def test_noninteractive_strucrack_skips_a_stru_record_it_cannot_read(tmp_path: Path) -> None:
    zero_byte_records = [bytes([UNUSED_TABLE_ID]) + bytes(11)] * 300
    looks_compressed = KODcoding(KOD).decode(4 + 8 + 1, corrupt_compressed_record())
    dbdir = write_database(
        tmp_path / "db",
        [bank_record(TEST_TABLE_ID, PERSON_FIELDS), *zero_byte_records],
        KOD,
        extra_stru_records=[*[bytes(256)] * 8, looks_compressed],
        index_records=zero_byte_records,
    )

    result = run_command("cli", ["crack", "strucrack", "--noninteractive", "--silent", dbdir])

    assert result.returncode == 0, result.stderr
    assert result.stdout == KOD_LINE


def test_strucrack_reports_a_crostru_checksum_mismatch_by_kind(tmp_path: Path) -> None:
    records = [*stru_records_from_test_db(), compressed_record(b"x" * 40, wrong_checksums={0})]
    write_datafile(tmp_path, "Stru", records, kod=None)

    result = run_command("cli", ["crack", "strucrack", f"--text={len(records) - 1}:0:0:x", str(tmp_path)])

    assert result.returncode == 0, result.stderr
    lines = result.stderr.splitlines()
    assert any(line.startswith("warning: checksum_mismatch: CroStru.dat record ") for line in lines), result.stderr
    assert not any("unexpected_structure" in line for line in lines), result.stderr
