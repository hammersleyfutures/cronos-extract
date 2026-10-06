# ABOUTME: Tests that test_data/sample_bank is what tests/cronos_builder.py's write_sample_bank writes, and its records.
# ABOUTME: Run pytest with --update-golden to rewrite test_data/sample_bank after a deliberate change to the builder.
import datetime
import shutil
from pathlib import Path

import pytest
from cronos_builder import write_sample_bank

import cronos_extract

SAMPLE_BANK = Path(__file__).resolve().parent.parent / "test_data" / "sample_bank"

pytestmark = pytest.mark.usefixtures("prints_nothing")


def test_the_sample_bank_is_what_the_builder_writes(tmp_path: Path, request: pytest.FixtureRequest) -> None:
    write_sample_bank(tmp_path / "sample_bank")
    if request.config.getoption("--update-golden"):
        shutil.rmtree(SAMPLE_BANK, ignore_errors=True)
        shutil.copytree(tmp_path / "sample_bank", SAMPLE_BANK)

    written = {path.name: path.read_bytes() for path in sorted((tmp_path / "sample_bank").iterdir())}
    committed = {path.name: path.read_bytes() for path in sorted(SAMPLE_BANK.iterdir())}
    assert committed == written, "run `uv run pytest --update-golden tests/test_sample_bank.py` to rewrite it"


def test_the_sample_bank_holds_live_records_of_each_kind() -> None:
    with cronos_extract.open(SAMPLE_BANK) as bank:
        (table,) = bank.tables
        records = list(table.records())
        files = list(bank.files())
        references = [record["Entry #6"].value for record in records]
        stored, unstored = (
            bank.read_file(reference) for reference in references if isinstance(reference, cronos_extract.FileReference)
        )
        diagnostic_kinds = [diagnostic.kind for diagnostic in bank.diagnostics]

    assert [record.number for record in records] == [1, 2, 3]
    assert [record["Entry #2"].value for record in records] == ["Hammersley", "Ivanova", "Smith"]
    assert records[0]["Entry #3"].value == "Привет"
    assert [record["Entry #4"].value for record in records] == [datetime.date(2024, 3, 15), "1985-00-00", None]
    assert [record["Entry #5"].value for record in records] == [datetime.time(9, 30), None, datetime.time(17, 45)]
    assert [record["Entry #6"].value for record in records] == [
        cronos_extract.FileReference("notes", "txt", 4, table="erdgeist", referrer=1, field="Entry #6"),
        None,
        cronos_extract.FileReference("scan", "jpg", None, table="erdgeist", referrer=3, field="Entry #6"),
    ]
    assert files == [cronos_extract.EmbeddedFile(4, b"Hello from the Files table.\n", None)]
    assert stored == cronos_extract.EmbeddedFile(4, b"Hello from the Files table.\n", "notes.txt")
    assert unstored is None
    assert cronos_extract.DiagnosticKind.UNRESOLVED_FILE_REFERENCE in diagnostic_kinds
    assert [info.version for info in bank.info] == ["01.02", "01.02"]
