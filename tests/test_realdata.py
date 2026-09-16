# ABOUTME: Checks the cronos_extract API against Ben's real CronosPro databases, found under roots listed in local/.
# ABOUTME: Deselected by default; run with `uv run pytest -m realdata`. Test ids are indexes, never paths.
import contextlib
import functools
import io
import itertools
import struct
from pathlib import Path

import pytest
from cronos_builder import tad_layout

import cronos_extract
import cronos_extract.koddecoder
from cronos_extract._api.info import read_file_info
from cronos_extract.Database import Database
from cronos_extract.survey import SurveyedDatabase, read_path_list, survey_databases

pytestmark = pytest.mark.realdata

# Each entry of the list is a survey root, as `cronos-extract survey --list` treats it: the databases are the
# directories under it that hold Cro*.dat files.
LIST_FILE = Path(__file__).resolve().parent.parent / "local" / "mash_datasets_with_CroIndex_dat.txt"
# Every Table.records() call walks all of CroBank, so databases with larger CroBank indexes are left out of the
# checks that read records.
MAX_BANK_TAD_BYTES = 32_000_000
# The number of records compared per table.
RECORDS_COMPARED = 500
# The number of .tad entries checked per file in the v4 deleted-length check.
TAD_ENTRIES_CHECKED = 1_000_000
DBCRACK_TEST = "test_dbcrack_recovers_a_kod_that_opens_a_v4_database"
# The tests that run on the 01.11 databases only.
V4_TESTS = ("test_v4_tad_entries_never_use_the_v3_deleted_length", DBCRACK_TEST)
# dbcrack recovers the KOD of the v4 databases whose CroBank header says KOD-encoded. Neither crack method
# recovers it for the others.
V4_CRACK_XFAIL = pytest.mark.xfail(
    strict=True,
    reason="neither crack method recovers the KOD of a real 01.11 database whose CroBank header is not "
    "KOD-encoded; how v4 encodes records is an open item",
)


@functools.cache
def found_databases() -> list[SurveyedDatabase]:
    """The databases under every listed root, each directory once, in the order the survey finds them."""
    roots = [path for path in read_path_list(LIST_FILE) if path.is_dir()] if LIST_FILE.exists() else []
    found: dict[Path, SurveyedDatabase] = {}
    for root in roots:
        for surveyed in survey_databases(root):
            found.setdefault(surveyed.directory.resolve(), surveyed)
    return list(found.values())


def survey_of(directory: Path) -> SurveyedDatabase:
    return next(database for database in found_databases() if database.directory == directory)


def named(directory: Path, filename: str) -> Path | None:
    """The file in `directory` named `filename`, matched case-insensitively."""
    return next((path for path in sorted(directory.iterdir()) if path.name.lower() == filename.lower()), None)


def bank_is_small(directory: Path) -> bool:
    tad = named(directory, "CroBank.tad")
    return tad is not None and tad.stat().st_size <= MAX_BANK_TAD_BYTES


def is_v4(directory: Path) -> bool:
    dat = named(directory, "CroStru.dat")
    return dat is not None and read_file_info("Stru", dat).version == "01.11"


def bank_header_is_kod_encoded(directory: Path) -> bool:
    return any(info.name.lower() == "bank" and info.kod_encoded for info in survey_of(directory).files)


def open_or_skip(dbdir: Path, *, compact: bool = False) -> cronos_extract.Bank:
    """The bank in `dbdir`, opened with the default KOD, or a skip when it does not open."""
    try:
        return cronos_extract.open(dbdir, compact=compact)
    except cronos_extract.CronosError:
        pytest.skip("the database does not open with the default KOD")


def realdata_is_selected(config: pytest.Config) -> bool:
    markexpr = str(config.getoption("markexpr"))
    return "realdata" in markexpr and "not realdata" not in markexpr


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """
    Parametrise each test over the real databases, with ids db00, db01, and so on.

    The listed roots are walked only when the realdata marker is selected, so a default run never reads them.
    """
    if "dbdir" not in metafunc.fixturenames:
        return
    databases = [database.directory for database in found_databases()] if realdata_is_selected(metafunc.config) else []
    name = metafunc.function.__name__
    cases = [
        pytest.param(
            database,
            id=f"db{index:02d}",
            marks=V4_CRACK_XFAIL if name == DBCRACK_TEST and not bank_header_is_kod_encoded(database) else (),
        )
        for index, database in enumerate(databases)
        if name not in V4_TESTS or is_v4(database)
    ]
    metafunc.parametrize("dbdir", cases)


def test_open_reads_every_table_or_raises_a_cronos_error(dbdir: Path, capfd: pytest.CaptureFixture[str]) -> None:
    if not bank_is_small(dbdir):
        pytest.skip("CroBank is too large to walk once per table")
    try:
        bank = cronos_extract.open(dbdir)
    except cronos_extract.CronosError:
        pass
    else:
        with bank:
            for table in bank.tables:
                for _ in itertools.islice(table.records(), RECORDS_COMPARED):
                    pass
            list(itertools.islice(bank.files(), RECORDS_COMPARED))
    captured = capfd.readouterr()
    assert (captured.out, captured.err) == ("", "")


def test_field_text_matches_database_enumerate_records(dbdir: Path) -> None:
    if not bank_is_small(dbdir):
        pytest.skip("CroBank is too large to walk once per table")
    with (
        open_or_skip(dbdir) as bank,
        contextlib.redirect_stderr(io.StringIO()),
        Database(str(dbdir), False, cronos_extract.koddecoder.new()) as db,
    ):
        internal = {(table.tableid, table.tablename): table for table in db.enumerate_tables()}
        assert {(table.id, table.name) for table in bank.tables} == set(internal)
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


def test_bank_info_agrees_with_the_survey(dbdir: Path) -> None:
    survey = survey_of(dbdir)
    # compact=True reads .tad entries on demand, so a multi-GB CroBank.tad is not loaded into memory.
    with open_or_skip(dbdir, compact=True) as bank:
        by_path = {info.path: info for info in survey.files}
        for info in bank.info:
            if info.problem is None:
                assert info == by_path[info.path]


def test_tad_layout_matches_what_the_builder_writes(dbdir: Path) -> None:
    checked = 0
    for info in survey_of(dbdir).files:
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


def test_dbcrack_recovers_a_kod_that_opens_a_v4_database(dbdir: Path) -> None:
    kod = cronos_extract.crack_kod(dbdir, "dbcrack")

    assert kod is not None
    # compact=True reads .tad entries on demand, so a multi-GB CroBank.tad is not loaded into memory.
    with cronos_extract.open(dbdir, kod=kod, compact=True) as bank:
        assert bank.tables
