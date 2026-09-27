# ABOUTME: Checks the cronos_extract API against Ben's real CronosPro databases, found under roots listed in local/.
# ABOUTME: Deselected by default; run with `uv run pytest -m realdata`. Test ids are indexes, never paths.
import functools
import hashlib
import itertools
import json
import subprocess
from pathlib import Path

import pytest
from cli import run_command
from cronos_builder import ignore_problems, tad_layout

import cronos_extract
from cronos_extract._api.info import read_file_info
from cronos_extract._cli.sql_out import unique_sql_table_name
from cronos_extract._format.tad import DELETED_LENGTH, V4_FLAG_SHIFT, is_v4_deleted
from cronos_extract._format.tad import tad_layout as production_tad_layout
from cronos_extract.Datamodel import TableDefinition, is_table_key
from cronos_extract.survey import SurveyedDatabase, read_path_list, survey_databases

pytestmark = pytest.mark.realdata

# Each entry of the list is a survey root, as `cronos-extract survey --list` treats it: the databases are the
# directories under it that hold Cro*.dat files.
LIST_FILE = Path(__file__).resolve().parent.parent / "local" / "mash_datasets_with_CroIndex_dat.txt"
# Record counts and SHA-256 fingerprints of the API's field text, keyed by database directory; git-ignored.
FINGERPRINTS = LIST_FILE.parent / "realdata-fingerprints.json"
# The number of records compared per table.
RECORDS_COMPARED = 500
# The number of .tad entries read per chunk in the v4 deleted-length check, which reads every entry.
TAD_ENTRIES_CHECKED = 1_000_000
# The number of the first live CroBank records the garbage check samples, and the fraction of them that must carry
# a table id the definition names.
LIVE_RECORDS_SAMPLED = 10_000
LIVE_RECORDS_MATCH_FRACTION = 0.9
# The garbage check skips a database with fewer live CroBank records than this, too few to judge a fraction by.
MIN_LIVE_RECORDS_SAMPLED = 100
DBCRACK_TEST = "test_dbcrack_recovers_a_kod_that_opens_a_v4_database"
# The tests that run on the 01.11 databases only.
V4_TESTS = ("test_v4_tad_entries_never_use_the_v3_deleted_length", DBCRACK_TEST)
# dbcrack recovers the KOD of the v4 databases whose CroBank header says KOD-encoded. Neither crack method
# recovers it for the others.
V4_CRACK_XFAIL = pytest.mark.xfail(
    strict=True,
    reason="dbcrack returns None: this database's CroBank and CroIndex are not KOD-encoded, so there are no encoded "
    "records to learn from; its CroStru is encoded with its own KOD and holds too few records for strucrack, which "
    "is Phase 3e's question",
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


def is_v4(directory: Path) -> bool:
    """Whether CroBank's own header says v4; a database's CroBank can be v4 while its CroStru is v3."""
    dat = named(directory, "CroBank.dat")
    return dat is not None and read_file_info("Bank", dat).generation == "v4"


def bank_header_is_kod_encoded(directory: Path) -> bool:
    return any(info.name.lower() == "bank" and info.kod_encoded for info in survey_of(directory).files)


def open_or_skip(dbdir: Path, *, compact: bool = False) -> cronos_extract.Bank:
    """The bank in `dbdir`, opened with the default KOD, or a skip when it does not open."""
    try:
        return cronos_extract.open(dbdir, compact=compact)
    except cronos_extract.CronosError as error:
        raise pytest.skip.Exception("the database does not open with the default KOD") from error


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


def test_no_real_database_reports_a_checksum_mismatch(dbdir: Path) -> None:
    with open_or_skip(dbdir) as bank:
        for table in bank.tables:
            for _ in itertools.islice(table.records(), RECORDS_COMPARED):
                pass
        list(itertools.islice(bank.files(), RECORDS_COMPARED))
        assert bank.diagnostic_counts[cronos_extract.DiagnosticKind.CHECKSUM_MISMATCH] == 0


def api_fingerprint(dbdir: Path) -> dict[str, object]:
    """The record count and a SHA-256 of the API's field texts for the first RECORDS_COMPARED records of each table."""
    with open_or_skip(dbdir) as bank:
        tables = []
        count = 0
        for table in bank.tables:
            records = [
                [record.number, [field.text for field in record.fields]]
                for record in itertools.islice(table.records(), RECORDS_COMPARED)
            ]
            count += len(records)
            tables.append({"id": table.id, "name": table.name, "records": records})
    text = json.dumps(tables, ensure_ascii=False, sort_keys=True)
    return {"records": count, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def test_api_output_matches_its_fingerprint(dbdir: Path, request: pytest.FixtureRequest) -> None:
    key = str(dbdir.resolve())
    fingerprint = api_fingerprint(dbdir)
    stored = json.loads(FINGERPRINTS.read_text(encoding="utf-8")) if FINGERPRINTS.exists() else {}
    if request.config.getoption("--update-golden"):
        stored[key] = fingerprint
        FINGERPRINTS.write_text(json.dumps(stored, indent=1, sort_keys=True), encoding="utf-8")
        return
    command = "uv run pytest -q -m realdata tests/test_realdata.py -k fingerprint --update-golden"
    assert key in stored, f"no fingerprint for this database; write them with: {command}"
    assert fingerprint == stored[key]


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
    """
    Every v4 .tad file's entries never use the v3 deleted length, and the header's deleted count equals the
    entries whose flags mark them deleted (bit 0x02 set, bit 0x01 clear); this runs on every Cro file whose own
    header is v4, since a database's CroBank can be v4 while its CroStru is v3.
    """
    checked = 0
    for info in survey_of(dbdir).files:
        if info.generation != "v4":
            continue
        tad = named(dbdir, f"Cro{info.name}.tad")
        if tad is None or info.version is None:
            continue
        layout = production_tad_layout(info.version.encode())
        assert layout is not None, f"Cro{info.name}.tad"
        with tad.open("rb") as file:
            header_deleted, _ = layout.deleted_counts(file.read(layout.header.size))
            deleted_by_flag = 0
            while chunk := file.read(layout.entry.size * TAD_ENTRIES_CHECKED):
                usable = len(chunk) - len(chunk) % layout.entry.size
                for offset, length, _checksum in layout.entry.iter_unpack(chunk[:usable]):
                    assert length != DELETED_LENGTH, f"Cro{info.name}.tad"
                    if is_v4_deleted(offset >> V4_FLAG_SHIFT):
                        deleted_by_flag += 1
        assert deleted_by_flag == header_deleted, f"Cro{info.name}.tad"
        checked += 1
    assert checked > 0


def test_dbcrack_recovers_a_kod_that_opens_a_v4_database(dbdir: Path) -> None:
    kod = cronos_extract.crack_kod(dbdir, "dbcrack")

    assert kod is not None
    # compact=True reads .tad entries on demand, so a multi-GB CroBank.tad is not loaded into memory.
    with cronos_extract.open(dbdir, kod=kod, compact=True) as bank:
        assert bank.tables


def defined_table_ids(bank: cronos_extract.Bank) -> set[int]:
    """Every table id the database definition names under a Base### key, table definitions that fail to decode aside."""
    definition = bank._database.read_db_definition()
    ids = set()
    for key, value in definition.items():
        if not is_table_key(key):
            continue
        image = definition.get("BaseImage" + key[4:], b"")
        try:
            table_definition = TableDefinition(value, image, report=ignore_problems)
        except Exception:
            continue
        ids.add(table_definition.tableid)
    return ids


def test_live_records_belong_to_the_tables_the_definition_names(dbdir: Path) -> None:
    """
    At least 90% of the first 10,000 live CroBank records carry the table id of a table in bank.tables or of the
    Files table, catching records decoded with the wrong KOD. A record whose id instead belongs to a table the
    definition names but bank.tables left out is counted separately, so a wrong KOD and a left-out table are told
    apart. Only a KOD-encoded CroBank can be decoded with the wrong KOD, and a fraction of fewer than 100 records
    says little, so any other database is skipped.
    """
    with open_or_skip(dbdir, compact=True) as bank:
        if not bank._bank_file.header.kod_encoded:
            pytest.skip("CroBank's header says its records are not KOD-encoded, so no KOD can decode them wrongly")
        known_ids = {table.id for table in bank.tables}
        if bank._files_table_id is not None:
            known_ids.add(bank._files_table_id)
        left_out_ids: set[int] | None = None
        sampled = 0
        matched = 0
        left_out = 0
        for number in range(1, bank._bank_file.nrofrecords + 1):
            if sampled >= LIVE_RECORDS_SAMPLED:
                break
            try:
                parts = bank._bank_file.read_record(number)
            except Exception:
                continue
            if parts is None or not parts.data:
                continue
            sampled += 1
            table_id = parts.data[0]
            if table_id in known_ids:
                matched += 1
                continue
            if left_out_ids is None:
                left_out_ids = defined_table_ids(bank) - known_ids
            if table_id in left_out_ids:
                left_out += 1
        if sampled < MIN_LIVE_RECORDS_SAMPLED:
            pytest.skip(f"{sampled} live CroBank records, fewer than the {MIN_LIVE_RECORDS_SAMPLED} the check needs")
        assert matched >= sampled * LIVE_RECORDS_MATCH_FRACTION, (
            f"{sampled - matched} of {sampled} sampled live records carry a table id bank.tables does not have "
            f"({left_out} of those are ids of tables the definition names but bank.tables left out)"
        )


# A command run over one real database is killed after this many seconds.
EXPORT_TIMEOUT = 1800
# The CSV export, which also writes every stored file, runs on this many of the smallest databases.
CSV_DATABASES = 3


def export_command(dbdir: Path, output: Path, *options: str) -> subprocess.CompletedProcess[str]:
    return run_command("cli", ["export", *options, "--compact", "-o", str(output), str(dbdir)], timeout=EXPORT_TIMEOUT)


def finished_or_failed_cleanly(result: subprocess.CompletedProcess[str]) -> bool:
    """Assert that the command exited 0, or 1 with one Error line last; return whether it finished."""
    assert "Traceback" not in result.stderr
    if result.returncode == 0:
        return True
    lines = result.stderr.splitlines()
    assert result.returncode == 1
    assert [line for line in lines if line.startswith("Error: ")] == [lines[-1]]
    return False


def api_record_count(dbdir: Path, *, sql: bool = False) -> int:
    """
    The number of records the API reads from the tables of `dbdir`, counting a repeated table once.

    With `sql`, a table is also skipped when its PostgreSQL name repeats an earlier table's, as SqlWriter.table()
    skips it, so the count matches what --postgres actually writes.
    """
    with open_or_skip(dbdir, compact=True) as bank:
        written: set[tuple[str, int]] = set()
        sql_names: dict[str, int] = {}
        count = 0
        for table in bank.tables:
            if (table.name, table.id) in written:
                continue
            written.add((table.name, table.id))
            if sql and unique_sql_table_name(table, sql_names) is None:
                continue
            count += sum(1 for _ in table.records())
        return count


@functools.cache
def smallest_databases() -> set[Path]:
    sized = []
    for surveyed in found_databases():
        tad = named(surveyed.directory, "CroBank.tad")
        if tad is not None:
            sized.append((tad.stat().st_size, surveyed.directory))
    return {directory for _, directory in sorted(sized)[:CSV_DATABASES]}


def test_export_jsonl_holds_every_record_the_api_reads(dbdir: Path, tmp_path: Path) -> None:
    output = tmp_path / "out.jsonl"

    result = export_command(dbdir, output, "--jsonl")

    if finished_or_failed_cleanly(result):
        lines = [json.loads(line) for line in output.read_bytes().decode("utf-8").split("\n")[:-1]]
        assert sum(line["type"] == "record" for line in lines) == api_record_count(dbdir)


def test_export_postgres_writes_one_insert_per_record(dbdir: Path, tmp_path: Path) -> None:
    output = tmp_path / "out.sql"

    result = export_command(dbdir, output, "--postgres")

    if finished_or_failed_cleanly(result):
        sql = output.read_bytes().decode("utf-8")
        assert sum(line.startswith('INSERT INTO "') for line in sql.split("\n")) == api_record_count(dbdir, sql=True)


def test_export_csv_writes_the_smallest_databases_with_their_files(dbdir: Path, tmp_path: Path) -> None:
    if dbdir not in smallest_databases():
        pytest.skip(f"the CSV export runs on the {CSV_DATABASES} smallest databases")

    result = export_command(dbdir, tmp_path / "out", "--csv")

    finished_or_failed_cleanly(result)
