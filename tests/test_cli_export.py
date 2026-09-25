# ABOUTME: Tests for the export subcommand: each format's layout, the -o rules, diagnostics and exit statuses.
# ABOUTME: They export crafted databases from tests/cronos_builder.py, in this process or by running the command.
import csv
import os
import re
from pathlib import Path

import pytest
from cli import run_in_process
from cronos_builder import (
    TEST_DB,
    TEST_TABLE_FIELD_COUNT,
    TEST_TABLE_ID,
    bank_record,
    database_with_extra_definition_key,
    database_with_files_abbreviation,
    erdgeist_table_definition,
    file_record,
    file_reference_field,
    patched_table_definition,
    record_with_file_field,
    renamed_table_definition,
    write_database,
)

from cronos_extract import DatabaseDefinitionError
from cronos_extract._cli import export

HEADER = ["Системный номер", *(f"Entry #{number}" for number in range(1, 12))]
# Both of TEST_DB's table definitions report that their Section 2 is not marked with a 2.
TEST_DB_SUMMARY = "2 diagnostics: 2 unexpected_structure"


def table_record(values: dict[int, bytes]) -> bytes:
    """A record of the test table holding `values` by field index, Entry #1 being 0, with every other field empty."""
    fields = [b""] * TEST_TABLE_FIELD_COUNT
    for index, value in values.items():
        fields[index] = value
    return bank_record(TEST_TABLE_ID, fields)


def export_csv(dbdir: str | Path, outdir: Path, *options: str) -> int:
    return run_in_process(export.add_parser, ["export", "--csv", *options, "-o", str(outdir), str(dbdir)])


def csv_rows(path: Path, delimiter: str = ",") -> list[list[str]]:
    with path.open(encoding="utf-8", newline="") as file:
        return list(csv.reader(file, delimiter=delimiter))


def names_in(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir())


def snapshot(path: Path) -> tuple[str, object]:
    """What `path` is and holds, to check that an export left it alone."""
    if path.is_symlink():
        return "link", os.readlink(path)
    if path.is_dir():
        return "directory", names_in(path)
    return "file", path.read_bytes()


def test_csv_export_writes_a_file_per_table_and_the_files_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    outdir = tmp_path / "out"

    assert export_csv(TEST_DB, outdir) == 0

    assert names_in(outdir) == ["Files-FL", "erdgeist.csv"]
    assert names_in(outdir / "Files-FL") == []
    assert csv_rows(outdir / "erdgeist.csv") == [HEADER]
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines()[-1] == TEST_DB_SUMMARY


def test_csv_files_are_utf8_without_a_bom_and_end_rows_with_crlf(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [table_record({0: "Иванов".encode("cp1251")})])

    assert export_csv(dbdir, tmp_path / "out") == 0

    data = (tmp_path / "out" / "erdgeist.csv").read_bytes()
    assert data.startswith("Системный номер,Entry #1,".encode())
    assert data.endswith(("1,Иванов" + "," * 10 + "\r\n").encode())


def test_csv_cells_hold_exactly_what_the_api_decoded(tmp_path: Path) -> None:
    texts = ["=1+1", "-5", "+7 900", "@x", "multi\nline", "carriage\rreturn", 'a,"b"', "C:\\Users\\x"]
    dbdir = write_database(tmp_path / "db", [table_record({0: text.encode("cp1251")}) for text in texts])

    assert export_csv(dbdir, tmp_path / "out") == 0

    assert [row[1] for row in csv_rows(tmp_path / "out" / "erdgeist.csv")[1:]] == texts


def test_csv_export_creates_a_timestamped_directory_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert run_in_process(export.add_parser, ["export", "--csv", str(TEST_DB)]) == 0

    (created,) = tmp_path.iterdir()
    assert re.fullmatch(r"cronos-extract-\d{4}(-\d{2}){5}-\d{6}", created.name)
    assert (created / "erdgeist.csv").is_file()


@pytest.fixture(params=["directory", "file", "dangling-symlink"])
def existing_target(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    target = tmp_path / "out"
    if request.param == "directory":
        target.mkdir()
    elif request.param == "file":
        target.write_text("kept")
    else:
        target.symlink_to(tmp_path / "nowhere")
    return target


def test_csv_export_refuses_a_target_that_exists(
    existing_target: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = snapshot(existing_target)

    with pytest.raises(SystemExit) as stopped:
        export_csv(TEST_DB, existing_target)

    assert stopped.value.code == 2
    assert "already exists" in capsys.readouterr().err
    assert snapshot(existing_target) == before
    assert not (tmp_path / "nowhere").exists()


def test_csv_export_creates_nothing_when_the_database_cannot_be_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(DatabaseDefinitionError):
        export_csv(TEST_DB, tmp_path / "out", "--nokod")

    assert not (tmp_path / "out").exists()
    assert capsys.readouterr().err.splitlines()[-1] == "1 diagnostic: 1 unexpected_structure"


def test_csv_export_leaves_the_working_directory_unchanged(tmp_path: Path) -> None:
    before = Path.cwd()

    export_csv(TEST_DB, tmp_path / "out")

    assert Path.cwd() == before


def test_csv_export_writes_the_stored_and_the_referenced_files(tmp_path: Path) -> None:
    dbdir = write_database(
        tmp_path / "db", [file_record(b"DATA"), record_with_file_field(file_reference_field("report", "pdf", 1))]
    )

    assert export_csv(dbdir, tmp_path / "out") == 0

    assert (tmp_path / "out" / "Files-FL" / "1").read_bytes() == b"DATA"
    assert (tmp_path / "out" / "Files-Referenced" / "report.pdf").read_bytes() == b"DATA"


def test_files_referenced_is_created_for_a_record_whose_file_field_is_empty(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [record_with_file_field(b"")])

    assert export_csv(dbdir, tmp_path / "out") == 0

    assert names_in(tmp_path / "out" / "Files-Referenced") == []


def test_no_files_leaves_out_both_file_directories(tmp_path: Path) -> None:
    dbdir = write_database(
        tmp_path / "db", [file_record(b"DATA"), record_with_file_field(file_reference_field("report", "pdf", 1))]
    )

    assert export_csv(dbdir, tmp_path / "out", "--no-files") == 0

    assert names_in(tmp_path / "out") == ["erdgeist.csv"]


def test_the_delimiter_separates_the_cells(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [table_record({0: b"a;b"})])

    assert export_csv(dbdir, tmp_path / "out", "--delimiter", ";") == 0

    table = tmp_path / "out" / "erdgeist.csv"
    assert table.read_text(encoding="utf-8").startswith("Системный номер;Entry #1;")
    assert csv_rows(table, delimiter=";")[1][:2] == ["1", "a;b"]


@pytest.mark.parametrize("delimiter", ['"', "\n", "ab", ""], ids=["quote", "line-break", "two-characters", "empty"])
def test_a_delimiter_csv_rejects_is_a_usage_error(
    tmp_path: Path, delimiter: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        export_csv(TEST_DB, tmp_path / "out", f"--delimiter={delimiter}")

    assert stopped.value.code == 2
    assert "cannot be a CSV delimiter" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    ("abbreviation", "expected"),
    [
        (b"Referenced", "Files-Referenced-0"),
        (b"REFERENCED", "Files-REFERENCED-0"),
        ("я".encode("cp1251") * 255, None),
    ],
    ids=["collides-with-referenced", "differs-only-in-case", "510-utf8-bytes"],
)
def test_the_files_directory_name_is_unique_and_short(
    tmp_path: Path, abbreviation: bytes, expected: str | None
) -> None:
    dbdir = database_with_files_abbreviation(
        tmp_path / "db",
        abbreviation,
        [file_record(b"DATA"), record_with_file_field(file_reference_field("a", "txt", 1))],
    )
    outdir = tmp_path / "out"

    assert export_csv(dbdir, outdir) == 0

    (files_directory,) = [path for path in outdir.iterdir() if path.is_dir() and path.name != "Files-Referenced"]
    assert (files_directory / "1").read_bytes() == b"DATA"
    assert (outdir / "Files-Referenced" / "a.txt").read_bytes() == b"DATA"
    assert len(files_directory.name.encode("utf-8")) <= 255
    if expected is not None:
        assert files_directory.name == expected


def test_a_table_defined_twice_with_one_name_and_id_is_exported_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dbdir = database_with_extra_definition_key(
        tmp_path / "db", "Base002", erdgeist_table_definition(), [table_record({0: b"one"})]
    )

    assert export_csv(dbdir, tmp_path / "out") == 0

    # table_record fills every field, including the empty type-6 "Entry #6" field, which is why Files-Referenced
    # is created here even though nothing is written into it.
    assert names_in(tmp_path / "out") == ["Files-FL", "Files-Referenced", "erdgeist.csv"]
    assert [row[1] for row in csv_rows(tmp_path / "out" / "erdgeist.csv")[1:]] == ["one"]
    err = capsys.readouterr().err
    assert 'warning: duplicate_table: table "erdgeist": ' in err
    assert "1 duplicate_table" in err.splitlines()[-1]


def test_a_table_whose_safe_name_and_id_repeat_another_is_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    second = renamed_table_definition(erdgeist_table_definition(), name=b"ERDGEIST")
    dbdir = database_with_extra_definition_key(tmp_path / "db", "Base002", second, [table_record({0: b"one"})])

    assert export_csv(dbdir, tmp_path / "out") == 0

    assert names_in(tmp_path / "out") == ["Files-FL", "Files-Referenced", "erdgeist.csv"]
    assert 'warning: duplicate_table: table "ERDGEIST": ' in capsys.readouterr().err


def test_a_refused_tables_records_are_not_read_again(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    second = renamed_table_definition(erdgeist_table_definition(), name=b"ERDGEIST")
    dbdir = database_with_extra_definition_key(
        tmp_path / "db", "Base002", second, [table_record({0: b"one", 3: b"12x"})]
    )

    assert export_csv(dbdir, tmp_path / "out") == 0

    lines = capsys.readouterr().err.splitlines()
    assert sum("invalid_value" in line and "warning" in line for line in lines) == 1
    assert "1 invalid_value" in lines[-1]


def test_hostile_names_stay_inside_the_output_directory(tmp_path: Path) -> None:
    hostile = "../../etc/passwd"
    second = renamed_table_definition(patched_table_definition(tableid=2), name=hostile.encode("cp1251"))
    dbdir = database_with_extra_definition_key(
        tmp_path / "db",
        "Base002",
        second,
        [
            file_record(b"DATA"),
            record_with_file_field(file_reference_field(hostile, "", 1)),
            bank_record(2, [b"x"] + [b""] * (TEST_TABLE_FIELD_COUNT - 1)),
        ],
    )
    outdir = tmp_path / "out"

    assert export_csv(dbdir, outdir) == 0

    assert names_in(tmp_path) == ["db", "out"]
    assert all(path.resolve().is_relative_to(outdir.resolve()) for path in outdir.rglob("*"))
    assert names_in(outdir) == [".._.._etc_passwd.csv", "Files-FL", "Files-Referenced", "erdgeist.csv"]
    assert names_in(outdir / "Files-Referenced") == [".._.._etc_passwd"]
