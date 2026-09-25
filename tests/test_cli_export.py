# ABOUTME: Tests for the export subcommand: each format's layout, the -o rules, diagnostics and exit statuses.
# ABOUTME: They export crafted databases from tests/cronos_builder.py, in this process or by running the command.
import csv
import gc
import json
import os
import re
import struct
from pathlib import Path
from typing import cast

import pytest
from cli import run_command, run_in_process
from cronos_builder import (
    TEST_DB,
    TEST_TABLE_FIELD_COUNT,
    TEST_TABLE_FILE_FIELD_INDEX,
    TEST_TABLE_ID,
    bank_record,
    complex_field,
    corrupt_compressed_record,
    database_with_extra_definition_key,
    database_with_files_abbreviation,
    database_with_missing_definition,
    database_with_wrong_kod_record_out_of_range,
    duplicate_table_name_database,
    erdgeist_table_definition,
    file_record,
    file_reference_field,
    key_referencing_a_deleted_record,
    patched_table_definition,
    random_kod,
    record_with_file_field,
    renamed_table_definition,
    stru_records_from_test_db,
    write_database,
    write_datafile,
)

from cronos_extract import DatabaseDefinitionError, FieldDefinition
from cronos_extract import open as open_bank
from cronos_extract._cli import export
from cronos_extract._cli.sql_out import unique_sql_column_names, unique_sql_table_name
from cronos_extract.Database import KOD_HINT

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


def export_to_stdout(dbdir: str | Path, *options: str) -> int:
    return run_in_process(export.add_parser, ["export", *options, str(dbdir)])


def insert_statements(sql: str) -> list[str]:
    return [line for line in sql.splitlines() if line.startswith("INSERT")]


TEST_DB_SQL = (
    "SET standard_conforming_strings = on;\n"
    "\n"
    'CREATE TABLE "erdgeist" (\n' + ",\n".join(f'    "{name}" TEXT' for name in HEADER) + "\n);\n"
)


def test_postgres_export_writes_the_layout_d9_describes(capsys: pytest.CaptureFixture[str]) -> None:
    assert export_to_stdout(TEST_DB, "--postgres") == 0

    captured = capsys.readouterr()
    assert captured.out == TEST_DB_SQL
    assert captured.err.splitlines()[-1] == TEST_DB_SUMMARY


def test_postgres_export_writes_one_insert_per_record_with_null_for_empty_values(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dbdir = write_database(
        tmp_path / "db",
        [table_record({0: b"O'Brien", 1: b"C:\\x"}), table_record({3: b"1240315", 4: b"0930"})],
    )

    assert export_to_stdout(dbdir, "--postgres") == 0

    assert insert_statements(capsys.readouterr().out) == [
        'INSERT INTO "erdgeist" VALUES '
        "('1', 'O''Brien', 'C:\\x', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);",
        'INSERT INTO "erdgeist" VALUES '
        "('2', NULL, NULL, NULL, '2024-03-15', '09:30', NULL, NULL, NULL, NULL, NULL, NULL);",
    ]


def test_postgres_export_replaces_nul_with_u_fffd_and_reports_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dbdir = write_database(tmp_path / "db", [table_record({1: b"a\x00b"})])

    assert export_to_stdout(dbdir, "--postgres") == 0

    captured = capsys.readouterr()
    (insert,) = insert_statements(captured.out)
    assert "'a\ufffdb'" in insert
    assert "\x00" not in captured.out
    assert (
        'warning: replaced_nul: table "erdgeist", record 1, field "Entry #2": the value holds NUL characters, which '
        "PostgreSQL text cannot hold; they are written as U+FFFD" in captured.err
    )
    assert captured.err.splitlines()[-1] == "3 diagnostics: 2 unexpected_structure, 1 replaced_nul"


def test_postgres_export_writes_a_file_that_o_names(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "out.sql"

    assert export_to_stdout(TEST_DB, "--postgres", "-o", str(output)) == 0

    assert output.read_text(encoding="utf-8") == TEST_DB_SQL
    assert capsys.readouterr().out == ""


def test_postgres_export_refuses_a_file_that_exists(tmp_path: Path) -> None:
    output = tmp_path / "out.sql"
    output.write_text("kept")

    with pytest.raises(SystemExit) as stopped:
        export_to_stdout(TEST_DB, "--postgres", "-o", str(output))

    assert stopped.value.code == 2
    assert output.read_text() == "kept"


@pytest.mark.parametrize(
    ("options", "message"),
    [(["--no-files"], "--no-files applies only to --csv"), (["--delimiter", ";"], "--delimiter applies only to --csv")],
    ids=["no-files", "delimiter"],
)
def test_csv_options_with_another_format_are_usage_errors(
    options: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        export_to_stdout(TEST_DB, "--postgres", *options)

    assert stopped.value.code == 2
    assert message in capsys.readouterr().err


def test_sql_column_names_are_unique_and_fit_postgres_identifiers() -> None:
    fields = [
        FieldDefinition("Системный номер", 0),
        FieldDefinition("я" * 40, 1),
        FieldDefinition("я" * 40 + "ж", 1),
        FieldDefinition("same", 1),
        FieldDefinition("SAME", 1),
        FieldDefinition("", 1),
        FieldDefinition('say "hi"', 1),
    ]

    names = unique_sql_column_names(fields)

    assert len({name.casefold() for name in names}) == len(fields), names
    assert all(len(name.encode("utf-8")) <= 63 for name in names), names
    assert names[3:] == ["same", "SAME-4", "5", "say _hi_"]


def test_sql_table_names_are_unique_and_fit_postgres_identifiers(tmp_path: Path) -> None:
    dbdir = duplicate_table_name_database(tmp_path / "db", second_table_name=("я" * 100).encode("cp1251"))
    used_names: dict[str, int] = {}

    with open_bank(dbdir) as bank:
        names = [unique_sql_table_name(table, used_names) for table in bank.tables]

    assert names[0] == "erdgeist"
    assert names[1] is not None
    assert len(names[1].encode("utf-8")) <= 63


def test_a_table_whose_sql_name_and_id_repeat_another_is_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    second = renamed_table_definition(erdgeist_table_definition(), name=b"ERDGEIST")
    dbdir = database_with_extra_definition_key(tmp_path / "db", "Base002", second, [table_record({0: b"one"})])

    assert export_to_stdout(dbdir, "--postgres") == 0

    captured = capsys.readouterr()
    assert [line for line in captured.out.splitlines() if line.startswith("CREATE")] == ['CREATE TABLE "erdgeist" (']
    assert len(insert_statements(captured.out)) == 1
    assert 'warning: duplicate_table: table "ERDGEIST": ' in captured.err


def jsonl_lines(output: str) -> list[dict[str, object]]:
    assert output.endswith("\n")
    return [json.loads(line) for line in output.split("\n")[:-1]]


SECTION_2_DIAGNOSTICS = [
    {
        "type": "diagnostic",
        "kind": "unexpected_structure",
        "message": f"{key}: FieldDefinition Section 2 not marked with a 2",
        "file": "CroStru.dat",
        "table": None,
        "record": None,
        "field": None,
    }
    for key in ("Base000", "Base001")
]
TEST_TABLE_LINE = {
    "type": "table",
    "table": "erdgeist",
    "table_id": 1,
    "abbreviation": "ER",
    "fields": [
        {"name": name, "type": field_type}
        for name, field_type in zip(HEADER, [0, 1, 2, 3, 4, 5, 6, 29, 7, 8, 9, 17], strict=True)
    ],
}


def record_line(number: int, values: dict[str, object]) -> dict[str, object]:
    """The JSON Lines record line of the test table's record `number`, whose fields are `values` or null."""
    return {
        "type": "record",
        "table": "erdgeist",
        "table_id": 1,
        "record": number,
        "fields": [{"name": name, "value": str(number) if name == HEADER[0] else values.get(name)} for name in HEADER],
    }


def test_jsonl_writes_the_table_line_for_a_table_without_records(capsys: pytest.CaptureFixture[str]) -> None:
    assert export_to_stdout(TEST_DB, "--jsonl") == 0

    assert jsonl_lines(capsys.readouterr().out) == [*SECTION_2_DIAGNOSTICS, TEST_TABLE_LINE]


def test_jsonl_writes_each_value_as_d4_describes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dbdir = write_database(
        tmp_path / "db",
        [
            table_record({0: b"42", 3: b"1240315", 4: b"0930", 5: file_reference_field("scan", "jpg", 40)}),
            table_record({3: b"850000", 5: file_reference_field("scan", "jpg", "abc")}),
        ],
    )

    assert export_to_stdout(dbdir, "--jsonl") == 0

    assert jsonl_lines(capsys.readouterr().out)[3:] == [
        record_line(
            1,
            {
                "Entry #1": "42",
                "Entry #4": "2024-03-15",
                "Entry #5": "09:30",
                "Entry #6": {"name": "scan", "extension": "jpg", "record": 40},
            },
        ),
        record_line(2, {"Entry #4": "1985-00-00", "Entry #6": {"name": "scan", "extension": "jpg", "record": None}}),
    ]


@pytest.mark.parametrize(
    ("date", "value", "message"),
    [
        (b"\x00" * 6, "", "the value is not a date; it is kept as text"),
        (b"12x", "12x", "the value is not a date; it is kept as text"),
    ],
    ids=["nul-only", "not-a-date"],
)
def test_jsonl_writes_a_record_s_diagnostics_before_it_and_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], date: bytes, value: str, message: str
) -> None:
    dbdir = write_database(tmp_path / "db", [table_record({3: date})])

    assert export_to_stdout(dbdir, "--jsonl") == 0

    captured = capsys.readouterr()
    assert jsonl_lines(captured.out)[3:] == [
        {
            "type": "diagnostic",
            "kind": "invalid_value",
            "message": message,
            "file": "CroBank.dat",
            "table": "erdgeist",
            "record": 1,
            "field": "Entry #4",
        },
        record_line(1, {"Entry #4": value}),
    ]
    assert f'warning: invalid_value: table "erdgeist", record 1, field "Entry #4": {message}' in captured.err


def test_jsonl_is_utf8_text_not_ascii_escapes(capsys: pytest.CaptureFixture[str]) -> None:
    assert export_to_stdout(TEST_DB, "--jsonl") == 0

    assert '"Системный номер"' in capsys.readouterr().out


def test_jsonl_writes_a_repeated_table_once_and_says_so_in_the_stream(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dbdir = database_with_extra_definition_key(
        tmp_path / "db", "Base002", erdgeist_table_definition(), [table_record({0: b"one"})]
    )

    assert export_to_stdout(dbdir, "--jsonl") == 0

    lines = jsonl_lines(capsys.readouterr().out)
    assert [line["type"] for line in lines if line["type"] != "diagnostic"] == ["table", "record"]
    assert {"kind": "duplicate_table", "table": "erdgeist"}.items() <= lines[-1].items()


def test_jsonl_writes_both_tables_whose_names_differ_only_in_case(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    second = renamed_table_definition(erdgeist_table_definition(), name=b"ERDGEIST")
    dbdir = database_with_extra_definition_key(tmp_path / "db", "Base002", second, [table_record({0: b"one"})])

    assert export_to_stdout(dbdir, "--jsonl") == 0

    lines = jsonl_lines(capsys.readouterr().out)
    assert [(line["type"], line["table"]) for line in lines if line["type"] != "diagnostic"] == [
        ("table", "erdgeist"),
        ("record", "erdgeist"),
        ("table", "ERDGEIST"),
        ("record", "ERDGEIST"),
    ]


def test_jsonl_writes_to_the_file_o_names(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "out.jsonl"

    assert export_to_stdout(TEST_DB, "--jsonl", "-o", str(output)) == 0

    assert jsonl_lines(output.read_text(encoding="utf-8")) == [*SECTION_2_DIAGNOSTICS, TEST_TABLE_LINE]
    assert capsys.readouterr().out == ""


def last_line(stderr: str) -> str:
    return stderr.splitlines()[-1]


def test_export_exits_0_when_it_finishes(tmp_path: Path) -> None:
    result = run_command("cli", ["export", "--csv", "-o", str(tmp_path / "out"), str(TEST_DB)])

    assert result.returncode == 0, result.stderr
    assert last_line(result.stderr) == TEST_DB_SUMMARY


def test_export_of_an_undecodable_definition_exits_1_naming_the_crack_command() -> None:
    result = run_command("cli", ["export", "--postgres", "--nokod", str(TEST_DB)])

    assert result.returncode == 1
    assert result.stdout == ""
    lines = result.stderr.splitlines()
    assert lines[-2] == "1 diagnostic: 1 unexpected_structure"
    assert lines[-1].startswith("Error: the database definition in CroStru.dat of ")
    assert lines[-1].endswith(KOD_HINT)
    assert "cronos_extract.crack_kod" not in result.stderr


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--postgres", "--no-files"], "--no-files applies only to --csv"),
        (["--jsonl", "--delimiter", ";"], "--delimiter applies only to --csv"),
        (["--csv", "--delimiter", "ab"], "cannot be a CSV delimiter"),
        (["--jsonl", "--kod", "00" * 256], "each number from 0 to 255 exactly once"),
        (["--csv", "--jsonl"], "not allowed with"),
        (["--nokod"], "one of the arguments --csv --postgres --jsonl is required"),
    ],
    ids=["no-files", "delimiter-format", "delimiter-length", "kod", "two-formats", "no-format"],
)
def test_export_usage_errors_exit_2(args: list[str], message: str) -> None:
    result = run_command("cli", ["export", *args, str(TEST_DB)])

    assert result.returncode == 2
    assert message in result.stderr
    assert "invalid kod_argument value" not in result.stderr


def test_export_to_an_existing_target_exits_2(tmp_path: Path) -> None:
    (tmp_path / "out").mkdir()

    result = run_command("cli", ["export", "--csv", "-o", str(tmp_path / "out"), str(TEST_DB)])

    assert result.returncode == 2
    assert "already exists" in result.stderr


@pytest.mark.parametrize("problem", ["missing", "file"])
def test_a_database_directory_that_cannot_be_listed_exits_1(tmp_path: Path, problem: str) -> None:
    dbdir = tmp_path / "db"
    if problem == "file":
        dbdir.write_text("not a directory")

    result = run_command("cli", ["export", "--jsonl", str(dbdir)])

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert last_line(result.stderr).startswith("Error: ")


def test_an_output_in_a_missing_directory_exits_1(tmp_path: Path) -> None:
    result = run_command("cli", ["export", "--csv", "-o", str(tmp_path / "missing" / "out"), str(TEST_DB)])

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert last_line(result.stderr).startswith("Error: [Errno 2]")


@pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="needs a POSIX user that permissions apply to")
def test_an_output_in_a_directory_that_is_not_writable_exits_1(tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        result = run_command("cli", ["export", "--csv", "-o", str(locked / "out"), str(TEST_DB)])
    finally:
        locked.chmod(0o700)

    assert result.returncode == 1
    assert last_line(result.stderr).startswith("Error: [Errno 13]")


def test_a_crack_that_recovers_nothing_exits_1(tmp_path: Path) -> None:
    dbdir = write_database(
        tmp_path / "db", [table_record({0: b"x"})], random_kod(seed=7), index_records=[bytes(12)] * 3
    )

    result = run_command("cli", ["export", "--jsonl", "--crack", "dbcrack", dbdir])

    assert result.returncode == 1
    assert "cronos-extract crack strucrack" in last_line(result.stderr)


def test_strict_exits_1_after_writing_the_output(tmp_path: Path) -> None:
    # Every crafted database reports unexpected_structure for its table definitions (D17), so --strict exits 1.
    outdir = tmp_path / "out"

    result = run_command("cli", ["export", "--csv", "--strict", "-o", str(outdir), str(TEST_DB)])

    assert result.returncode == 1
    assert (outdir / "erdgeist.csv").is_file()
    assert last_line(result.stderr) == TEST_DB_SUMMARY


def test_strict_does_not_lower_a_usage_error(tmp_path: Path) -> None:
    (tmp_path / "out").mkdir()

    result = run_command("cli", ["export", "--csv", "--strict", "-o", str(tmp_path / "out"), str(TEST_DB)])

    assert result.returncode == 2


def test_table_definition_warnings_go_to_stderr_not_into_the_sql() -> None:
    result = run_command("cli", ["export", "--postgres", str(TEST_DB)])

    assert result.returncode == 0, result.stderr
    assert "FieldDefinition" not in result.stdout
    assert (
        "warning: unexpected_structure: CroStru.dat: Base001: FieldDefinition Section 2 not marked with a 2"
        in result.stderr
    )


def test_db_definition_errors_go_to_stderr_not_into_the_sql() -> None:
    result = run_command("cli", ["export", "--postgres", "--nokod", str(TEST_DB)])

    assert result.returncode == 1
    assert result.stdout == ""
    assert "warning: unexpected_structure: CroStru.dat: expected dbinfo to start with 0x03" in result.stderr
    assert last_line(result.stderr).startswith("Error: the database definition in CroStru.dat of ")


def test_postgres_output_is_not_html_escaped(tmp_path: Path) -> None:
    fields = [b""] * TEST_TABLE_FIELD_COUNT
    fields[1] = b'<b>&"O\'Brien"</b>'
    dbdir = write_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, fields)])

    result = run_command("cli", ["export", "--postgres", dbdir])

    assert result.returncode == 0, result.stderr
    assert "'<b>&\"O''Brien\"</b>'" in result.stdout


def unreadable_file_references_database(directory: Path) -> str:
    """Write a database whose record 3 refers to a stored file and records 4 to 6 refer to unreadable ones."""
    return write_database(
        directory,
        [
            file_record(b"GOOD"),
            None,
            record_with_file_field(file_reference_field("good", "pdf", 1)),
            record_with_file_field(file_reference_field("letters", "pdf", "abc")),
            record_with_file_field(file_reference_field("deleted", "pdf", 2)),
            record_with_file_field(file_reference_field("missing", "pdf", 99)),
        ],
    )


def test_csv_export_skips_unreadable_file_references(tmp_path: Path) -> None:
    dbdir = unreadable_file_references_database(tmp_path / "db")
    outdir = tmp_path / "out"

    result = run_command("cli", ["export", "--csv", "-o", str(outdir), dbdir])

    assert result.returncode == 0, result.stderr
    lines = result.stderr.splitlines()
    for warning in [
        "warning: unresolved_file_reference: CroBank.dat: a file reference cannot be read: "
        "its record number is not a number",
        "warning: unresolved_file_reference: CroBank.dat record 2: a file reference cannot be read: "
        "CroBank record 2 is deleted or corrupt",
        "warning: unresolved_file_reference: CroBank.dat record 99: a file reference cannot be read: "
        "CroBank has no record 99",
    ]:
        assert lines.count(warning) == 1, result.stderr
    assert [path.name for path in (outdir / "Files-Referenced").iterdir()] == ["good.pdf"]
    assert (outdir / "Files-Referenced" / "good.pdf").read_bytes() == b"GOOD"


def test_csv_export_gives_referenced_files_safe_unique_names(tmp_path: Path) -> None:
    dbdir = write_database(
        tmp_path / "db",
        [
            file_record(b"one"),
            file_record(b"two"),
            file_record(b"three"),
            file_record(b"four"),
            file_record(b"five"),
            record_with_file_field(file_reference_field("", "", 1)),
            record_with_file_field(file_reference_field("..", "", 2)),
            record_with_file_field(file_reference_field("same", "txt", 3)),
            record_with_file_field(file_reference_field("same", "txt", 4)),
            record_with_file_field(file_reference_field("same", "txt", 3)),
            record_with_file_field(file_reference_field("nul\x00byte", "bin", 5)),
        ],
    )
    outdir = tmp_path / "out"

    result = run_command("cli", ["export", "--csv", "-o", str(outdir), dbdir])

    assert result.returncode == 0, result.stderr
    referenced = outdir / "Files-Referenced"
    assert {path.name: path.read_bytes() for path in referenced.iterdir()} == {
        "1": b"one",
        "2": b"two",
        "same.txt": b"three",
        "same-4.txt": b"four",
        "nul_byte.bin": b"five",
    }


def test_tad_leftover_warning_goes_to_stderr_not_into_the_sql(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [])
    with (Path(dbdir) / "CroBank.tad").open("ab") as tad:
        tad.write(b"\x00\x00\x00")

    result = run_command("cli", ["export", "--postgres", dbdir])

    assert result.returncode == 0, result.stderr
    assert "leftover" not in result.stdout
    assert "warning: unexpected_structure: CroBank.dat: leftover data in .tad" in result.stderr


def partly_broken_records_database(directory: Path) -> str:
    """Write a database with one intact record and two whose fields fail to decode.

    Record 2's second field claims 100 bytes but holds 3, so no later field can be read either.
    Record 3's file reference field is too short to decode, but the field after it is intact.
    """
    intact = [b""] * TEST_TABLE_FIELD_COUNT
    intact[0] = b"intact"
    truncated = [b""] * TEST_TABLE_FIELD_COUNT
    truncated[0] = b"first"
    truncated[1] = b"\x1b" + struct.pack("<L", 100) + b"abc"
    short_file = [b""] * TEST_TABLE_FIELD_COUNT
    short_file[0] = b"first"
    short_file[TEST_TABLE_FILE_FIELD_INDEX] = complex_field(b"\x01")
    short_file[TEST_TABLE_FILE_FIELD_INDEX + 1] = b"after"
    return write_database(
        directory,
        [
            bank_record(TEST_TABLE_ID, intact),
            bank_record(TEST_TABLE_ID, truncated),
            bank_record(TEST_TABLE_ID, short_file),
        ],
    )


def assert_partly_broken_record_warnings(stderr: str) -> None:
    lines = stderr.splitlines()
    for recno, fieldname in [(2, "Entry #2"), (3, "Entry #6")]:
        prefix = (
            f'warning: undecodable_field: table "erdgeist", record {recno}, field "{fieldname}": '
            "the field could not be decoded ("
        )
        assert any(line.startswith(prefix) for line in lines), (
            f"no warning about field {fieldname} of record {recno} in stderr: {stderr}"
        )
    assert "2 undecodable_field" in lines[-1], f"no count of undecodable fields at the end of stderr: {stderr}"


def test_csv_export_keeps_the_decoded_fields_of_broken_records(tmp_path: Path) -> None:
    dbdir = partly_broken_records_database(tmp_path / "db")
    outdir = tmp_path / "out"

    result = run_command("cli", ["export", "--csv", "-o", str(outdir), dbdir])

    assert result.returncode == 0, result.stderr
    assert_partly_broken_record_warnings(result.stderr)
    with (outdir / "erdgeist.csv").open(encoding="utf-8", newline="") as csvfile:
        rows = list(csv.reader(csvfile))[1:]
    assert rows == [
        ["1", "intact", "", "", "", "", "", "", "", "", "", ""],
        ["2", "first", "", "", "", "", "", "", "", "", "", ""],
        ["3", "first", "", "", "", "", "", "after", "", "", "", ""],
    ]


def test_postgres_export_keeps_the_decoded_fields_of_broken_records(tmp_path: Path) -> None:
    dbdir = partly_broken_records_database(tmp_path / "db")

    result = run_command("cli", ["export", "--postgres", dbdir])

    assert result.returncode == 0, result.stderr
    assert_partly_broken_record_warnings(result.stderr)
    assert "intact" in result.stdout
    assert "after" in result.stdout


def test_postgres_output_has_no_insert_for_an_empty_table(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [])

    result = run_command("cli", ["export", "--postgres", dbdir])

    assert result.returncode == 0, result.stderr
    assert 'CREATE TABLE "erdgeist"' in result.stdout
    assert insert_statements(result.stdout) == []


def test_postgres_output_has_one_insert_per_record(tmp_path: Path) -> None:
    first = [b""] * TEST_TABLE_FIELD_COUNT
    first[1] = b"one"
    second = [b""] * TEST_TABLE_FIELD_COUNT
    second[1] = b"two"
    dbdir = write_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, first), bank_record(TEST_TABLE_ID, second)])

    result = run_command("cli", ["export", "--postgres", dbdir])

    assert result.returncode == 0, result.stderr
    inserts = insert_statements(result.stdout)
    assert len(inserts) == 2
    assert all(line.startswith('INSERT INTO "erdgeist" VALUES (') and line.endswith(");") for line in inserts)
    assert "'one'" in inserts[0]
    assert "'two'" in inserts[1]


def test_export_reports_a_key_referencing_a_deleted_record(tmp_path: Path) -> None:
    dbdir = key_referencing_a_deleted_record(tmp_path / "db", "DanglingKey")

    result = run_command("cli", ["export", "--postgres", dbdir])

    assert result.returncode == 1
    assert result.stdout == ""
    assert last_line(result.stderr) == (
        f"Error: the database definition in CroStru.dat of {dbdir} cannot be decoded: "
        f'ValueError: key "DanglingKey" refers to CroStru record 5, which is deleted. {KOD_HINT}'
    )


def test_export_reports_a_record_out_of_range_with_a_wrong_kod(tmp_path: Path) -> None:
    dbdir, wrong_kod_hex = database_with_wrong_kod_record_out_of_range(tmp_path / "db")

    result = run_command("cli", ["export", "--postgres", "--kod", wrong_kod_hex, dbdir])

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert result.stdout == ""
    lines = result.stderr.splitlines()
    assert len(lines) == 2, result.stderr
    assert lines[0] == "no diagnostics"
    assert re.fullmatch(
        r"Error: the database definition in CroStru\.dat of .* cannot be decoded: "
        r'ValueError: key ".*" refers to CroStru record \d+, which CroStru does not hold \(4 records\)\. '
        + re.escape(KOD_HINT),
        lines[1],
    )


def test_export_reports_a_deleted_definition_record(tmp_path: Path) -> None:
    stru_records = [None, *stru_records_from_test_db()[1:]]
    dbdir = database_with_missing_definition(tmp_path / "db", stru_records)

    result = run_command("cli", ["export", "--postgres", dbdir])

    assert result.returncode == 1
    assert last_line(result.stderr) == (
        f"Error: the database definition in CroStru.dat of {dbdir} cannot be decoded: "
        f"ValueError: CroStru record 1, which holds the database definition, is deleted. {KOD_HINT}"
    )


def test_export_reports_no_definition_record(tmp_path: Path) -> None:
    dbdir = database_with_missing_definition(tmp_path / "db", [])

    result = run_command("cli", ["export", "--postgres", dbdir])

    assert result.returncode == 1
    assert last_line(result.stderr) == (
        f"Error: the database definition in CroStru.dat of {dbdir} cannot be decoded: "
        f"ValueError: CroStru holds no records, so it has no database definition. {KOD_HINT}"
    )


def test_export_stops_with_a_clear_message_without_crostru(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [])
    (Path(dbdir) / "CroStru.dat").unlink()
    (Path(dbdir) / "CroStru.tad").unlink()

    result = run_command("cli", ["export", "--postgres", dbdir])

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert "CroStru.dat" in result.stderr
    assert dbdir in result.stderr
    assert result.stdout == ""


def name_with_undefined_cp1251_byte_database(directory: Path) -> str:
    """Write a database whose table name and a field name each contain byte 0x98, undefined in CP-1251.

    Base001 (the test table's definition) is stored in CroStru record 4, referenced from record 1's database
    definition; its table name "erdgeist" and field name "Entry #6" each have their first byte replaced.
    """
    stru = stru_records_from_test_db()
    table_definition = stru[3]
    assert table_definition is not None
    mutated = bytearray(table_definition)
    for name in (b"erdgeist", b"Entry #6"):
        mutated[mutated.index(name)] = 0x98
    stru[3] = bytes(mutated)
    write_datafile(directory, "Stru", stru)

    fields = [b""] * TEST_TABLE_FIELD_COUNT
    fields[1] = b"value"
    write_datafile(directory, "Bank", [bank_record(TEST_TABLE_ID, fields)])
    return str(directory)


def test_jsonl_replaces_an_undefined_cp1251_byte_in_a_name(tmp_path: Path) -> None:
    dbdir = name_with_undefined_cp1251_byte_database(tmp_path / "db")

    result = run_command("cli", ["export", "--jsonl", dbdir])

    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr
    (table_line,) = [line for line in jsonl_lines(result.stdout) if line["type"] == "table"]
    assert table_line["table"] == "\ufffdrdgeist"
    assert {"name": "\ufffdntry #6", "type": 6} in cast(list[object], table_line["fields"])


def test_csv_export_writes_tables_with_the_same_name_to_different_files(tmp_path: Path) -> None:
    dbdir = duplicate_table_name_database(tmp_path / "db")
    outdir = tmp_path / "out"

    result = run_command("cli", ["export", "--csv", "-o", str(outdir), dbdir])

    assert result.returncode == 0, result.stderr
    tables = {}
    for path in outdir.glob("*.csv"):
        with path.open(encoding="utf-8", newline="") as csvfile:
            tables[path.name] = [row[2] for row in list(csv.reader(csvfile))[1:]]
    assert tables == {"erdgeist.csv": ["one"], "erdgeist-2.csv": ["two"]}


def test_postgres_output_gives_tables_with_the_same_name_different_names(tmp_path: Path) -> None:
    dbdir = duplicate_table_name_database(tmp_path / "db")

    result = run_command("cli", ["export", "--postgres", dbdir])

    assert result.returncode == 0, result.stderr
    creates = [line for line in result.stdout.splitlines() if line.startswith("CREATE TABLE")]
    assert creates == ['CREATE TABLE "erdgeist" (', 'CREATE TABLE "erdgeist-2" (']
    inserts = insert_statements(result.stdout)
    assert len(inserts) == 2
    assert inserts[0].startswith('INSERT INTO "erdgeist" VALUES (') and "'one'" in inserts[0]
    assert inserts[1].startswith('INSERT INTO "erdgeist-2" VALUES (') and "'two'" in inserts[1]


def test_postgres_output_writes_null_for_every_empty_value(tmp_path: Path) -> None:
    fields = [b""] * TEST_TABLE_FIELD_COUNT
    fields[1] = b"text"
    dbdir = write_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, fields)])

    result = run_command("cli", ["export", "--postgres", dbdir])

    assert result.returncode == 0, result.stderr
    assert insert_statements(result.stdout) == [
        "INSERT INTO \"erdgeist\" VALUES ('1', NULL, 'text', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);"
    ]


def test_postgres_output_declares_every_column_text_and_writes_values_as_decoded(tmp_path: Path) -> None:
    decoded = [b""] * TEST_TABLE_FIELD_COUNT
    decoded[0] = b"42"
    decoded[3] = b"1240315"
    decoded[4] = b"0930"
    unparseable = [b""] * TEST_TABLE_FIELD_COUNT
    unparseable[0] = b"not a number"
    unparseable[3] = b"12x"
    dbdir = write_database(
        tmp_path / "db", [bank_record(TEST_TABLE_ID, decoded), bank_record(TEST_TABLE_ID, unparseable)]
    )

    result = run_command("cli", ["export", "--postgres", dbdir])

    assert result.returncode == 0, result.stderr
    column_lines = [line.strip().rstrip(",").strip() for line in result.stdout.splitlines() if line.startswith('    "')]
    assert len(column_lines) == TEST_TABLE_FIELD_COUNT + 1
    assert all(line.endswith('" TEXT') for line in column_lines), column_lines
    assert insert_statements(result.stdout) == [
        (
            'INSERT INTO "erdgeist" VALUES '
            "('1', '42', NULL, NULL, '2024-03-15', '09:30', NULL, NULL, NULL, NULL, NULL, NULL);"
        ),
        (
            'INSERT INTO "erdgeist" VALUES '
            "('2', 'not a number', NULL, NULL, '12x', NULL, NULL, NULL, NULL, NULL, NULL, NULL);"
        ),
    ]


def test_csv_export_round_trips_a_backslash(tmp_path: Path) -> None:
    fields = [b""] * TEST_TABLE_FIELD_COUNT
    fields[1] = 'C:\\Users\\x,"quoted"'.encode("cp1251")
    dbdir = write_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, fields)])
    outdir = tmp_path / "out"

    result = run_command("cli", ["export", "--csv", "-o", str(outdir), dbdir])

    assert result.returncode == 0, result.stderr
    with (outdir / "erdgeist.csv").open(encoding="utf-8", newline="") as csvfile:
        rows = list(csv.reader(csvfile))[1:]
    assert rows[0][2] == 'C:\\Users\\x,"quoted"'


def corrupt_bank_record_database(directory: Path) -> str:
    """Write a database whose CroBank record 2 is corrupt, with records referring to a good and to the corrupt file.

    Record 2's index entry has no inline flag, so the reader expects an extended record header, which is longer
    than the 4 bytes stored.
    """
    dbdir = write_database(
        directory,
        [
            file_record(b"GOOD"),
            b"\x00abc",
            record_with_file_field(file_reference_field("good", "pdf", 1)),
            record_with_file_field(file_reference_field("broken", "pdf", 2)),
        ],
    )
    tad_path = Path(dbdir) / "CroBank.tad"
    tad = bytearray(tad_path.read_bytes())
    entry_offset = 8 + 12
    offset, length, checksum = struct.unpack_from("<LLL", tad, entry_offset)
    struct.pack_into("<LLL", tad, entry_offset, offset, length & 0xFFFFFF, checksum)
    tad_path.write_bytes(tad)
    return dbdir


def test_csv_export_skips_a_corrupt_bank_record(tmp_path: Path) -> None:
    dbdir = corrupt_bank_record_database(tmp_path / "db")
    outdir = tmp_path / "out"

    result = run_command("cli", ["export", "--csv", "-o", str(outdir), dbdir])

    assert result.returncode == 0, result.stderr
    prefix = "warning: corrupt_record: CroBank.dat record 2: CroBank record 2 is corrupt and is skipped: "
    assert any(line.startswith(prefix) for line in result.stderr.splitlines()), result.stderr
    with (outdir / "erdgeist.csv").open(encoding="utf-8", newline="") as csvfile:
        assert [row[0] for row in list(csv.reader(csvfile))[1:]] == ["3", "4"]
    assert [path.name for path in (outdir / "Files-FL").iterdir()] == ["1"]
    assert [path.name for path in (outdir / "Files-Referenced").iterdir()] == ["good.pdf"]


def corrupt_compressed_bank_record_database(directory: Path) -> str:
    """Write a database whose CroBank record 2 passes iscompressed() but is not valid deflate data."""
    fields = [b""] * TEST_TABLE_FIELD_COUNT
    fields[0] = b"good"
    return write_database(
        directory,
        [
            bank_record(TEST_TABLE_ID, fields),
            corrupt_compressed_record(),
        ],
    )


def test_csv_export_skips_a_corrupt_compressed_bank_record(tmp_path: Path) -> None:
    dbdir = corrupt_compressed_bank_record_database(tmp_path / "db")
    outdir = tmp_path / "out"

    result = run_command("cli", ["export", "--csv", "-o", str(outdir), dbdir])

    assert result.returncode == 0, result.stderr
    prefix = (
        "warning: corrupt_record: CroBank.dat record 2: CroBank record 2 is corrupt and is skipped: "
        "ValueError: corrupt compressed data: "
    )
    assert any(line.startswith(prefix) for line in result.stderr.splitlines()), result.stderr
    with (outdir / "erdgeist.csv").open(encoding="utf-8", newline="") as csvfile:
        rows = list(csv.reader(csvfile))[1:]
    assert rows == [["1", "good", "", "", "", "", "", "", "", "", "", ""]]


def test_exports_close_the_database_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dbdir = write_database(
        tmp_path / "db", [file_record(b"DATA"), record_with_file_field(file_reference_field("report", "pdf", 1))]
    )
    monkeypatch.chdir(tmp_path)

    run_in_process(export.add_parser, ["export", "--csv", "-o", "out", dbdir])
    run_in_process(export.add_parser, ["export", "--postgres", dbdir])
    run_in_process(export.add_parser, ["export", "--jsonl", dbdir])
    gc.collect()

    assert (tmp_path / "out" / "Files-Referenced" / "report.pdf").read_bytes() == b"DATA"


def test_a_corrupt_referenced_file_gets_one_accurate_warning(tmp_path: Path) -> None:
    dbdir = corrupt_bank_record_database(tmp_path / "db")

    result = run_command("cli", ["export", "--csv", "-o", "out", dbdir], cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    lines = result.stderr.splitlines()
    corrupt = [line for line in lines if line.startswith("warning: corrupt_record: CroBank.dat record 2: ")]
    assert len(corrupt) == 1, result.stderr
    unresolved = (
        "warning: unresolved_file_reference: CroBank.dat record 2: a file reference cannot be read: "
        "CroBank record 2 is deleted or corrupt"
    )
    assert lines.count(unresolved) == 1, result.stderr
    assert "is not the number of a stored file" not in result.stderr


def reference_to_a_data_record_database(directory: Path) -> str:
    """Write a database whose record 2 refers to record 1, a record of the data table instead of the Files table."""
    fields = [b""] * TEST_TABLE_FIELD_COUNT
    fields[1] = b"secret"
    return write_database(
        directory,
        [
            bank_record(TEST_TABLE_ID, fields),
            record_with_file_field(file_reference_field("stolen", "txt", 1)),
        ],
    )


def test_a_file_reference_to_a_record_of_another_table_is_skipped(tmp_path: Path) -> None:
    dbdir = reference_to_a_data_record_database(tmp_path / "db")

    result = run_command("cli", ["export", "--csv", "-o", "out", dbdir], cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    warning = (
        "warning: unresolved_file_reference: CroBank.dat record 1: a file reference cannot be read: "
        "CroBank record 1 is not a record of the Files table"
    )
    assert result.stderr.splitlines().count(warning) == 1, result.stderr
    assert list((tmp_path / "out" / "Files-Referenced").iterdir()) == []


def test_csv_export_shortens_over_long_file_and_table_names(tmp_path: Path) -> None:
    long_name = "я" * 200
    dbdir = write_database(
        tmp_path / "files",
        [
            file_record(b"one"),
            file_record(b"two"),
            file_record(b"three"),
            record_with_file_field(file_reference_field(long_name, "txt", 1)),
            record_with_file_field(file_reference_field(long_name + "ж", "txt", 2)),
            record_with_file_field(file_reference_field("long", "x" * 300, 3)),
        ],
    )
    outdir = tmp_path / "files-out"

    result = run_command("cli", ["export", "--csv", "-o", str(outdir), dbdir])

    assert result.returncode == 0, result.stderr
    files = {path.name: path.read_bytes() for path in (outdir / "Files-Referenced").iterdir()}
    assert all(len(name.encode("utf-8")) <= 255 for name in files), list(files)
    by_content = {content: name for name, content in files.items()}
    assert set(by_content) == {b"one", b"two", b"three"}
    assert by_content[b"one"].endswith(".txt") and by_content[b"one"].startswith("яяя")
    assert by_content[b"two"].endswith("-2.txt")
    assert by_content[b"three"].startswith("long.x")

    tablesdir = duplicate_table_name_database(tmp_path / "tables", second_table_name=long_name.encode("cp1251"))
    tablesout = tmp_path / "tables-out"

    result = run_command("cli", ["export", "--csv", "-o", str(tablesout), tablesdir])

    assert result.returncode == 0, result.stderr
    csv_names = sorted(path.name for path in tablesout.glob("*.csv"))
    assert len(csv_names) == 2
    assert all(len(name.encode("utf-8")) <= 255 and name.endswith(".csv") for name in csv_names), csv_names


def test_postgres_output_shortens_a_long_table_name(tmp_path: Path) -> None:
    dbdir = duplicate_table_name_database(tmp_path / "db", second_table_name=("я" * 100).encode("cp1251"))

    result = run_command("cli", ["export", "--postgres", dbdir])

    assert result.returncode == 0, result.stderr
    creates = [line for line in result.stdout.splitlines() if line.startswith("CREATE TABLE")]
    assert len(creates) == 2
    for line in creates:
        name = line.removeprefix('CREATE TABLE "').removesuffix('" (')
        assert len(name.encode("utf-8")) <= 63, line


def test_postgres_output_replaces_nul_characters_and_warns(tmp_path: Path) -> None:
    fields = [b""] * TEST_TABLE_FIELD_COUNT
    fields[1] = b"a\x00b"
    dbdir = write_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, fields)])

    result = run_command("cli", ["export", "--postgres", dbdir])

    assert result.returncode == 0, result.stderr
    (insert,) = insert_statements(result.stdout)
    assert "'a�b'" in insert
    assert "\x00" not in result.stdout
    warnings = [line for line in result.stderr.splitlines() if line.startswith("warning: replaced_nul")]
    assert warnings == [
        'warning: replaced_nul: table "erdgeist", record 1, field "Entry #2": the value holds NUL characters, which '
        "PostgreSQL text cannot hold; they are written as U+FFFD"
    ], result.stderr

    outdir = tmp_path / "out"
    csv_result = run_command("cli", ["export", "--csv", "-o", str(outdir), dbdir])

    assert csv_result.returncode == 0, csv_result.stderr
    assert "replaced_nul" not in csv_result.stderr
    with (outdir / "erdgeist.csv").open(encoding="utf-8", newline="") as csvfile:
        assert list(csv.reader(csvfile))[1][2] == "a\x00b"


def test_jsonl_export_kod_option_decodes_an_encrypted_database(tmp_path: Path) -> None:
    kod = random_kod(seed=11)
    dbdir = write_database(tmp_path / "db", [table_record({1: b"Hammersley"})], kod=kod)

    result = run_command("cli", ["export", "--jsonl", "--kod", bytes(kod).hex(), dbdir])

    assert result.returncode == 0, result.stderr
    (record,) = [line for line in jsonl_lines(result.stdout) if line["type"] == "record"]
    assert record == record_line(1, {"Entry #2": "Hammersley"})
