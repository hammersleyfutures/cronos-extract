# ABOUTME: Checks the cronos_extract API against Ben's real CronosPro databases, listed in the git-ignored local/.
# ABOUTME: Deselected by default; run with `uv run pytest -m realdata`. Test ids are list indexes, never paths.
import contextlib
import io
import itertools
import struct
from pathlib import Path

import pytest
from cronos_builder import tad_layout

from cronos_extract import koddecoder
from cronos_extract._api.bank import open as open_bank
from cronos_extract._api.crack import crack_kod
from cronos_extract._api.errors import CronosError
from cronos_extract._api.info import read_file_info
from cronos_extract.Database import Database
from cronos_extract.survey import read_path_list, survey_databases

pytestmark = pytest.mark.realdata

LIST_FILE = Path(__file__).resolve().parent.parent / "local" / "mash_datasets_with_CroIndex_dat.txt"
# Every Table.records() call walks all of CroBank, so databases with larger CroBank indexes are left out of the
# checks that read records.
MAX_BANK_TAD_BYTES = 32_000_000
# The number of records compared per table.
RECORDS_COMPARED = 500
# The number of .tad entries checked per file in the v4 deleted-length check.
TAD_ENTRIES_CHECKED = 1_000_000


def listed_databases() -> list[Path]:
    return [path for path in read_path_list(LIST_FILE) if path.is_dir()] if LIST_FILE.exists() else []


DATABASES = listed_databases()
IDS = [f"db{index:02d}" for index in range(len(DATABASES))]


def named(directory: Path, filename: str) -> Path | None:
    """The file in `directory` named `filename`, matched case-insensitively."""
    return next((path for path in sorted(directory.iterdir()) if path.name.lower() == filename.lower()), None)


def bank_is_small(directory: Path) -> bool:
    tad = named(directory, "CroBank.tad")
    return tad is not None and tad.stat().st_size <= MAX_BANK_TAD_BYTES


def is_v4(directory: Path) -> bool:
    dat = named(directory, "CroStru.dat")
    return dat is not None and read_file_info("Stru", dat).version == "01.11"


V4 = [(database, IDS[index]) for index, database in enumerate(DATABASES) if is_v4(database)]
every_database = pytest.mark.parametrize("dbdir", DATABASES, ids=IDS)


@every_database
def test_open_reads_every_table_or_raises_a_cronos_error(dbdir: Path, capfd: pytest.CaptureFixture[str]) -> None:
    if not bank_is_small(dbdir):
        pytest.skip("CroBank is too large to walk once per table")
    try:
        bank = open_bank(dbdir)
    except CronosError:
        pass
    else:
        with bank:
            for table in bank.tables:
                for _ in itertools.islice(table.records(), RECORDS_COMPARED):
                    pass
            list(itertools.islice(bank.files(), RECORDS_COMPARED))
    captured = capfd.readouterr()
    assert (captured.out, captured.err) == ("", "")


@every_database
def test_field_text_matches_database_enumerate_records(dbdir: Path) -> None:
    if not bank_is_small(dbdir):
        pytest.skip("CroBank is too large to walk once per table")
    try:
        bank = open_bank(dbdir)
    except CronosError:
        pytest.skip("the database does not open with the default KOD")
    with bank, contextlib.redirect_stderr(io.StringIO()), Database(str(dbdir), False, koddecoder.new()) as db:
        internal = {(table.tableid, table.tablename): table for table in db.enumerate_tables()}
        for table in bank.tables:
            expected = [
                (record.recno, [field.content for field in record.fields])
                for record in itertools.islice(db.enumerate_records(internal[(table.id, table.name)]), RECORDS_COMPARED)
            ]
            actual = [
                (record.number, [field.text for field in record.fields])
                for record in itertools.islice(table.records(), RECORDS_COMPARED)
            ]
            assert actual == expected, f"table id {table.id} differs"


@every_database
def test_bank_info_agrees_with_the_survey(dbdir: Path) -> None:
    surveyed = next(survey_databases(dbdir))
    assert surveyed.directory == dbdir
    try:
        bank = open_bank(dbdir)
    except CronosError:
        pytest.skip("the database does not open with the default KOD")
    with bank:
        by_path = {info.path: info for info in surveyed.files}
        for info in bank.info:
            if info.problem is None:
                assert info == by_path[info.path]


@every_database
def test_tad_layout_matches_what_the_builder_writes(dbdir: Path) -> None:
    checked = 0
    for info in next(survey_databases(dbdir)).files:
        if info.version is None or info.version not in ("01.02", "01.03", "01.11"):
            continue
        tad = named(dbdir, f"Cro{info.name}.tad")
        if tad is None:
            continue
        header, entry = tad_layout(info.version.encode())
        with tad.open("rb") as file:
            start = file.read(len(header))
        assert (tad.stat().st_size - len(header)) % entry.size == 0, f"Cro{info.name}.tad entry size"
        if info.version == "01.11":
            assert (start[:4], start[12:16]) == (header[:4], header[12:16]), f"Cro{info.name}.tad header"
        checked += 1
    assert checked > 0


@pytest.mark.parametrize("dbdir", [database for database, _ in V4], ids=[test_id for _, test_id in V4])
def test_v4_tad_entries_never_use_the_v3_deleted_length(dbdir: Path) -> None:
    for base in ("Stru", "Bank", "Index"):
        tad = named(dbdir, f"Cro{base}.tad")
        if tad is None:
            continue
        with tad.open("rb") as file:
            file.seek(16)
            data = file.read(16 * TAD_ENTRIES_CHECKED)
        usable = len(data) - len(data) % 16
        lengths = {length for _, length, _ in struct.iter_unpack("<QLL", data[:usable])}
        assert 0xFFFFFFFF not in lengths, f"Cro{base}.tad"


@pytest.mark.parametrize("dbdir", [database for database, _ in V4], ids=[test_id for _, test_id in V4])
def test_dbcrack_recovers_a_kod_that_opens_a_v4_database(dbdir: Path) -> None:
    kod = crack_kod(dbdir, "dbcrack")

    assert kod is not None
    with open_bank(dbdir, kod=kod) as bank:
        assert bank.tables
