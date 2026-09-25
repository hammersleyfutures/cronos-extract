# ABOUTME: Tests for the export subcommand: each format's layout, the -o rules, diagnostics and exit statuses.
# ABOUTME: They export crafted databases from tests/cronos_builder.py, in this process or by running the command.
import csv
import json
import os
import re
from pathlib import Path

import pytest
from cli import run_command, run_in_process
from cronos_builder import (
    TEST_DB,
    TEST_TABLE_FIELD_COUNT,
    TEST_TABLE_ID,
    bank_record,
    database_with_extra_definition_key,
    database_with_files_abbreviation,
    duplicate_table_name_database,
    erdgeist_table_definition,
    file_record,
    file_reference_field,
    patched_table_definition,
    random_kod,
    record_with_file_field,
    renamed_table_definition,
    write_database,
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
