# ABOUTME: Tests for the public surface of cronos_extract: the names in __all__, the roadmap's example, and py.typed.
# ABOUTME: Uses a database from tests/cronos_builder.py through `import cronos_extract` only.
import datetime
from pathlib import Path

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
    "Kod",
    "NotACronosFile",
    "Record",
    "Table",
    "UnsupportedVersion",
    "crack_kod",
    "open",
]


def test_the_public_names_are_exactly_those_in_all() -> None:
    assert cronos_extract.__all__ == PUBLIC_NAMES
    for name in PUBLIC_NAMES:
        module = getattr(cronos_extract, name).__module__
        # Diagnostic and DiagnosticKind are shared with the internal readers, which report them.
        if name in ("Diagnostic", "DiagnosticKind"):
            assert module == "cronos_extract._diagnostic"
        else:
            assert module.startswith("cronos_extract._api.")


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
