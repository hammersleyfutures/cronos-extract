# ABOUTME: Tests for the KOD and --compact options that export and inspect share, and the Kod they select.
# ABOUTME: They parse real arguments and crack real encrypted databases from tests/cronos_builder.py.
import argparse
from pathlib import Path

import pytest
from cronos_builder import TEST_TABLE_ID, bank_record, crackable_database, random_kod, write_database

from cronos_extract import Kod
from cronos_extract._cli.options import kod_options, selected_kod
from cronos_extract._cli.report import Failure

KOD = random_kod(seed=3)
PERSON_FIELDS = [b"42", b"Hammersley", b"", b"1240315", b"0930", b"", b"", b"", b"", b"", b""]


def parser_with(*, crack: bool = True, compact: bool = True) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="test", parents=[kod_options(crack=crack, compact=compact)])
    parser.add_argument("dbdir")
    return parser


def test_kod_reads_512_hex_digits() -> None:
    args = parser_with().parse_args(["--kod", bytes(KOD).hex(), "db"])

    assert args.kod == Kod.from_table(KOD)


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("zz" * 256, "exactly 512 hex digits"),
        ("00" * 255, "exactly 512 hex digits"),
        ("00" * 256, "each number from 0 to 255 exactly once"),
    ],
    ids=["not-hex", "too-short", "not-a-permutation"],
)
def test_kod_that_is_not_a_kod_is_a_usage_error_giving_the_reason(
    text: str, reason: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        parser_with().parse_args(["--kod", text, "db"])

    assert stopped.value.code == 2
    error = capsys.readouterr().err
    assert reason in error
    assert "--kod" in error


@pytest.mark.parametrize(
    "options",
    [["--kod", bytes(KOD).hex(), "--nokod"], ["--nokod", "--crack", "dbcrack"], ["-n", "--crack", "strucrack"]],
)
def test_kod_nokod_and_crack_exclude_each_other(options: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        parser_with().parse_args([*options, "db"])

    assert stopped.value.code == 2
    assert "not allowed with" in capsys.readouterr().err


def test_options_left_out_still_have_their_defaults() -> None:
    args = parser_with(crack=False, compact=False).parse_args(["db"])

    assert (args.kod, args.nokod, args.crack, args.compact) == (None, False, None, False)


@pytest.mark.parametrize("option", ["--crack", "--compact"])
def test_options_left_out_are_not_accepted(option: str) -> None:
    with pytest.raises(SystemExit) as stopped:
        parser_with(crack=False, compact=False).parse_args([option, "strucrack", "db"])

    assert stopped.value.code == 2


def test_the_default_kod_is_selected_without_options() -> None:
    assert selected_kod(parser_with().parse_args(["db"])) == Kod.default()


def test_nokod_selects_no_kod() -> None:
    assert selected_kod(parser_with().parse_args(["--nokod", "db"])) is None


def test_kod_selects_the_kod_given() -> None:
    assert selected_kod(parser_with().parse_args(["--kod", bytes(KOD).hex(), "db"])) == Kod.from_table(KOD)


@pytest.mark.parametrize("method", ["strucrack", "dbcrack"])
def test_crack_selects_the_kod_it_recovers(tmp_path: Path, method: str) -> None:
    dbdir = crackable_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, PERSON_FIELDS)], KOD)

    assert selected_kod(parser_with().parse_args(["--crack", method, dbdir])) == Kod.from_table(KOD)


def test_crack_that_recovers_nothing_fails_naming_the_crack_command(tmp_path: Path) -> None:
    dbdir = write_database(
        tmp_path / "db", [bank_record(TEST_TABLE_ID, PERSON_FIELDS)], KOD, index_records=[bytes(12)] * 3
    )

    with pytest.raises(Failure) as failed:
        selected_kod(parser_with().parse_args(["--crack", "dbcrack", dbdir]))

    assert failed.value.status == 1
    assert f"cronos-extract crack strucrack {dbdir}" in str(failed.value)
