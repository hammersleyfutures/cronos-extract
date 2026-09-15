# ABOUTME: Tests for recovering a database's KOD table with strucrack and dbcrack, directly and through the commands.
# ABOUTME: Uses encrypted databases from tests/cronos_builder.py whose KOD table is known.
from pathlib import Path

import pytest
from cli import run_command
from cronos_builder import (
    TEST_TABLE_ID,
    bank_record,
    crackable_database,
    random_kod,
    write_database,
    write_datafile,
)

from cronos_extract.crodump import build_parser, crack_kod, derive_kod_from_bank_and_index, derive_kod_from_stru
from cronos_extract.Database import Database

KOD = random_kod(seed=7)
PERSON_FIELDS = [b"42", b"Hammersley", b"", b"1240315", b"0930", b"", b"", b"", b"", b"", b""]
CRACK_FLAGS = ["--strucrack", "--dbcrack"]


@pytest.fixture
def encrypted_db(tmp_path: Path) -> str:
    return crackable_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, PERSON_FIELDS)], KOD)


@pytest.fixture
def uncrackable_db(tmp_path: Path) -> str:
    """A database with too few records for either crack method to resolve every KOD entry."""
    return write_database(
        tmp_path / "db", [bank_record(TEST_TABLE_ID, PERSON_FIELDS)], KOD, index_records=[bytes(12)] * 3
    )


def derive_from_stru(dbdir: str, *options: str):
    """Run derive_kod_from_stru on `dbdir` with strucrack's `options`, returning the KOD table or None."""
    args = build_parser().parse_args(["strucrack", *options, dbdir])
    with Database(dbdir, False, None) as db:
        return derive_kod_from_stru(db, args)


def derive_from_bank_and_index(dbdir: str, *options: str):
    """Run derive_kod_from_bank_and_index on `dbdir` with dbcrack's `options`, returning the KOD table or None."""
    args = build_parser().parse_args(["dbcrack", *options, dbdir])
    with Database(dbdir, False, None) as db:
        return derive_kod_from_bank_and_index(db, args)


def fix_switch(entry: int, shift: int, plain: int) -> str:
    """Return a -f value that forces KOD[entry] so that `entry` decodes to `plain` at `shift`."""
    return f"{entry:02x}{shift:02x}{plain:02x}"


def test_strucrack_rejects_a_kod_with_duplicate_values(encrypted_db: str, capsys: pytest.CaptureFixture[str]) -> None:
    # Force KOD[0] to the value of KOD[1], so two entries map to the same value.
    duplicate_fix = fix_switch(0, 0, KOD[1])

    assert derive_from_stru(encrypted_db, "-f", duplicate_fix) is None
    output = capsys.readouterr().out
    assert "Use the following database key" not in output
    assert "entries unsolved" in output


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

    output = capsys.readouterr().out
    assert "Ambigous result when cracking. 1 entries unsolved" in output
    assert "[01] =>" in output


def test_strucrack_colours_only_forced_entries_as_forced(
    db_with_counts_of_255: str, capsys: pytest.CaptureFixture[str]
) -> None:
    forced_colour = "\033[32m"

    assert derive_from_stru(db_with_counts_of_255, "--color") == KOD
    assert forced_colour not in capsys.readouterr().out


def test_strucrack_returns_none_when_entries_stay_unresolved(uncrackable_db: str) -> None:
    assert derive_from_stru(uncrackable_db) is None


def test_strucrack_noninteractive_stops_with_a_message_when_cracking_fails(uncrackable_db: str) -> None:
    result = run_command("crodump", ["strucrack", "--noninteractive", uncrackable_db])

    assert result.returncode == 1
    assert "Processing record number" not in result.stdout
    assert "entries unsolved" in result.stderr


def test_strucrack_noninteractive_prints_nothing_when_silent(
    uncrackable_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert derive_from_stru(uncrackable_db, "--silent", "--noninteractive") is None
    assert capsys.readouterr().out == ""


def kod_estimate(output: str) -> str:
    """Return the hex KOD estimate that strucrack prints when entries stay unresolved."""
    lines = output.splitlines()
    return lines[lines.index("KOD estimate:") + 1]


def test_strucrack_keeps_entries_that_shift_rows_without_data_do_not_claim(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # 200 zero bytes in record 1 cover shifts 1..200 only, and KOD[0] is one of them.
    assert 1 <= KOD[0] <= 200
    write_datafile(tmp_path / "db", "Stru", [bytes(200)], KOD)

    assert derive_from_stru(str(tmp_path / "db")) is None
    assert kod_estimate(capsys.readouterr().out)[0:2] == f"{KOD[0]:02x}"


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
    assert kod_estimate(capsys.readouterr().out)[2 * entry : 2 * entry + 2] == f"{strong_shift:02x}"


def test_dbcrack_returns_none_when_the_kod_is_not_a_permutation(
    uncrackable_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert derive_from_bank_and_index(uncrackable_db) is None
    assert "entries unsolved" in capsys.readouterr().out


def test_dbcrack_reads_the_last_record_of_each_file(tmp_path: Path) -> None:
    # dbcrack reads the fourth byte of record i for shift i + 3. CroBank records 1..253 cover shifts 4..255 and 0,
    # and the last three CroIndex records, 254..256, cover shifts 1..3, so every shift is covered exactly once.
    dbdir = write_database(tmp_path / "db", [bytes(12)] * 253, KOD, index_records=[None] * 253 + [bytes(12)] * 3)

    assert derive_from_bank_and_index(dbdir, "--silent") == KOD


@pytest.mark.parametrize("options", [[], ["-f", fix_switch(0, 0, KOD[1])]], ids=["cracked", "duplicate-fix"])
def test_strucrack_prints_nothing_when_silent(
    encrypted_db: str, options: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    derive_from_stru(encrypted_db, "--silent", *options)

    assert capsys.readouterr().out == ""


def test_strucrack_prints_nothing_about_a_missing_stru_file_when_silent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_datafile(tmp_path / "db", "Bank", [bank_record(TEST_TABLE_ID, PERSON_FIELDS)], KOD)

    assert derive_from_stru(str(tmp_path / "db"), "--silent") is None
    assert capsys.readouterr().out == ""


def test_dbcrack_prints_nothing_about_a_missing_index_file_when_silent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dbdir = write_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, PERSON_FIELDS)], KOD)

    assert derive_from_bank_and_index(dbdir, "--silent") is None
    assert capsys.readouterr().out == ""


def test_croconvert_output_holds_no_cracking_dump(encrypted_db: str) -> None:
    result = run_command("croconvert", ["--strucrack", "-t", "postgres", encrypted_db])

    assert result.returncode == 0, result.stderr
    assert "Processing record number" not in result.stdout


@pytest.mark.parametrize("method", ["strucrack", "dbcrack"])
def test_crack_kod_recovers_the_database_kod(encrypted_db: str, method: str) -> None:
    assert crack_kod(method, encrypted_db, False) == KOD


@pytest.mark.parametrize("flag", CRACK_FLAGS)
def test_croconvert_decodes_with_a_cracked_kod(encrypted_db: str, flag: str) -> None:
    result = run_command("croconvert", [flag, "-t", "postgres", encrypted_db])

    assert result.returncode == 0, result.stderr
    assert "'Hammersley'" in result.stdout


@pytest.mark.parametrize("flag", CRACK_FLAGS)
def test_crodump_decodes_with_a_cracked_kod(encrypted_db: str, flag: str) -> None:
    result = run_command("crodump", [flag, "strudump", encrypted_db])

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
    result = run_command("crodump", ["strucrack", "-f", fix, encrypted_db])

    assert result.returncode != 0
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
    result = run_command("crodump", ["strucrack", f"--text={text}", str(tmp_path / "db")])

    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert message in result.stderr


@pytest.mark.parametrize("width", ["0", "-3"])
def test_strucrack_rejects_a_width_that_is_not_positive(encrypted_db: str, width: str) -> None:
    result = run_command("crodump", ["strucrack", "--width", width, encrypted_db])

    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert "must be a positive number" in result.stderr


def test_crodump_crack_flag_needs_a_database_subcommand() -> None:
    result = run_command("crodump", ["--strucrack", "kodump", "--help"])

    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("flag", CRACK_FLAGS)
def test_dumpdbfields_decodes_with_a_cracked_kod(encrypted_db: str, flag: str) -> None:
    result = run_command("dumpdbfields", [flag, encrypted_db])

    assert result.returncode == 0, result.stderr
    assert "-- Hammersley" in result.stdout
