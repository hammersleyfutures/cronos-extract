# ABOUTME: Pins the API's field text against a committed golden file per builder version, KOD and record layout.
# ABOUTME: Generated with --update-golden; test_api_bank.py checks each file against Database.enumerate_records too.
from collections.abc import Callable
from pathlib import Path

import pytest
from cronos_builder import write_database
from test_api_bank import PARITY_CASES, golden_api_name, parity_case_id, parity_records, render_api_jsonl

import cronos_extract


@pytest.mark.parametrize("extended", [False, True], ids=["inline", "extended"])
@pytest.mark.parametrize(
    ("version", "kod"),
    PARITY_CASES,
    ids=parity_case_id,
)
def test_api_output_matches_its_golden_file(
    tmp_path: Path,
    golden: Callable[[str, str], None],
    version: bytes,
    kod: list[int] | None,
    extended: bool,
) -> None:
    dbdir = write_database(tmp_path / "db", parity_records(version), kod, version=version, extended=extended)

    with cronos_extract.open(
        dbdir, kod=cronos_extract.Kod.from_table(kod) if kod else cronos_extract.Kod.default()
    ) as bank:
        rendered = render_api_jsonl(bank)

    golden(golden_api_name(version, kod, extended=extended), rendered)
