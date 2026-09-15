# ABOUTME: Tests for the croconvert command's HTML, PostgreSQL and CSV exports of crafted and sample databases.
# ABOUTME: They run the real command as a subprocess and check its stdout, stderr and output files.
import csv
import struct
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import override

import pytest
from cronos_builder import (
    TEST_DB,
    TEST_TABLE_FIELD_COUNT,
    TEST_TABLE_FILE_FIELD_INDEX,
    TEST_TABLE_ID,
    bank_record,
    complex_field,
    file_record,
    file_reference_field,
    stru_records_from_test_db,
    write_database,
    write_datafile,
)

from cronos_extract.Database import Database
from cronos_extract.koddecoder import INITIAL_KOD, KODcoding

# The offset of the table id in a table definition of TEST_DB, which has version 3 and an extra dword.
TABLE_ID_OFFSET = 14


def run_croconvert(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "cronos_extract.croconvert", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def record_with_file_field(file_field: bytes) -> bytes:
    """Build a record of the test table whose fields are empty except for the file reference `file_field`."""
    fields = [b""] * TEST_TABLE_FIELD_COUNT
    fields[TEST_TABLE_FILE_FIELD_INDEX] = file_field
    return bank_record(TEST_TABLE_ID, fields)


class TagCollector(HTMLParser):
    """Collects the name and attributes of every start tag in an HTML document."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, list[tuple[str, str | None]]]] = []

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, attrs))


def start_tags(html: str, name: str) -> list[list[tuple[str, str | None]]]:
    collector = TagCollector()
    collector.feed(html)
    collector.close()
    return [attrs for tag, attrs in collector.tags if tag == name]


def test_table_definition_warnings_go_to_stderr_not_into_the_sql() -> None:
    result = run_croconvert(["-t", "postgres", str(TEST_DB)])

    assert result.returncode == 0, result.stderr
    assert "Warning" not in result.stdout
    assert "Warning: FieldDefinition Section 2 not marked with a 2" in result.stderr


def test_db_definition_errors_go_to_stderr_not_into_the_sql() -> None:
    result = run_croconvert(["--nokod", "-t", "postgres", str(TEST_DB)])

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert "WARN: expected dbinfo to start with 0x03" in result.stderr
    assert "ERROR decoding db definition" in result.stderr


def test_html_escapes_a_hostile_file_name_in_the_download_attribute(tmp_path: Path) -> None:
    hostile_name = 'x" onmouseover="alert(1)'
    dbdir = write_database(
        tmp_path / "db", [file_record(b"DATA"), record_with_file_field(file_reference_field(hostile_name, "pdf", 1))]
    )

    result = run_croconvert([dbdir])

    assert result.returncode == 0, result.stderr
    (link,) = start_tags(result.stdout, "a")[1:]
    assert [name for name, _ in link] == ["download", "href"]
    assert dict(link)["download"] == hostile_name + ".pdf"
    assert dict(link)["href"] == "data:application/x-binary;base64,REFUQQ=="


def test_postgres_output_is_not_html_escaped(tmp_path: Path) -> None:
    fields = [b""] * TEST_TABLE_FIELD_COUNT
    fields[1] = b'<b>&"O\'Brien"</b>'
    dbdir = write_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, fields)])

    result = run_croconvert(["-t", "postgres", dbdir])

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


def assert_skipped_file_warnings(stderr: str) -> None:
    for recno, filename in [(4, "letters.pdf"), (5, "deleted.pdf"), (6, "missing.pdf")]:
        assert any(
            "Warning" in line and f"record {recno}" in line and filename in line for line in stderr.splitlines()
        ), f"no warning about {filename} of record {recno} in stderr: {stderr}"


def test_csv_export_skips_unreadable_file_references(tmp_path: Path) -> None:
    dbdir = unreadable_file_references_database(tmp_path / "db")
    outdir = tmp_path / "out"

    result = run_croconvert(["--csv", "-o", str(outdir), dbdir])

    assert result.returncode == 0, result.stderr
    assert_skipped_file_warnings(result.stderr)
    assert [path.name for path in (outdir / "Files-Referenced").iterdir()] == ["good.pdf"]
    assert (outdir / "Files-Referenced" / "good.pdf").read_bytes() == b"GOOD"


def test_html_export_skips_unreadable_file_references(tmp_path: Path) -> None:
    dbdir = unreadable_file_references_database(tmp_path / "db")

    result = run_croconvert([dbdir])

    assert result.returncode == 0, result.stderr
    assert_skipped_file_warnings(result.stderr)
    assert [dict(link).get("download") for link in start_tags(result.stdout, "a")[1:]] == ["good.pdf"]
    assert "</html>" in result.stdout


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

    result = run_croconvert(["--csv", "-o", str(outdir), dbdir])

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

    result = run_croconvert(["-t", "postgres", dbdir])

    assert result.returncode == 0, result.stderr
    assert "WARN" not in result.stdout
    assert "WARN: leftover data in .tad" in result.stderr


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
        assert any("Warning" in line and f"record {recno}" in line and f'"{fieldname}"' in line for line in lines), (
            f"no warning about field {fieldname} of record {recno} in stderr: {stderr}"
        )
    assert "2 records" in lines[-1], f"no count of affected records at the end of stderr: {stderr}"


def test_csv_export_keeps_the_decoded_fields_of_broken_records(tmp_path: Path) -> None:
    dbdir = partly_broken_records_database(tmp_path / "db")
    outdir = tmp_path / "out"

    result = run_croconvert(["--csv", "-o", str(outdir), dbdir])

    assert result.returncode == 0, result.stderr
    assert_partly_broken_record_warnings(result.stderr)
    with (outdir / "erdgeist.csv").open(encoding="utf-8", newline="") as csvfile:
        rows = list(csv.reader(csvfile))[1:]
    assert rows == [
        ["1", "intact", "", "", "", "", "", "", "", "", "", ""],
        ["2", "first", "", "", "", "", "", "", "", "", "", ""],
        ["3", "first", "", "", "", "", "", "after", "", "", "", ""],
    ]


@pytest.mark.parametrize("template_args", [[], ["-t", "postgres"]], ids=["html", "postgres"])
def test_template_export_keeps_the_decoded_fields_of_broken_records(tmp_path: Path, template_args: list[str]) -> None:
    dbdir = partly_broken_records_database(tmp_path / "db")

    result = run_croconvert([*template_args, dbdir])

    assert result.returncode == 0, result.stderr
    assert_partly_broken_record_warnings(result.stderr)
    assert "intact" in result.stdout
    assert "after" in result.stdout


def insert_statements(sql: str) -> list[str]:
    return [line for line in sql.splitlines() if line.lstrip().startswith("INSERT")]


def test_postgres_output_has_no_insert_for_an_empty_table(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [])

    result = run_croconvert(["-t", "postgres", dbdir])

    assert result.returncode == 0, result.stderr
    assert 'CREATE TABLE "erdgeist"' in result.stdout
    assert insert_statements(result.stdout) == []


def test_postgres_output_has_one_insert_per_record(tmp_path: Path) -> None:
    first = [b""] * TEST_TABLE_FIELD_COUNT
    first[1] = b"one"
    second = [b""] * TEST_TABLE_FIELD_COUNT
    second[1] = b"two"
    dbdir = write_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, first), bank_record(TEST_TABLE_ID, second)])

    result = run_croconvert(["-t", "postgres", dbdir])

    assert result.returncode == 0, result.stderr
    inserts = insert_statements(result.stdout)
    assert len(inserts) == 2
    assert all(line.startswith('INSERT INTO "erdgeist" VALUES (') and line.endswith(");") for line in inserts)
    assert "'one'" in inserts[0]
    assert "'two'" in inserts[1]


class TableShapes(HTMLParser):
    """Records, for every HTML table, the number of cells in each row, plus the tr and img tags seen."""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[int]] = []
        self.tr_starts = 0
        self.tr_ends = 0
        self.images = 0

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self.tables.append([])
        elif tag == "tr":
            self.tr_starts += 1
            self.tables[-1].append(0)
        elif tag in ("th", "td"):
            self.tables[-1][-1] += 1
        elif tag == "img":
            self.images += 1

    @override
    def handle_endtag(self, tag: str) -> None:
        if tag == "tr":
            self.tr_ends += 1


def test_html_tables_are_well_formed(tmp_path: Path) -> None:
    dbdir = write_database(
        tmp_path / "db",
        [
            file_record(b"DATA"),
            record_with_file_field(file_reference_field("report", "pdf", 1)),
            record_with_file_field(b""),
        ],
    )

    result = run_croconvert([dbdir])

    assert result.returncode == 0, result.stderr
    shapes = TableShapes()
    shapes.feed(result.stdout)
    shapes.close()
    assert shapes.tr_starts == shapes.tr_ends
    assert shapes.images == 0
    assert len(shapes.tables) == 2
    for rows in shapes.tables:
        assert len(rows) > 1
        assert len(set(rows)) == 1, f"rows of one table have different numbers of cells: {rows}"


def test_croconvert_stops_with_a_clear_message_without_crostru(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [])
    (Path(dbdir) / "CroStru.dat").unlink()
    (Path(dbdir) / "CroStru.tad").unlink()

    result = run_croconvert(["-t", "postgres", dbdir])

    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert "CroStru.dat" in result.stderr
    assert dbdir in result.stderr
    assert result.stdout == ""


def duplicate_table_name_database(directory: Path) -> str:
    """Write a database with two tables named "erdgeist", ids 1 and 2, holding records "one" and "two".

    The second table is the first table's definition with its table id changed, added to CroStru's
    database definition as an inline Base002 entry.
    """
    stru = stru_records_from_test_db()
    with Database(str(TEST_DB), False, KODcoding(INITIAL_KOD)) as db:
        assert db.stru is not None
        base001 = db.decode_db_definition(db.stru.readrec(1)[1:])["Base001"]
    base002 = base001[:TABLE_ID_OFFSET] + struct.pack("<L", 2) + base001[TABLE_ID_OFFSET + 4 :]
    name = b"Base002"
    database_definition = stru[0]
    assert database_definition is not None
    stru[0] = database_definition + bytes([len(name)]) + name + struct.pack("<L", len(base002) | 0x80000000) + base002
    write_datafile(directory, "Stru", stru)

    fields_one = [b""] * TEST_TABLE_FIELD_COUNT
    fields_one[1] = b"one"
    fields_two = [b""] * TEST_TABLE_FIELD_COUNT
    fields_two[1] = b"two"
    write_datafile(directory, "Bank", [bank_record(TEST_TABLE_ID, fields_one), bank_record(2, fields_two)])
    return str(directory)


def test_csv_export_writes_tables_with_the_same_name_to_different_files(tmp_path: Path) -> None:
    dbdir = duplicate_table_name_database(tmp_path / "db")
    outdir = tmp_path / "out"

    result = run_croconvert(["--csv", "-o", str(outdir), dbdir])

    assert result.returncode == 0, result.stderr
    tables = {}
    for path in outdir.glob("*.csv"):
        with path.open(encoding="utf-8", newline="") as csvfile:
            tables[path.name] = [row[2] for row in list(csv.reader(csvfile))[1:]]
    assert tables == {"erdgeist.csv": ["one"], "erdgeist-2.csv": ["two"]}


def test_postgres_output_gives_tables_with_the_same_name_different_names(tmp_path: Path) -> None:
    dbdir = duplicate_table_name_database(tmp_path / "db")

    result = run_croconvert(["-t", "postgres", dbdir])

    assert result.returncode == 0, result.stderr
    creates = [line for line in result.stdout.splitlines() if line.startswith("CREATE TABLE")]
    assert creates == ['CREATE TABLE "erdgeist" (', 'CREATE TABLE "erdgeist-2" (']
    inserts = insert_statements(result.stdout)
    assert len(inserts) == 2
    assert inserts[0].startswith('INSERT INTO "erdgeist" VALUES (') and "'one'" in inserts[0]
    assert inserts[1].startswith('INSERT INTO "erdgeist-2" VALUES (') and "'two'" in inserts[1]


def test_postgres_output_writes_null_for_empty_values_in_columns_that_are_not_text(tmp_path: Path) -> None:
    fields = [b""] * TEST_TABLE_FIELD_COUNT
    fields[1] = b"text"
    dbdir = write_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, fields)])

    result = run_croconvert(["-t", "postgres", dbdir])

    assert result.returncode == 0, result.stderr
    assert insert_statements(result.stdout) == [
        "INSERT INTO \"erdgeist\" VALUES ('1', NULL, 'text', '', NULL, NULL, '', '', '', '', '', '');"
    ]
