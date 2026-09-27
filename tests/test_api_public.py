# ABOUTME: Tests for the public surface of cronos_extract: the names in __all__, the examples, py.typed and docs/api.md.
# ABOUTME: Uses a database from tests/cronos_builder.py through `import cronos_extract` only.
import datetime
import re
import typing
from pathlib import Path

import pytest
from cronos_builder import TEST_TABLE_ID, bank_record, write_database

import cronos_extract

PUBLIC_NAMES = [
    "Bank",
    "CronosError",
    "DatabaseDefinitionError",
    "Diagnostic",
    "DiagnosticKind",
    "EmbeddedFile",
    "Field",
    "FieldDefinition",
    "FileInfo",
    "FileReference",
    "Generation",
    "Kod",
    "NotACronosFile",
    "Record",
    "Table",
    "UnsupportedVersion",
    "WrongKod",
    "crack_kod",
    "open",
]
API_REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "api.md"
# The directory the example in docs/api.md opens, relative to the directory it runs in.
EXAMPLE_DATABASE = "path/to/database"
# What the example prints for the database that test_the_api_reference_example_runs builds: the builder's copy of
# TEST_DB's table definitions gives two diagnostics, then the one record.
EXAMPLE_OUTPUT = (
    "warning: unexpected_structure Base000: FieldDefinition Section 2 not marked with a 2\n"
    "warning: unexpected_structure Base001: FieldDefinition Section 2 not marked with a 2\n"
    "erdgeist 1 ['1', '42', 'Hammersley', '', '2024-03-15', '09:30', '', '', '', '', '', '']\n"
)


def test_the_public_names_are_exactly_those_in_all() -> None:
    assert cronos_extract.__all__ == PUBLIC_NAMES
    for name in PUBLIC_NAMES:
        # Generation is a plain Literal alias, not a class, so it has no cronos_extract module of its own.
        if name == "Generation":
            continue
        module = getattr(cronos_extract, name).__module__
        # Diagnostic and DiagnosticKind are shared with the internal readers, which report them.
        if name in ("Diagnostic", "DiagnosticKind"):
            assert module == "cronos_extract._diagnostic"
        else:
            assert module.startswith("cronos_extract._api.")


def test_generation_lists_the_four_cronospro_generations() -> None:
    assert typing.get_args(cronos_extract.Generation) == ("v3", "v4", "v7", "unknown")


def test_wrong_kod_is_a_cronos_error() -> None:
    assert issubclass(cronos_extract.WrongKod, cronos_extract.CronosError)


def test_the_roadmap_example_reads_a_record(tmp_path: Path) -> None:
    fields = [b"42", b"Hammersley", b"", b"1240315", b"0930", b"", b"", b"", b"", b"", b""]
    path = write_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, fields)])

    values = []
    with cronos_extract.open(path, kod=cronos_extract.Kod.default(), compact=False, on_diagnostic=None) as bank:
        for table in bank.tables:
            for record in table.records():
                values.append(record["Entry #4"].value)

    assert values == [datetime.date(2024, 3, 15)]


def test_the_package_is_marked_as_typed() -> None:
    assert (Path(cronos_extract.__file__).parent / "py.typed").is_file()


def inline_code(markdown: str) -> set[str]:
    """The text of every inline code span in `markdown`, outside fenced code blocks."""
    prose = re.sub(r"^```.*?^```", "", markdown, flags=re.MULTILINE | re.DOTALL)
    return set(re.findall(r"`([^`\n]+)`", prose))


def test_the_api_reference_names_every_public_name_and_diagnostic_kind() -> None:
    spans = inline_code(API_REFERENCE.read_text(encoding="utf-8"))

    missing = [name for name in cronos_extract.__all__ if name not in spans and f"{name}()" not in spans]
    missing += [kind.value for kind in cronos_extract.DiagnosticKind if kind.value not in spans]

    assert missing == []


def test_the_api_reference_example_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fields = [b"42", b"Hammersley", b"", b"1240315", b"0930", b"", b"", b"", b"", b"", b""]
    write_database(tmp_path / EXAMPLE_DATABASE, [bank_record(TEST_TABLE_ID, fields)])
    example = re.search(r"^```python\n(.*?)^```", API_REFERENCE.read_text(encoding="utf-8"), re.MULTILINE | re.DOTALL)
    assert example is not None, f"{API_REFERENCE} has no python code block"
    monkeypatch.chdir(tmp_path)

    exec(compile(example[1], str(API_REFERENCE), "exec"), {"__name__": "__main__"})

    assert capsys.readouterr().out == EXAMPLE_OUTPUT
