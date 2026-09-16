# Phase 1: public façade API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the `cronos_extract` library API — `open()`, `Bank`, `Table`, `Record`, `Field`, `FieldDefinition`, `FileReference`, `EmbeddedFile`, `FileInfo`, `Kod`, `crack_kod`, `Diagnostic`, `DiagnosticKind` and the exceptions — over today's `Database`, `Datafile` and `Datamodel`, which become internal, and make the survey stream its results.

**Architecture:** New private modules under `src/cronos_extract/_api/` implement the façade; `src/cronos_extract/__init__.py` re-exports the public names. The façade drives the internal primitives (`Datafile.readrec`, `Database.read_db_definition`, `TableDefinition`, `Datamodel.Record`) instead of the printing `Database.enumerate_*` generators, and passes a `warn` hook to the few primitives that print, so the library never prints while `crodump` and `croconvert` keep their output. Files are opened through one non-blocking, regular-files-only opener in `_format/files.py`.

**Tech Stack:** Python 3.12+, uv, ruff (line length 120), ty (every rule an error), pytest (`filterwarnings = error`), `tests/cronos_builder.py` for real crafted databases.

**Spec:** `docs/superpowers/specs/2026-09-16-phase1-public-api-design.md` (decisions P1–P12, Architecture, Hostile input, Testing, Delivery). It builds on `docs/superpowers/specs/2026-09-15-modernisation-roadmap-design.md`. Read both before starting a task.

## Global Constraints

- Address the user as "Ben". Ben's global rules in `~/.claude/CLAUDE.md` override skills. The repository's rules are in `CLAUDE.md`.
- Work in the repository root, `<repo-root>` below, on branch `phase1-public-api` (it exists and holds the spec). Never push to `master`. GitHub is `hammersleyfutures/cronos-extract`; always pass `-R hammersleyfutures/cronos-extract` to `gh pr` commands. Never open anything against `alephdata/cronodump`.
- Test-first for every change: write the test, run it, confirm it fails for the stated reason, write the code, run it green. Real crafted databases from `tests/cronos_builder.py` and real files only. Never mock.
- One logical change per commit. Subject in imperative mood, ≤ 72 characters; the body says what and why. Every commit message ends with exactly `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` — use this line verbatim, never your own model name.
- Every new code file starts with two comment lines beginning `# ABOUTME: `. Neither line may contain `coding:` or `coding=` (as in "decoding: x"): Python reads that as a source encoding declaration and refuses to import the file.
- New code is fully type-annotated and ty-clean. The internal readers are unannotated, so their values are `Unknown` to ty, and ty's `unsound-*` rules report an `Unknown` value returned, yielded or assigned where an annotation expects a type. Narrow at that boundary: `int(...)` or `str(...)` where a conversion is natural, otherwise `typing.cast(...)` naming the type the reader returns. Names and comments describe what code is, never its history. Never delete a comment unless it is false.
- Run `uv run ruff format` on changed files before checking: it wraps long signatures and calls, though not long comments. Before every commit, all clean, each checked by exit code: `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check`, `uv run ty check`. The pre-commit hook runs them too.
- Bash tool: `set -e` does not stop a multi-line command. Guard commits with explicit checks, e.g. `fail() { echo "STOPPED: $*"; exit 1; }` and `uv run pytest -q > /tmp/<task>-pytest.txt 2>&1 || fail pytest`. Never pipe a checked command through `tail`.
- Never run `git checkout -- <file>` or `git restore` on a file holding uncommitted work. To try a temporary mutation, copy the file aside and copy it back.
- `tests/golden/` must not change. `git diff master -- tests/golden` must be empty after every task. If a golden file changes, stop and report.
- `crodump` and `croconvert` output must not change, except where a task says so explicitly.
- The library never prints: every façade test asserts that stdout and stderr stay empty (`capfd`).
- Diagnostic messages never embed record data or field values (P12).
- `local/mash_datasets_with_CroIndex_dat.txt` names real datasets. Never commit it, never quote its entries or any path from it in code, commits, PRs, test ids or reports.
- Follow the code when this plan and the code disagree about existing behaviour; report the divergence rather than loosening an assertion.
- Plain, factual language in commits and PRs. Avoid: critical, crucial, essential, significant, comprehensive, robust, elegant.
- Scratch files go in `/tmp` with names prefixed by the task number.

## File Structure

Created:

- `src/cronos_extract/_format/files.py` — `open_regular_file`, the one way Cro files are opened: non-blocking, regular files only.
- `src/cronos_extract/_api/__init__.py` — package marker for the private façade modules.
- `src/cronos_extract/_api/errors.py` — `CronosError` and its subclasses.
- `src/cronos_extract/_api/diagnostics.py` — `DiagnosticKind`, `Diagnostic`, `DiagnosticLog` (capped list, counts, callback), `RecordNumbers` (bit set).
- `src/cronos_extract/_api/kod.py` — `Kod` and `kod_coder`.
- `src/cronos_extract/_api/info.py` — `FileInfo` and `read_file_info`; the survey uses them too.
- `src/cronos_extract/_api/values.py` — `FieldDefinition`, `FileReference`, `EmbeddedFile`, `Field`, `Record`, `decode_record`.
- `src/cronos_extract/_api/datafiles.py` — finding Cro file pairs case-insensitively and opening them as `Datafile`s, raising the public exceptions.
- `src/cronos_extract/_api/bank.py` — `open`, `Bank`, `Table`.
- `src/cronos_extract/_api/crack.py` — the automatic KOD cracking steps and `crack_kod`.
- `src/cronos_extract/py.typed` — marks the package as typed.
- Tests: `tests/test_files.py`, `tests/test_api_diagnostics.py`, `tests/test_api_kod.py`, `tests/test_api_info.py`, `tests/test_api_values.py`, `tests/test_api_datafiles.py`, `tests/test_api_open.py`, `tests/test_api_bank.py`, `tests/test_api_crack.py`, `tests/test_realdata.py`, `tests/test_api_public.py`.

Modified:

- `tests/cronos_builder.py` — versions `01.02`, `01.03`, `01.04`, `01.05`, `01.11`; definition-key helpers.
- `src/cronos_extract/hexdump.py` — `warn_on_stderr`, the default warn hook.
- `src/cronos_extract/Datafile.py`, `Datamodel.py`, `Database.py` — `warn` hooks; `Database` opens a chosen set of files through `open_regular_file` and gains `from_datafiles`.
- `src/cronos_extract/_format/header.py` — `Generation` literal type.
- `src/cronos_extract/survey.py`, `src/cronos_extract/cli.py` — `FileInfo` in place of `SurveyedFile`; `survey_roots` streams with an `on_problem` callback.
- `src/cronos_extract/crodump.py` — uses the cracking steps from `_api/crack.py`.
- `src/cronos_extract/__init__.py` — the public names and the documented promises.
- `pyproject.toml` — the `realdata` marker, deselected by default.
- `README.md`, `CLAUDE.md` — the Python API.
- `docs/superpowers/specs/2026-09-15-modernisation-roadmap-design.md`, this plan — status and outcome (last task).

## Shared test data

Several tasks use the table of `test_data/all_field_types`, which every built database shares: table `erdgeist`, id 1, abbreviation `ER`, and 12 fields — the system number (type 0), then `Entry #1` to `Entry #11` with types 1, 2, 3, 4 (date), 5 (time), 6 (file reference), 29, 7, 8, 9, 17. The Files table is `Base000`, id 0, abbreviation `FL`. Decoding either definition warns "FieldDefinition Section 2 not marked with a 2", so every built database reports two `unexpected_structure` diagnostics at `open()`.

---

### Task 1: The test builder writes every v3 version and 01.11

Spec: P11, and P12 "Builder and tests".

**Files:**
- Modify: `tests/cronos_builder.py`
- Test: `tests/test_cronos_builder.py`

**Interfaces:**
- Consumes: nothing new.
- Produces, in `tests/cronos_builder.py`:
  - `BUILDER_VERSIONS: tuple[bytes, ...] = (b"01.02", b"01.03", b"01.04", b"01.05", b"01.11")`
  - `OWN_KOD_VERSIONS: tuple[bytes, ...] = (b"01.04", b"01.05", b"01.11")`
  - `tad_layout(version: bytes) -> tuple[bytes, struct.Struct]` — the `.tad` header bytes and entry format.
  - `write_raw_datafile(directory, name, body, tad_entries, encoding=0, version=ENCRYPTED_V3_VERSION)`
  - `write_datafile(directory, name, records, kod=None, version=ENCRYPTED_V3_VERSION)` — raises `ValueError` for a `kod` with `01.02`/`01.03`, and for a deleted (`None`) record with `01.11`.
  - `write_database(directory, bank_records, kod=None, *, extra_stru_records=(), index_records=None, version=ENCRYPTED_V3_VERSION) -> str`
  - `erdgeist_table_definition() -> bytes` — the `Base001` definition bytes of `TEST_DB`.
  - `patched_table_definition(*, tableid: int) -> bytes` — `Base001` with another table id.
  - `table_definition_without_fields(*, tableid: int) -> bytes` — a definition that decodes to a table with no fields.
  - `database_with_extra_definition_key(directory: Path, keyname: str, value: bytes, bank_records: Sequence[bytes | None] = ()) -> str`
  - `database_without_files_table(directory: Path, bank_records: Sequence[bytes | None] = ()) -> str`

- [ ] **Step 1: Write the failing tests**

Add `from cronos_extract.Datamodel import TableDefinition` to the `cronos_extract` imports of `tests/test_cronos_builder.py`. Add to its imports (keep the list sorted, as ruff's isort rule requires): `BUILDER_VERSIONS`, `DAT_PREFIX_SIZE`, `database_with_extra_definition_key`, `database_without_files_table`, `patched_table_definition`, `erdgeist_table_definition`, `table_definition_without_fields`, `write_datafile`. Then append:

```python
VERSIONS_AND_KODS = [
    (b"01.02", None),
    (b"01.03", None),
    (b"01.04", random_kod(seed=3)),
    (b"01.05", random_kod(seed=3)),
    (b"01.11", random_kod(seed=3)),
]


@pytest.mark.parametrize(
    ("version", "kod"),
    VERSIONS_AND_KODS,
    ids=lambda value: value.decode() if isinstance(value, bytes) else ("kod" if value else "default"),
)
def test_a_database_of_each_version_reads_back_through_database(
    tmp_path: Path, version: bytes, kod: list[int] | None
) -> None:
    record = person_record(b"")
    dbdir = write_database(tmp_path / "db", [record, record], kod, version=version)

    with Database(dbdir, False, KODcoding(kod if kod else INITIAL_KOD)) as db:
        assert db.bank is not None
        assert db.bank.version == version
        assert [db.bank.readrec(recno) for recno in (1, 2)] == [record, record]
        assert [table.tablename for table in db.enumerate_tables()] == ["erdgeist"]


@pytest.mark.parametrize(
    ("version", "header_size", "entry_size"),
    [(b"01.02", 8, 12), (b"01.03", 8, 16), (b"01.04", 8, 12), (b"01.05", 8, 16), (b"01.11", 16, 16)],
)
def test_the_tad_file_has_its_versions_header_and_entry_size(
    tmp_path: Path, version: bytes, header_size: int, entry_size: int
) -> None:
    write_datafile(tmp_path, "Bank", [b"\x01abc", b"\x01de"], version=version)

    assert len((tmp_path / "CroBank.tad").read_bytes()) == header_size + 2 * entry_size


def test_a_v4_tad_header_starts_with_the_marker_real_files_have(tmp_path: Path) -> None:
    write_datafile(tmp_path, "Bank", [], version=b"01.11")

    assert struct.unpack("<4L", (tmp_path / "CroBank.tad").read_bytes()) == (0xFFFFFFFE, 0, 0, 0)


def test_v4_record_flags_are_in_the_top_byte_of_the_offset(tmp_path: Path) -> None:
    write_datafile(tmp_path, "Bank", [b"\x01abc"], version=b"01.11")

    offset, length, _ = struct.unpack("<QLL", (tmp_path / "CroBank.tad").read_bytes()[16:])
    assert (offset >> 56, offset & ((1 << 56) - 1), length) == (0x04, DAT_PREFIX_SIZE, 4)


def test_v3_record_flags_are_in_the_top_byte_of_the_length(tmp_path: Path) -> None:
    write_datafile(tmp_path, "Bank", [b"\x01abc"], version=b"01.03")

    offset, length, _ = struct.unpack("<QLL", (tmp_path / "CroBank.tad").read_bytes()[8:])
    assert (offset, length >> 24, length & 0xFFFFFF) == (DAT_PREFIX_SIZE, 0x80, 4)


@pytest.mark.parametrize("version", [b"01.02", b"01.03"])
def test_the_builder_refuses_a_kod_for_a_version_read_with_the_default_kod(tmp_path: Path, version: bytes) -> None:
    with pytest.raises(ValueError, match="default KOD"):
        write_datafile(tmp_path, "Bank", [b"\x01abc"], kod=random_kod(seed=3), version=version)


def test_the_builder_refuses_a_deleted_v4_record(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="deleted v4 record"):
        write_datafile(tmp_path, "Bank", [None], version=b"01.11")


def test_the_builder_refuses_a_version_it_cannot_write(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cannot write version"):
        write_datafile(tmp_path, "Bank", [], version=b"01.19")


def test_the_builder_versions_are_the_ones_the_spec_names() -> None:
    assert BUILDER_VERSIONS == (b"01.02", b"01.03", b"01.04", b"01.05", b"01.11")


def test_a_patched_table_definition_changes_the_table_id(tmp_path: Path) -> None:
    dbdir = database_with_extra_definition_key(tmp_path / "db", "Base002", patched_table_definition(tableid=300))

    with Database(dbdir, False, KODcoding(INITIAL_KOD)) as db:
        assert [(table.tableid, table.tablename) for table in db.enumerate_tables()] == [
            (1, "erdgeist"),
            (300, "erdgeist"),
        ]


def test_a_patched_table_definition_changes_only_the_table_id_bytes() -> None:
    patched = patched_table_definition(tableid=0x01020304)
    original = erdgeist_table_definition()

    assert len(patched) == len(original)
    assert [index for index in range(len(original)) if patched[index] != original[index]] == [14, 15, 16, 17]


def test_a_table_definition_without_fields_decodes_to_a_table_with_no_fields() -> None:
    messages: list[str] = []

    table = TableDefinition(table_definition_without_fields(tableid=2), warn=messages.append)

    assert (table.tableid, table.tablename, table.abbrev, table.fields, messages) == (2, "erdgeist", "ER", [], [])


def test_an_extra_definition_key_holds_its_value_inline(tmp_path: Path) -> None:
    dbdir = database_with_extra_definition_key(tmp_path / "db", "Extra", b"\x01\x02")

    with Database(dbdir, False, KODcoding(INITIAL_KOD)) as db:
        assert db.read_db_definition()["Extra"] == b"\x01\x02"


def test_a_database_without_a_files_table_has_no_base000_key(tmp_path: Path) -> None:
    dbdir = database_without_files_table(tmp_path / "db")

    with Database(dbdir, False, KODcoding(INITIAL_KOD)) as db:
        keys = db.read_db_definition().keys()
        assert "Base000" not in keys
        assert "Base001" in keys
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_cronos_builder.py`
Expected: collection fails with `ImportError: cannot import name 'BUILDER_VERSIONS'`.

- [ ] **Step 3: Implement the builder changes**

In `tests/cronos_builder.py`, replace the constants block from `DAT_HEADER = struct.Struct("<8sH5sHH")` to `COMPLEX_FIELD_MARKER = b"\x1b"` with:

```python
DAT_HEADER = struct.Struct("<8sH5sHH")
DAT_HEADER_PADDING = 0xE9
TAD_V3_HEADER = struct.Struct("<2L")
TAD_V4_HEADER = struct.Struct("<4L")
# The first dword of every .tad header in Ben's real v4 databases.
TAD_V4_MARKER = 0xFFFFFFFE
TAD_V3_ENTRY = struct.Struct("<LLL")
TAD_64BIT_ENTRY = struct.Struct("<QLL")
BLOCKSIZE = 0x40
# Size of the .dat file header and the padding that follows it; the first record starts here.
DAT_PREFIX_SIZE = DAT_HEADER.size + DAT_HEADER_PADDING
# Version 01.04 is a 32-bit v3 file whose records are decoded with the database's own KOD table.
ENCRYPTED_V3_VERSION = b"01.04"
BUILDER_VERSIONS = (b"01.02", b"01.03", b"01.04", b"01.05", b"01.11")
VERSIONS_64BIT = (b"01.03", b"01.05", b"01.11")
V4_VERSIONS = (b"01.11",)
# Datafile decodes every other version with the default KOD table, whatever table it is given.
OWN_KOD_VERSIONS = (b"01.04", b"01.05", b"01.11")
# A non-zero flag byte in the top of a v3 .tad length marks a record stored inline, not in extension blocks.
INLINE_RECORD_FLAGS = 0x80
# A v4 .tad keeps the flag byte in the top of the offset; 0x04 marks a record stored inline.
V4_INLINE_RECORD_FLAGS = 0x04
DELETED_RECORD_LENGTH = 0xFFFFFFFF
FIELD_SEPARATOR = b"\x1e"
COMPLEX_FIELD_MARKER = b"\x1b"
# The high bit of a database definition key's length says its value follows inline.
INLINE_DEFINITION_VALUE = 0x80000000
# Offsets in TEST_DB's Base001 definition: the table id, and the number of field definitions after the names.
TABLE_ID_OFFSET = 14
FIELD_COUNT_OFFSET = 34
```

Add `from typing import cast` to the imports of `tests/cronos_builder.py`. Replace `write_raw_datafile` and `write_datafile` with:

```python
def tad_layout(version: bytes) -> tuple[bytes, struct.Struct]:
    """Return the .tad header bytes and the .tad entry format that `version` uses."""
    if version not in BUILDER_VERSIONS:
        raise ValueError(f"the builder cannot write version {version!r}; it writes {BUILDER_VERSIONS!r}")
    if version in V4_VERSIONS:
        return TAD_V4_HEADER.pack(TAD_V4_MARKER, 0, 0, 0), TAD_64BIT_ENTRY
    return TAD_V3_HEADER.pack(0, 0), TAD_64BIT_ENTRY if version in VERSIONS_64BIT else TAD_V3_ENTRY


def write_raw_datafile(
    directory: Path,
    name: str,
    body: bytes,
    tad_entries: Sequence[tuple[int, int]],
    encoding: int = 0,
    version: bytes = ENCRYPTED_V3_VERSION,
) -> None:
    """Write Cro<name>.dat holding `body` after the file header, and Cro<name>.tad with one entry per record.

    Each entry is (offset field, length field), packed as `version` stores them: v3 keeps a record's flags in the
    top byte of the length field, v4 in the top byte of the offset field. The body starts at DAT_PREFIX_SIZE. This
    lets tests lay out inline, extended or corrupt records byte by byte.
    """
    tad_header, tad_entry = tad_layout(version)
    dat = DAT_HEADER.pack(b"CroFile\x00", 0, version, encoding, BLOCKSIZE) + bytes(DAT_HEADER_PADDING)
    tad = tad_header + b"".join(tad_entry.pack(offset, length, 0) for offset, length in tad_entries)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"Cro{name}.dat").write_bytes(dat + body)
    (directory / f"Cro{name}.tad").write_bytes(tad)
```

(`write_header_only_datafile` stays as it is.)

```python
def write_datafile(
    directory: Path,
    name: str,
    records: Sequence[bytes | None],
    kod: Sequence[int] | None = None,
    version: bytes = ENCRYPTED_V3_VERSION,
) -> None:
    """Write Cro<name>.dat and Cro<name>.tad of `version` holding `records` inline, where None marks a deleted record.

    With `kod`, each record is KOD-encoded using its record number as the shift and the encoding bit is set; only
    versions encrypted with their own KOD table take one. Deleted records cannot be written for v4, because how v4
    marks them is unsettled.
    """
    tad_layout(version)
    if kod is not None and version not in OWN_KOD_VERSIONS:
        raise ValueError(
            f"version {version!r} is always read with the default KOD, so it cannot be written with another"
        )
    coder = KODcoding(list(kod)) if kod is not None else None
    body = bytearray()
    tad_entries = []
    for recno, plain in enumerate(records, start=1):
        if plain is None:
            if version in V4_VERSIONS:
                raise ValueError("the builder does not write a deleted v4 record: how v4 marks one is unsettled")
            tad_entries.append((0, DELETED_RECORD_LENGTH))
            continue
        stored = coder.encode(recno, plain) if coder else plain
        offset = DAT_PREFIX_SIZE + len(body)
        if version in V4_VERSIONS:
            tad_entries.append((offset | V4_INLINE_RECORD_FLAGS << 56, len(stored)))
        else:
            tad_entries.append((offset, len(stored) | INLINE_RECORD_FLAGS << 24))
        body += stored
    write_raw_datafile(directory, name, bytes(body), tad_entries, encoding=1 if coder else 0, version=version)
```

Replace `write_database` with:

```python
def write_database(
    directory: Path,
    bank_records: Sequence[bytes | None],
    kod: Sequence[int] | None = None,
    *,
    extra_stru_records: Sequence[bytes] = (),
    index_records: Sequence[bytes | None] | None = None,
    version: bytes = ENCRYPTED_V3_VERSION,
) -> str:
    """Write a database of `version` with TEST_DB's table definitions and `bank_records`, returning its directory path.

    `extra_stru_records` are appended to the CroStru records; `index_records`, when given, are written to CroIndex.
    """
    write_datafile(directory, "Stru", [*stru_records_from_test_db(), *extra_stru_records], kod, version)
    write_datafile(directory, "Bank", bank_records, kod, version)
    if index_records is not None:
        write_datafile(directory, "Index", index_records, kod, version)
    return str(directory)
```

Add after `key_referencing_a_deleted_record`:

```python
def erdgeist_table_definition() -> bytes:
    """Return the definition bytes of TEST_DB's table "erdgeist", the value of its Base001 key."""
    with Database(str(TEST_DB), False, KODcoding(INITIAL_KOD)) as db:
        return cast(bytes, db.read_db_definition()["Base001"])


def patched_table_definition(*, tableid: int) -> bytes:
    """Return TEST_DB's Base001 definition with its table id replaced."""
    definition = bytearray(erdgeist_table_definition())
    assert struct.unpack_from("<L", definition, TABLE_ID_OFFSET) == (TEST_TABLE_ID,)
    struct.pack_into("<L", definition, TABLE_ID_OFFSET, tableid)
    return bytes(definition)


def table_definition_without_fields(*, tableid: int) -> bytes:
    """
    Return a table definition with TEST_DB's Base001 names and `tableid` but no field definitions.

    After the header come an empty first field section, no extra byte strings, a second section marked with a 2
    holding no fields, and the terminator, so it decodes without warnings.
    """
    header = bytearray(patched_table_definition(tableid=tableid)[:FIELD_COUNT_OFFSET])
    empty_sections = struct.pack("<LLL", 0, 0, 0) + b"\x02" + struct.pack("<LLL", 0, 0, 0xFFFFFFFF)
    return bytes(header) + empty_sections


def database_with_extra_definition_key(
    directory: Path, keyname: str, value: bytes, bank_records: Sequence[bytes | None] = ()
) -> str:
    """Write a database whose database definition has an extra key `keyname` holding `value` inline.

    The key is appended after TEST_DB's own keys; a key already there, such as "BankName", becomes a duplicate.
    """
    stru = stru_records_from_test_db()
    dbinfo = stru[0]
    assert dbinfo is not None
    name = keyname.encode("cp1251")
    stru[0] = dbinfo + bytes([len(name)]) + name + struct.pack("<L", len(value) | INLINE_DEFINITION_VALUE) + value
    write_datafile(directory, "Stru", stru)
    write_datafile(directory, "Bank", bank_records)
    return str(directory)


def database_without_files_table(directory: Path, bank_records: Sequence[bytes | None] = ()) -> str:
    """Write a database whose database definition names its Files table Xase000, so it has no Base000 key."""
    stru = stru_records_from_test_db()
    dbinfo = stru[0]
    assert dbinfo is not None
    assert dbinfo.count(b"\x07Base000") == 1
    stru[0] = dbinfo.replace(b"\x07Base000", b"\x07Xase000")
    write_datafile(directory, "Stru", stru)
    write_datafile(directory, "Bank", bank_records)
    return str(directory)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_cronos_builder.py`
Expected: all pass, except that `test_a_table_definition_without_fields_decodes_to_a_table_with_no_fields` needs Task 2's `warn` parameter: until then it fails with `TypeError: ... unexpected keyword argument 'warn'`. Mark it `@pytest.mark.xfail(reason="TableDefinition takes warn from Task 2", strict=True)` in this task, and Task 2 removes the mark. If the assert in `patched_table_definition` fails, the offset is wrong: stop and report the actual bytes rather than changing the test.

- [ ] **Step 5: Run the whole suite and linters, then commit**

```bash
fail() { echo "STOPPED: $*"; exit 1; }
uv run pytest -q > /tmp/t1-pytest.txt 2>&1 || fail pytest
uv run ruff check > /tmp/t1-ruff.txt 2>&1 || fail ruff
uv run ruff format --check > /tmp/t1-format.txt 2>&1 || fail format
uv run ty check > /tmp/t1-ty.txt 2>&1 || fail ty
test -z "$(git diff master -- tests/golden)" || fail golden
git add tests/cronos_builder.py tests/test_cronos_builder.py
git commit -F - <<'EOF' || fail commit
Let the test builder write every v3 version and 01.11

Crafted databases can now be 01.02, 01.03 (64-bit), 01.04, 01.05 or
v4 01.11, so the façade tests can cover the 64-bit and v4 reader
paths. Adds helpers for extra definition keys, a patched table
definition and a database without a Files table.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 2: Open Cro files without blocking, and let readers report warnings through a hook

Spec: P1, P3 "Why", Architecture "Changes inside the internals", Hostile input (FIFO, socket, dangling symlink).

**Files:**
- Create: `src/cronos_extract/_format/files.py`, `tests/test_files.py`
- Modify: `src/cronos_extract/hexdump.py`, `src/cronos_extract/Datafile.py`, `src/cronos_extract/Datamodel.py`, `src/cronos_extract/Database.py`
- Test: `tests/test_database.py`, `tests/test_datafile.py`, `tests/test_datamodel.py`

**Interfaces:**
- Consumes: Task 1's `database_with_extra_definition_key`, `erdgeist_table_definition`.
- Produces:
  - `cronos_extract._format.files.NotARegularFile(OSError)`
  - `cronos_extract._format.files.open_regular_file(path: str | os.PathLike[str]) -> BinaryIO`
  - `cronos_extract.hexdump.warn_on_stderr(message: str) -> None`
  - `Datafile(name, dat, tad, compact, kod, warn=warn_on_stderr)`; `TableDefinition(data, image="", warn=warn_on_stderr)`
  - `Database(dbdir, compact, kod, files=ALL_FILES, warn=warn_on_stderr)` with `ALL_FILES = ("Stru", "Index", "Bank", "Sys")`; `Database.from_datafiles(dbdir, compact, kod, stru, bank, warn) -> Database`
  - Every warning that these print today goes through `warn` with the same text, prefix included (`"WARN: duplicate key: …"`, `"Warning: FieldDefinition Section 2 not marked with a 2"`, …).

This task makes two commits: the opener first, then the hooks.

- [ ] **Step 1: Write the failing opener tests**

Create `tests/test_files.py`:

```python
# ABOUTME: Tests for cronos_extract._format.files, which opens Cro files without blocking and only if they are regular.
# ABOUTME: Uses real FIFOs, sockets, directories and symlinks made in a temporary directory.
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from cronos_extract._format.files import NotARegularFile, open_regular_file


def test_a_regular_file_opens_for_binary_reading(tmp_path: Path) -> None:
    (tmp_path / "CroStru.dat").write_bytes(b"CroFile\x00")

    with open_regular_file(tmp_path / "CroStru.dat") as file:
        assert file.read() == b"CroFile\x00"


def test_a_fifo_is_refused_without_waiting_for_a_writer(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "CroStru.dat")
    code = (
        "import sys\n"
        "from cronos_extract._format.files import NotARegularFile, open_regular_file\n"
        "try:\n"
        "    open_regular_file(sys.argv[1])\n"
        "except NotARegularFile as e:\n"
        "    print(e)\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path / "CroStru.dat")],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.stdout == "CroStru.dat is not a regular file\n"
    assert result.stderr == ""


def test_a_directory_is_refused(tmp_path: Path) -> None:
    (tmp_path / "CroStru.dat").mkdir()

    with pytest.raises(NotARegularFile, match=r"^CroStru\.dat is not a regular file$"):
        open_regular_file(tmp_path / "CroStru.dat")


def test_a_socket_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "s"
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(str(path))

        with pytest.raises(OSError):
            open_regular_file(path)


def test_a_dangling_symlink_raises_file_not_found(tmp_path: Path) -> None:
    (tmp_path / "CroStru.dat").symlink_to(tmp_path / "missing")

    with pytest.raises(FileNotFoundError):
        open_regular_file(tmp_path / "CroStru.dat")


def test_a_symlink_to_a_regular_file_is_followed(tmp_path: Path) -> None:
    (tmp_path / "real").write_bytes(b"data")
    (tmp_path / "CroStru.dat").symlink_to(tmp_path / "real")

    with open_regular_file(tmp_path / "CroStru.dat") as file:
        assert file.read() == b"data"


def test_not_a_regular_file_is_an_os_error() -> None:
    assert issubclass(NotARegularFile, OSError)
```

If `tmp_path` is too long for a Unix socket path (over 107 bytes), `bind` raises `OSError: AF_UNIX path too long`; then bind to a name in a directory from `tempfile.mkdtemp(dir="/tmp")` instead and report it.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/test_files.py`
Expected: collection fails with `ModuleNotFoundError: No module named 'cronos_extract._format.files'`.

- [ ] **Step 3: Implement the opener**

Create `src/cronos_extract/_format/files.py`:

```python
# ABOUTME: Opens Cro*.dat and Cro*.tad files for reading without blocking on FIFOs, and only if they are regular files.
# ABOUTME: A FIFO, socket, device or directory raises NotARegularFile, an OSError, instead of hanging or being read.
import os
import stat
from pathlib import Path
from typing import BinaryIO

# Windows has neither O_NONBLOCK nor FIFOs in the file system; elsewhere it stops an open from waiting for a writer.
O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
# Windows opens files in text mode unless O_BINARY is given; elsewhere it does not exist.
O_BINARY = getattr(os, "O_BINARY", 0)


class NotARegularFile(OSError):
    """Raised for a path that is a FIFO, socket, device or directory, which no Cronos file is."""


def open_regular_file(path: str | os.PathLike[str]) -> BinaryIO:
    """
    Open `path` for binary reading, raising NotARegularFile unless it is a regular file.

    The file is opened without blocking, so a FIFO does not wait for a writer, and checked with fstat on the open
    descriptor, so it cannot be swapped for something else between the check and the open. Symbolic links are
    followed. Other failures to open raise the OSError that os.open raises.
    """
    descriptor = os.open(path, os.O_RDONLY | O_NONBLOCK | O_BINARY)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise NotARegularFile(f"{Path(path).name} is not a regular file")
        if O_NONBLOCK:
            os.set_blocking(descriptor, True)
        return os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise
```

- [ ] **Step 4: Run the opener tests to verify they pass**

Run: `uv run pytest -q tests/test_files.py`
Expected: all pass.

- [ ] **Step 5: Write the failing test that `Database` uses the opener**

Append to `tests/test_database.py` (add `import os` and `from cli import run_command` to the imports, sorted):

```python
def test_croconvert_passes_over_a_fifo_named_like_the_index_instead_of_blocking(tmp_path: Path) -> None:
    dbdir = Path(write_database(tmp_path / "db", []))
    os.mkfifo(dbdir / "CroIndex.dat")
    (dbdir / "CroIndex.tad").write_bytes(bytes(8))

    result = run_command("croconvert", ["--csv", "-o", str(tmp_path / "out"), str(dbdir)], timeout=60)

    assert result.returncode == 0, result.stderr
```

- [ ] **Step 6: Run it to verify it fails**

Run: `uv run pytest -q tests/test_database.py::test_croconvert_passes_over_a_fifo_named_like_the_index_instead_of_blocking`
Expected: FAIL with `subprocess.TimeoutExpired` after 60 seconds, because `Database.opendatafile` opens the FIFO with the built-in `open`.

- [ ] **Step 7: Make `Database.opendatafile` use the opener**

In `src/cronos_extract/Database.py`, add `from ._format.files import open_regular_file` to the imports, and in `opendatafile` replace `open(datname, "rb")` with `open_regular_file(datname)` and `open(tadname, "rb")` with `open_regular_file(tadname)`. `getfile` already turns an `OSError`, which `NotARegularFile` is, into `None`. Update the `getfile` docstring's second paragraph to: "When no such files exist, only one of them does, or one cannot be opened or is not a regular file, then None is returned."

- [ ] **Step 8: Run the test, the suite and the linters, then commit**

```bash
fail() { echo "STOPPED: $*"; exit 1; }
uv run pytest -q > /tmp/t2a-pytest.txt 2>&1 || fail pytest
uv run ruff check > /tmp/t2a-ruff.txt 2>&1 || fail ruff
uv run ruff format --check > /tmp/t2a-format.txt 2>&1 || fail format
uv run ty check > /tmp/t2a-ty.txt 2>&1 || fail ty
test -z "$(git diff master -- tests/golden)" || fail golden
git add src/cronos_extract/_format/files.py src/cronos_extract/Database.py tests/test_files.py tests/test_database.py
git commit -F - <<'EOF' || fail commit
Open Cro files without blocking on FIFOs

open_regular_file opens with O_NONBLOCK and checks fstat on the open
descriptor, so a FIFO, socket or directory named like a Cro file is
refused instead of hanging the reader. Database opens its files with
it, so croconvert passes over a FIFO named CroIndex.dat.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

- [ ] **Step 9: Write the failing hook tests**

Append to `tests/test_datafile.py` (add `write_datafile` to the existing `cronos_builder` import, sorted):

```python
def test_leftover_tad_bytes_are_reported_through_the_warn_hook(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    write_datafile(tmp_path, "Bank", [b"\x01abc"])
    with (tmp_path / "CroBank.tad").open("ab") as tad:
        tad.write(b"\x00")
    messages: list[str] = []

    with (tmp_path / "CroBank.dat").open("rb") as dat, (tmp_path / "CroBank.tad").open("rb") as tad:
        Datafile("Bank", dat, tad, False, None, warn=messages.append)

    assert messages == ["WARN: leftover data in .tad"]
    assert capfd.readouterr().err == ""


def test_leftover_tad_bytes_are_printed_without_a_warn_hook(tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    write_datafile(tmp_path, "Bank", [b"\x01abc"])
    with (tmp_path / "CroBank.tad").open("ab") as tad:
        tad.write(b"\x00")

    with (tmp_path / "CroBank.dat").open("rb") as dat, (tmp_path / "CroBank.tad").open("rb") as tad:
        Datafile("Bank", dat, tad, False, None)

    assert capfd.readouterr().err == "WARN: leftover data in .tad\n"
```

In `tests/test_cronos_builder.py`, remove the `xfail` mark from `test_a_table_definition_without_fields_decodes_to_a_table_with_no_fields`; it must now pass.

Append to `tests/test_datamodel.py` (add `from cronos_builder import erdgeist_table_definition` and `from cronos_extract.Datamodel import TableDefinition`, sorted into the existing imports):

```python
def test_table_definition_warnings_go_through_the_warn_hook(capfd: pytest.CaptureFixture[str]) -> None:
    messages: list[str] = []

    TableDefinition(erdgeist_table_definition(), warn=messages.append)

    assert messages == ["Warning: FieldDefinition Section 2 not marked with a 2"]
    assert capfd.readouterr().err == ""
```

Append to `tests/test_database.py` (add `database_with_extra_definition_key` to the `cronos_builder` import, sorted):

```python
def test_a_duplicate_definition_key_is_reported_through_the_warn_hook(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    dbdir = database_with_extra_definition_key(tmp_path / "db", "BankName", b"again")
    messages: list[str] = []

    with Database(dbdir, False, KODcoding(INITIAL_KOD), warn=messages.append) as db:
        db.read_db_definition()

    assert messages == ["WARN: duplicate key: BankName"]
    assert capfd.readouterr().err == ""


def test_database_opens_only_the_files_it_is_asked_for(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [], index_records=[])

    with Database(dbdir, False, KODcoding(INITIAL_KOD), files=("Stru", "Bank")) as db:
        assert (db.stru is not None, db.bank is not None, db.index, db.sys) == (True, True, None, None)


def test_a_corrupt_index_header_does_not_stop_a_database_that_does_not_open_the_index(tmp_path: Path) -> None:
    dbdir = Path(write_database(tmp_path / "db", []))
    (dbdir / "CroIndex.dat").write_bytes(b"garbage")
    (dbdir / "CroIndex.tad").write_bytes(bytes(8))

    with Database(str(dbdir), False, KODcoding(INITIAL_KOD), files=("Stru", "Bank")) as db:
        assert "Base001" in db.read_db_definition()


def test_a_database_made_from_open_datafiles_reads_its_definition(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [])
    kod = KODcoding(INITIAL_KOD)
    messages: list[str] = []
    with Database(dbdir, False, kod, files=("Stru", "Bank")) as opened:
        assert opened.stru is not None
        assert opened.bank is not None
        db = Database.from_datafiles(dbdir, False, kod, opened.stru, opened.bank, messages.append)

        assert (db.stru, db.bank, db.index, db.sys) == (opened.stru, opened.bank, None, None)
        assert "Base001" in db.read_db_definition()
```

- [ ] **Step 10: Run them to verify they fail**

Run: `uv run pytest -q tests/test_datafile.py tests/test_datamodel.py tests/test_database.py`
Expected: the new tests FAIL with `TypeError: ... got an unexpected keyword argument 'warn'` (and `'files'`, and `AttributeError: ... 'from_datafiles'`).

- [ ] **Step 11: Implement the hooks**

In `src/cronos_extract/hexdump.py`, add `import sys` to the imports and, after `unhex`:

```python
def warn_on_stderr(message):
    """
    Print a reader's warning to stderr, where the commands report problems.
    This is the default `warn` hook of Datafile, TableDefinition and Database.
    """
    print(message, file=sys.stderr)
```

In `src/cronos_extract/Datafile.py`: import `warn_on_stderr` alongside `tohex, toout` from `.hexdump`. Change the constructor to `def __init__(self, name, dat, tad, compact, kod, warn=warn_on_stderr):`, set `self.warn = warn` as its first line, and in `readtad` replace `print("WARN: leftover data in .tad", file=sys.stderr)` with `self.warn("WARN: leftover data in .tad")`. Remove `import sys` if nothing else in the file uses it (ruff reports it).

In `src/cronos_extract/Datamodel.py`: import `warn_on_stderr` alongside `ashex, tohex`. Change `TableDefinition.__init__` to:

```python
    def __init__(self, data, image="", warn=warn_on_stderr):
        """
        Decode a table definition from `data` and its image from `image`.
        `warn` receives a message for each part of the definition that is not laid out as expected.
        """
        self.warn = warn
        self.decode(data, image)
```

and in `decode` replace the three `print(..., file=sys.stderr)` calls with `self.warn(...)`, keeping each message text exactly:
`self.warn("Warning: FieldDefinition Section 2 not marked with a 2")`,
`self.warn(f"Warning: Error '{e}' parsing FieldDefinitions")`,
`self.warn("Warning: FieldDefinition section not terminated")`,
`self.warn(f"Warning: Error '{e}' parsing Tabledefinition")`.
Remove `import sys` if unused.

In `src/cronos_extract/Database.py`: import `warn_on_stderr` alongside the other `.hexdump` names. Add, above the class:

```python
# The files a Database opens unless told otherwise.
ALL_FILES = ("Stru", "Index", "Bank", "Sys")
```

Replace `__init__`'s signature, docstring and file opening with:

```text
    def __init__(self, dbdir, compact, kod, files=ALL_FILES, warn=warn_on_stderr):
        """
        `dbdir` is the directory containing the Cro*.dat and Cro*.tad files.
        `compact` if set, the .tad file is not cached in memory, making dumps 15 % slower
        `kod` is a KOD coder object, or None to read the records without KOD decoding.
        `files` names the components to open, from ALL_FILES; the others are None.
        `warn` receives a message for each part of the database definition that is not laid out as expected.
        """
        self.dbdir = dbdir
        self.compact = compact
        self.kod = kod
        self.files = files
        self.warn = warn

        # Stru+Index+Bank for the components for most databases
        self.stru = self.getfile("Stru")
        self.index = self.getfile("Index")
        self.bank = self.getfile("Bank")

        # the Sys file resides in the "Program Files\Cronos" directory, and
        # contains an index of all known databases.
        self.sys = self.getfile("Sys")

    @classmethod
    def from_datafiles(cls, dbdir, compact, kod, stru, bank, warn):
        """
        Make a Database of the CroStru and CroBank Datafiles `stru` and `bank`, which the caller has opened.
        Closing the Database closes them.
        """
        db = cls(dbdir, compact, kod, files=(), warn=warn)
        db.stru = stru
        db.bank = bank
        return db
```

In `getfile`, add `if name not in self.files: return None` (as two lines) before the `try:`, and add to its docstring: "A component not named in `files` is not opened, and None is returned." Keep the four assignments in `__init__` as plain `self.getfile(...)` calls: an explicit `... else None` there would make ty type every `self.stru` and `self.bank` as possibly `None` and report each attribute access in `Database.py` and `dumpdbfields.py`.
In `opendatafile`, pass the hook: `datafile = Datafile(name, dat, tad, self.compact, self.kod, self.warn)`.
In `decode_db_definition`, replace the two prints with `self.warn(f"WARN: duplicate key: {keyname}")` and `self.warn("WARN: expected refdata to start with 0x04")`. In `read_db_definition`, replace the print with `self.warn("WARN: expected dbinfo to start with 0x03")`. Leave every other `print` in `Database.py` alone.

- [ ] **Step 12: Run the tests, the suite and the linters, then commit**

Run: `uv run pytest -q tests/test_datafile.py tests/test_datamodel.py tests/test_database.py` — expected: all pass. Then:

```bash
fail() { echo "STOPPED: $*"; exit 1; }
uv run pytest -q > /tmp/t2b-pytest.txt 2>&1 || fail pytest
uv run ruff check > /tmp/t2b-ruff.txt 2>&1 || fail ruff
uv run ruff format --check > /tmp/t2b-format.txt 2>&1 || fail format
uv run ty check > /tmp/t2b-ty.txt 2>&1 || fail ty
test -z "$(git diff master -- tests/golden)" || fail golden
git add src/cronos_extract/hexdump.py src/cronos_extract/Datafile.py src/cronos_extract/Datamodel.py src/cronos_extract/Database.py tests/test_datafile.py tests/test_datamodel.py tests/test_database.py
git commit -F - <<'EOF' || fail commit
Report reader warnings through a hook and open chosen Cro files

Datafile, TableDefinition and Database take a warn callable, whose
default prints to stderr as before, so the library can turn those
warnings into diagnostics. Database can open a chosen subset of its
files and be made from Datafiles opened elsewhere.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---
### Task 3: Exceptions and diagnostics

Spec: P3, P8 (`unsupported_table`), P9, P12 "Diagnostics".

**Files:**
- Create: `src/cronos_extract/_api/__init__.py`, `src/cronos_extract/_api/errors.py`, `src/cronos_extract/_api/diagnostics.py`
- Test: `tests/test_api_diagnostics.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `cronos_extract._api.errors`: `CronosError(Exception)`, `NotACronosFile(CronosError)`, `UnsupportedVersion(CronosError)`, `DatabaseDefinitionError(CronosError)`.
  - `cronos_extract._api.diagnostics`:
    - `DIAGNOSTICS_KEPT = 1000`
    - `DiagnosticKind(StrEnum)` with members `CORRUPT_RECORD`, `UNDECODABLE_FIELD`, `INVALID_VALUE`, `UNDECODABLE_TABLE`, `UNSUPPORTED_TABLE`, `UNEXPECTED_STRUCTURE`, `UNRESOLVED_FILE_REFERENCE`, `UNREADABLE_FILE`, `UNUSED_KOD`, whose values are the lower-case names.
    - `Diagnostic` (frozen dataclass): `kind: DiagnosticKind`, `message: str`, `file: str | None = None`, `table: str | None = None`, `record: int | None = None`, `field: str | None = None`.
    - `DiagnosticLog(on_diagnostic: Callable[[Diagnostic], object] | None)` with `record(diagnostic: Diagnostic) -> None`, `kept: Sequence[Diagnostic]`, `counts: Mapping[DiagnosticKind, int]`.
    - `RecordNumbers(size: int)` with `add(number: int) -> bool`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_diagnostics.py`:

```python
# ABOUTME: Tests for the diagnostics of the cronos_extract API: their kinds, the capped log and the record number set.
# ABOUTME: Pins the kind names Phase 2's JSON output relies on and the memory bounds on hostile databases.
import dataclasses
from collections.abc import Sequence

import pytest

from cronos_extract._api.diagnostics import (
    DIAGNOSTICS_KEPT,
    Diagnostic,
    DiagnosticKind,
    DiagnosticLog,
    RecordNumbers,
)
from cronos_extract._api.errors import CronosError, DatabaseDefinitionError, NotACronosFile, UnsupportedVersion


def corrupt(number: int) -> Diagnostic:
    return Diagnostic(DiagnosticKind.CORRUPT_RECORD, "corrupt", file="CroBank.dat", record=number)


def test_the_diagnostic_kinds_have_stable_snake_case_values() -> None:
    assert [kind.value for kind in DiagnosticKind] == [
        "corrupt_record",
        "undecodable_field",
        "invalid_value",
        "undecodable_table",
        "unsupported_table",
        "unexpected_structure",
        "unresolved_file_reference",
        "unreadable_file",
        "unused_kod",
    ]
    assert DiagnosticKind.CORRUPT_RECORD == "corrupt_record"


def test_a_diagnostic_is_frozen_and_its_location_fields_default_to_none() -> None:
    diagnostic = Diagnostic(DiagnosticKind.UNUSED_KOD, "unused")

    assert (diagnostic.file, diagnostic.table, diagnostic.record, diagnostic.field) == (None, None, None, None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        diagnostic.message = "changed"  # ty: ignore[invalid-assignment]


def test_the_log_keeps_the_first_diagnostics_and_counts_every_one() -> None:
    log = DiagnosticLog(None)

    for number in range(1, DIAGNOSTICS_KEPT + 2):
        log.record(corrupt(number))

    assert DIAGNOSTICS_KEPT == 1000
    assert len(log.kept) == 1000
    assert (log.kept[0].record, log.kept[-1].record) == (1, 1000)
    assert log.counts[DiagnosticKind.CORRUPT_RECORD] == 1001


def test_the_log_passes_each_diagnostic_to_the_callback_after_keeping_and_counting_it() -> None:
    seen: list[tuple[Diagnostic, int, int]] = []

    def on_diagnostic(diagnostic: Diagnostic) -> None:
        seen.append((diagnostic, len(log.kept), log.counts[diagnostic.kind]))

    log = DiagnosticLog(on_diagnostic)
    log.record(corrupt(1))
    log.record(corrupt(2))

    assert seen == [(corrupt(1), 1, 1), (corrupt(2), 2, 2)]


def test_an_exception_from_the_callback_reaches_the_caller_after_the_diagnostic_is_counted() -> None:
    class StopReading(Exception):
        pass

    def on_diagnostic(diagnostic: Diagnostic) -> None:
        raise StopReading

    log = DiagnosticLog(on_diagnostic)
    with pytest.raises(StopReading):
        log.record(corrupt(1))

    assert log.counts[DiagnosticKind.CORRUPT_RECORD] == 1


def test_the_kept_diagnostics_are_a_read_only_sequence_that_grows() -> None:
    log = DiagnosticLog(None)
    kept = log.kept

    log.record(corrupt(1))
    log.record(corrupt(2))

    assert isinstance(kept, Sequence)
    assert not hasattr(kept, "append")
    assert list(kept) == [corrupt(1), corrupt(2)]
    assert kept[0:1] == (corrupt(1),)


def test_the_counts_hold_only_kinds_that_occurred() -> None:
    log = DiagnosticLog(None)
    counts = log.counts

    log.record(corrupt(1))
    log.record(Diagnostic(DiagnosticKind.UNUSED_KOD, "unused"))

    assert dict(counts) == {DiagnosticKind.CORRUPT_RECORD: 1, DiagnosticKind.UNUSED_KOD: 1}
    assert not hasattr(counts, "__setitem__")


def test_record_numbers_says_whether_a_number_is_new() -> None:
    numbers = RecordNumbers(16)

    assert [numbers.add(1), numbers.add(16), numbers.add(1), numbers.add(9)] == [True, True, False, True]


def test_record_numbers_needs_one_bit_per_record() -> None:
    numbers = RecordNumbers(8_000_000)

    assert numbers.add(8_000_000)
    assert len(numbers._bits) <= 1_000_001


def test_every_exception_is_a_cronos_error() -> None:
    for error in (NotACronosFile, UnsupportedVersion, DatabaseDefinitionError):
        assert issubclass(error, CronosError)
    assert issubclass(CronosError, Exception)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/test_api_diagnostics.py`
Expected: collection fails with `ModuleNotFoundError: No module named 'cronos_extract._api'`.

- [ ] **Step 3: Implement**

Create `src/cronos_extract/_api/__init__.py`:

```python
# ABOUTME: Private package holding the implementation of the cronos_extract library API.
# ABOUTME: Import the public names from cronos_extract itself; everything here may change.
```

Create `src/cronos_extract/_api/errors.py`:

```python
# ABOUTME: The exceptions the cronos_extract API raises for a database it cannot read at all.
# ABOUTME: Problems it can survive, such as one corrupt record, are diagnostics instead.


class CronosError(Exception):
    """The base class of the errors cronos_extract raises for a database it cannot read."""


class NotACronosFile(CronosError):
    """A CroStru or CroBank file is missing, cannot be opened, is not a regular file or is not a Cronos file."""


class UnsupportedVersion(CronosError):
    """CroStru or CroBank is a CronosPro version this release does not read."""


class DatabaseDefinitionError(CronosError):
    """The database definition in CroStru record 1 is missing or cannot be decoded."""
```

Create `src/cronos_extract/_api/diagnostics.py`:

```python
# ABOUTME: Diagnostics: the problems the cronos_extract API survives while reading, such as a corrupt record.
# ABOUTME: DiagnosticLog keeps the first few, counts all and passes each to a callback, so memory stays bounded.
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import overload, override

# How many diagnostics a bank keeps; counts and the callback cover every one.
DIAGNOSTICS_KEPT = 1000


class DiagnosticKind(StrEnum):
    """What kind of problem a Diagnostic reports. Later versions may add kinds."""

    CORRUPT_RECORD = "corrupt_record"
    UNDECODABLE_FIELD = "undecodable_field"
    INVALID_VALUE = "invalid_value"
    UNDECODABLE_TABLE = "undecodable_table"
    UNSUPPORTED_TABLE = "unsupported_table"
    UNEXPECTED_STRUCTURE = "unexpected_structure"
    UNRESOLVED_FILE_REFERENCE = "unresolved_file_reference"
    UNREADABLE_FILE = "unreadable_file"
    UNUSED_KOD = "unused_kod"


@dataclass(frozen=True)
class Diagnostic:
    """
    A problem found while reading, which reading survived.

    `file` is a canonical file name such as "CroBank.dat", `table` a table name, `record` a CroBank record number
    and `field` a field name, each None when it does not apply. The message never holds record data.
    """

    kind: DiagnosticKind
    message: str
    file: str | None = None
    table: str | None = None
    record: int | None = None
    field: str | None = None


class DiagnosticsView(Sequence[Diagnostic]):
    """A read-only view of a list of diagnostics, which grows as the list does."""

    def __init__(self, diagnostics: list[Diagnostic]) -> None:
        self._diagnostics = diagnostics

    @overload
    def __getitem__(self, index: int) -> Diagnostic: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[Diagnostic, ...]: ...

    @override
    def __getitem__(self, index: int | slice) -> Diagnostic | tuple[Diagnostic, ...]:
        if isinstance(index, slice):
            return tuple(self._diagnostics[index])
        return self._diagnostics[index]

    @override
    def __len__(self) -> int:
        return len(self._diagnostics)

    @override
    def __repr__(self) -> str:
        return f"DiagnosticsView({self._diagnostics!r})"


class DiagnosticLog:
    """
    Collects a bank's diagnostics.

    It keeps the first DIAGNOSTICS_KEPT of them, counts every one by kind, and passes every one to `on_diagnostic`
    after keeping and counting it. An exception from `on_diagnostic` reaches the code that recorded the diagnostic.
    """

    def __init__(self, on_diagnostic: Callable[[Diagnostic], object] | None) -> None:
        self._kept: list[Diagnostic] = []
        self._counts: Counter[DiagnosticKind] = Counter()
        self._on_diagnostic = on_diagnostic
        self.kept: Sequence[Diagnostic] = DiagnosticsView(self._kept)
        self.counts: Mapping[DiagnosticKind, int] = MappingProxyType(self._counts)

    def record(self, diagnostic: Diagnostic) -> None:
        """Keep `diagnostic` while fewer than DIAGNOSTICS_KEPT are kept, count it, and pass it to the callback."""
        if len(self._kept) < DIAGNOSTICS_KEPT:
            self._kept.append(diagnostic)
        self._counts[diagnostic.kind] += 1
        if self._on_diagnostic is not None:
            self._on_diagnostic(diagnostic)


class RecordNumbers:
    """A set of record numbers from 0 to `size`, held as one bit each, so marking every record stays small."""

    def __init__(self, size: int) -> None:
        self._bits = bytearray(size // 8 + 1)

    def add(self, number: int) -> bool:
        """Add `number`, returning whether it was not in the set before."""
        index, bit = divmod(number, 8)
        if self._bits[index] >> bit & 1:
            return False
        self._bits[index] |= 1 << bit
        return True
```

If ty rejects the `# ty: ignore[invalid-assignment]` code in the test, run `uv run ty check` and use the rule name it reports.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_api_diagnostics.py`
Expected: all pass.

- [ ] **Step 5: Run the suite and linters, then commit**

```bash
fail() { echo "STOPPED: $*"; exit 1; }
uv run pytest -q > /tmp/t3-pytest.txt 2>&1 || fail pytest
uv run ruff check > /tmp/t3-ruff.txt 2>&1 || fail ruff
uv run ruff format --check > /tmp/t3-format.txt 2>&1 || fail format
uv run ty check > /tmp/t3-ty.txt 2>&1 || fail ty
git add src/cronos_extract/_api tests/test_api_diagnostics.py
git commit -F - <<'EOF' || fail commit
Add the API's exceptions and diagnostics

CronosError and its subclasses are raised for a database that cannot
be read at all. Diagnostics report the problems reading survives; the
log keeps the first 1,000, counts every one and passes each to a
callback, and RecordNumbers marks records one bit each.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 4: `Kod`

Spec: P7, P12 (`Kod.from_hex`).

**Files:**
- Create: `src/cronos_extract/_api/kod.py`
- Test: `tests/test_api_kod.py`

**Interfaces:**
- Consumes: nothing.
- Produces, in `cronos_extract._api.kod`:
  - `Kod` (frozen dataclass): `table: tuple[int, ...]`; `Kod.default() -> Kod`; `Kod.from_table(table: Sequence[int]) -> Kod`; `Kod.from_hex(text: str) -> Kod`; `kod.hex() -> str`. Construction raises `ValueError` unless `table` is a permutation of 0–255 made of `int`s.
  - `kod_coder(kod: Kod | None) -> KODcoding | None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_kod.py`:

```python
# ABOUTME: Tests for Kod, the cronos_extract API's KOD table: construction, validation and hex conversion.
# ABOUTME: Also checks that its internal decoder decodes exactly as the koddecoder module does.
import pytest
from cronos_builder import random_kod

from cronos_extract._api.kod import Kod, kod_coder
from cronos_extract.koddecoder import INITIAL_KOD, KODcoding


def test_the_default_kod_is_the_initial_kod_table() -> None:
    assert Kod.default().table == tuple(INITIAL_KOD)


def test_a_kod_from_a_table_keeps_the_table() -> None:
    table = random_kod(seed=5)

    assert Kod.from_table(table).table == tuple(table)


def test_kods_compare_and_hash_by_table() -> None:
    assert Kod.from_table(INITIAL_KOD) == Kod.default()
    assert Kod.from_table(random_kod(seed=5)) != Kod.default()
    assert len({Kod.default(), Kod.from_table(INITIAL_KOD)}) == 1


@pytest.mark.parametrize(
    "table",
    [
        list(range(255)),
        [*range(256), 0],
        [0, *range(255)],
        [*range(255), 256],
        [-1, *range(1, 256)],
        [False, True, *range(2, 256)],
        [0.0, *range(1, 256)],
    ],
    ids=["too-short", "too-long", "duplicate", "256", "negative", "bool", "float"],
)
def test_a_table_that_is_not_a_permutation_of_ints_is_refused(table: list[object]) -> None:
    with pytest.raises(ValueError, match="each number from 0 to 255 exactly once"):
        Kod.from_table(table)  # ty: ignore[invalid-argument-type]


def test_hex_round_trips() -> None:
    kod = Kod.from_table(random_kod(seed=5))

    assert kod.hex() == bytes(random_kod(seed=5)).hex()
    assert Kod.from_hex(kod.hex()) == kod
    assert Kod.from_hex(kod.hex().upper()) == kod


@pytest.mark.parametrize(
    "text",
    [
        bytes(range(255)).hex(),
        bytes(range(256)).hex() + "00",
        " " + bytes(range(256)).hex()[1:],
        bytes(range(256)).hex()[:-1] + "\n",
        "zz" + bytes(range(256)).hex()[2:],
    ],
    ids=["510-digits", "514-digits", "space", "newline", "not-hex"],
)
def test_hex_that_is_not_512_hex_digits_is_refused(text: str) -> None:
    with pytest.raises(ValueError, match="exactly 512 hex digits"):
        Kod.from_hex(text)


def test_hex_digits_that_are_not_a_permutation_are_refused() -> None:
    with pytest.raises(ValueError, match="each number from 0 to 255 exactly once"):
        Kod.from_hex("00" * 256)


def test_kod_coder_decodes_as_the_koddecoder_does() -> None:
    table = random_kod(seed=5)
    coder = kod_coder(Kod.from_table(table))

    assert coder is not None
    assert coder.decode(3, b"any bytes") == KODcoding(table).decode(3, b"any bytes")
    assert kod_coder(None) is None
```

If ty reports a different rule name for the deliberate bad argument, use the name it reports.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/test_api_kod.py`
Expected: collection fails with `ModuleNotFoundError: No module named 'cronos_extract._api.kod'`.

- [ ] **Step 3: Implement**

Create `src/cronos_extract/_api/kod.py`:

```python
# ABOUTME: Kod: a CronosPro KOD table, the byte substitution that obfuscates records, as an immutable value.
# ABOUTME: Validates that a table is a permutation of 0-255 and converts it to and from 512 hex digits.
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Self

from ..koddecoder import INITIAL_KOD, KODcoding

HEX_KOD = re.compile(r"[0-9a-fA-F]{512}")


@dataclass(frozen=True)
class Kod:
    """A KOD table: a permutation of the numbers 0 to 255. Two Kods are equal when their tables are."""

    table: tuple[int, ...]

    def __post_init__(self) -> None:
        if (
            len(self.table) != 256
            or any(type(entry) is not int for entry in self.table)
            or sorted(self.table) != list(range(256))
        ):
            raise ValueError("a KOD table must hold each number from 0 to 255 exactly once")

    @classmethod
    def default(cls) -> Self:
        """The KOD table CronosPro uses for databases that are not encrypted with their own."""
        return cls(tuple(INITIAL_KOD))

    @classmethod
    def from_table(cls, table: Sequence[int]) -> Self:
        """A Kod holding `table`. Raises ValueError unless it is a permutation of 0 to 255."""
        return cls(tuple(table))

    @classmethod
    def from_hex(cls, text: str) -> Self:
        """
        A Kod from 512 hex digits, two per table entry, in either case and with nothing else around them.
        Raises ValueError for any other text, or when the digits are not a permutation of 0 to 255.
        """
        if not HEX_KOD.fullmatch(text):
            raise ValueError("a KOD in hex must be exactly 512 hex digits, two per table entry")
        return cls(tuple(bytes.fromhex(text)))

    def hex(self) -> str:
        """The table as 512 lower-case hex digits, as from_hex reads it."""
        return bytes(self.table).hex()


def kod_coder(kod: Kod | None) -> KODcoding | None:
    """The internal decoder for `kod`, or None to read without KOD decoding."""
    return None if kod is None else KODcoding(list(kod.table))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_api_kod.py`
Expected: all pass.

- [ ] **Step 5: Run the suite and linters, then commit**

```bash
fail() { echo "STOPPED: $*"; exit 1; }
uv run pytest -q > /tmp/t4-pytest.txt 2>&1 || fail pytest
uv run ruff check > /tmp/t4-ruff.txt 2>&1 || fail ruff
uv run ruff format --check > /tmp/t4-format.txt 2>&1 || fail format
uv run ty check > /tmp/t4-ty.txt 2>&1 || fail ty
git add src/cronos_extract/_api/kod.py tests/test_api_kod.py
git commit -F - <<'EOF' || fail commit
Add Kod, the API's KOD table value

Kod holds a permutation of 0-255 and refuses anything else, including
hex that is not exactly 512 hex digits.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 5: `FileInfo`, used by the survey

Spec: P5, P12 (`FileInfo.path`, `generation`).

**Files:**
- Create: `src/cronos_extract/_api/info.py`, `tests/test_api_info.py`
- Modify: `src/cronos_extract/_format/header.py`, `src/cronos_extract/survey.py`, `tests/test_survey.py`

**Interfaces:**
- Consumes: Task 2's `open_regular_file`; Task 1's `write_database(..., version=...)`.
- Produces:
  - `cronos_extract._format.header.Generation = Literal["v3", "v4", "v7", "unknown"]`; `DatHeader.generation -> Generation`.
  - `cronos_extract._api.info.FileInfo` (frozen dataclass): `name: str`, `path: Path`, `version: str | None`, `generation: Generation | None`, `use64bit: bool | None`, `kod_encoded: bool | None`, `compressed: bool | None`, `own_kod: bool | None`, `problem: str | None`. Either `problem` is `None` and every other field is set, or `problem` is set and the six header fields are `None`.
  - `info_from_header(name: str, path: Path, header: DatHeader) -> FileInfo`
  - `info_from_problem(name: str, path: Path, problem: str) -> FileInfo`
  - `read_file_info(name: str, path: Path) -> FileInfo` — never raises for an unreadable file.
  - `survey.SurveyedDatabase.files: tuple[FileInfo, ...]`; `survey.SurveyedFile` and `survey.survey_file` no longer exist.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_info.py`:

```python
# ABOUTME: Tests for FileInfo, the per-file version and encoding flags that bank.info and the survey report.
# ABOUTME: Reads headers of databases from tests/cronos_builder.py and of broken, FIFO and missing files.
import dataclasses
import os
from pathlib import Path

import pytest
from cronos_builder import random_kod, write_database, write_header_only_datafile

from cronos_extract._api.info import FileInfo, read_file_info


def test_file_info_reports_a_v3_header(tmp_path: Path) -> None:
    dbdir = Path(write_database(tmp_path / "db", []))

    info = read_file_info("Stru", dbdir / "CroStru.dat")

    assert info == FileInfo(
        name="Stru",
        path=dbdir / "CroStru.dat",
        version="01.04",
        generation="v3",
        use64bit=False,
        kod_encoded=False,
        compressed=False,
        own_kod=True,
        problem=None,
    )


def test_file_info_reports_a_kod_encoded_v4_header(tmp_path: Path) -> None:
    dbdir = Path(write_database(tmp_path / "db", [], random_kod(seed=1), version=b"01.11"))

    info = read_file_info("Bank", dbdir / "CroBank.dat")

    assert (info.version, info.generation, info.use64bit, info.kod_encoded, info.own_kod, info.problem) == (
        "01.11",
        "v4",
        True,
        True,
        True,
        None,
    )


def test_file_info_reports_a_v7_header_without_a_problem(tmp_path: Path) -> None:
    write_header_only_datafile(tmp_path, "Bank", encoding=3)

    info = read_file_info("Bank", tmp_path / "CroBank.dat")

    assert (info.version, info.generation, info.compressed, info.problem) == ("01.19", "v7", True, None)


@pytest.mark.parametrize(
    ("content", "problem"),
    [(b"CroFile\x00", "shorter than its 19-byte header"), (b"NotACronosFile" + bytes(20), "not a Cronos file")],
)
def test_file_info_reports_a_header_problem_with_no_flags(tmp_path: Path, content: bytes, problem: str) -> None:
    (tmp_path / "CroStru.dat").write_bytes(content)

    info = read_file_info("Stru", tmp_path / "CroStru.dat")

    assert info.problem is not None
    assert problem in info.problem
    assert (info.version, info.generation, info.use64bit, info.kod_encoded, info.compressed, info.own_kod) == (
        None,
        None,
        None,
        None,
        None,
        None,
    )


def test_file_info_reports_a_fifo_as_not_a_regular_file(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "CroStru.dat")

    assert read_file_info("Stru", tmp_path / "CroStru.dat").problem == "CroStru.dat is not a regular file"


def test_file_info_reports_a_missing_file(tmp_path: Path) -> None:
    problem = read_file_info("Stru", tmp_path / "CroStru.dat").problem

    assert problem is not None
    assert "No such file or directory" in problem


def test_file_info_is_frozen_and_hashable(tmp_path: Path) -> None:
    info = read_file_info("Stru", tmp_path / "CroStru.dat")

    assert hash(info) == hash(dataclasses.replace(info))
    with pytest.raises(dataclasses.FrozenInstanceError):
        info.name = "Bank"  # ty: ignore[invalid-assignment]
```

In `tests/test_survey.py`, change the two tests that read `.header` to read the `FileInfo` fields directly:

```python
    assert stru.problem is None
    assert stru.generation == "v3"
```

in place of `assert stru.header is not None` / `assert stru.header.generation == "v3"`, and

```python
    assert bank.problem is None
    assert (bank.version, bank.generation, bank.compressed) == ("01.19", "v7", True)
```

in place of `assert bank.header is not None` / `assert (bank.header.version_text, bank.header.generation, bank.header.compressed) == ("01.19", "v7", True)`.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/test_api_info.py tests/test_survey.py`
Expected: `test_api_info.py` fails to collect with `ModuleNotFoundError: No module named 'cronos_extract._api.info'`; the two changed survey tests FAIL with `AttributeError: 'SurveyedFile' object has no attribute 'generation'` (or `'version'`).

- [ ] **Step 3: Implement**

In `src/cronos_extract/_format/header.py`, change `from typing import BinaryIO` to `from typing import BinaryIO, Literal`, add after the version constants:

```python
# The CronosPro generations a header's version belongs to.
type Generation = Literal["v3", "v4", "v7", "unknown"]
```

and change the property's signature to `def generation(self) -> Generation:`.

If ty does not accept a `type` alias inside `Literal` comparisons or as a dataclass field annotation, use `Generation = Literal["v3", "v4", "v7", "unknown"]` instead and report it.

Create `src/cronos_extract/_api/info.py`:

```python
# ABOUTME: FileInfo: one Cro*.dat file's format version and encoding flags, or the problem that stopped them being read.
# ABOUTME: Shared by bank.info and the survey, which report files the same way; reads only the 19-byte header.
from dataclasses import dataclass
from pathlib import Path

from .._format.files import open_regular_file
from .._format.header import DatHeader, Generation, read_dat_header


@dataclass(frozen=True)
class FileInfo:
    """
    One Cro*.dat file, as its header describes it.

    `name` is the part of the file name between "Cro" and ".dat", as spelt on disk, such as "Stru", and `path` the
    file's path. When `problem` is None every other field is set; when the header could not be read, `problem`
    says why and the version and flag fields are None.
    """

    name: str
    path: Path
    version: str | None
    generation: Generation | None
    use64bit: bool | None
    kod_encoded: bool | None
    compressed: bool | None
    own_kod: bool | None
    problem: str | None


def info_from_header(name: str, path: Path, header: DatHeader) -> FileInfo:
    """The FileInfo of the file at `path`, whose header is `header`."""
    return FileInfo(
        name=name,
        path=path,
        version=header.version_text,
        generation=header.generation,
        use64bit=header.use64bit,
        kod_encoded=header.kod_encoded,
        compressed=header.compressed,
        own_kod=header.own_kod,
        problem=None,
    )


def info_from_problem(name: str, path: Path, problem: str) -> FileInfo:
    """The FileInfo of the file at `path`, whose header could not be read because of `problem`."""
    return FileInfo(
        name=name,
        path=path,
        version=None,
        generation=None,
        use64bit=None,
        kod_encoded=None,
        compressed=None,
        own_kod=None,
        problem=problem,
    )


def read_file_info(name: str, path: Path) -> FileInfo:
    """
    Read the header of the .dat file at `path`, returning the problem that stopped it instead of raising.

    Only a regular file is opened, and without blocking, so a FIFO named like a Cro file is reported, not waited on.
    """
    try:
        with open_regular_file(path) as file:
            return info_from_header(name, path, read_dat_header(file, where=path.name))
    except (ValueError, OSError) as e:
        return info_from_problem(name, path, str(e))
```

In `src/cronos_extract/survey.py`:
- Remove `import stat`, the `SurveyedFile` class and `survey_file`; remove `DatHeader` and `read_dat_header` from the imports and add `from ._api.info import FileInfo, read_file_info`.
- Change `SurveyedDatabase.files` to `files: tuple[FileInfo, ...]`.
- In `survey_databases`, replace `survey_file(path / name)` with `read_file_info(name[3:-4] or name, path / name)`.
- Replace `describe_file` with:

```python
def describe_file(file: FileInfo) -> str:
    """Return the survey line for one file, without its database's directory."""
    if file.problem is not None:
        return f"{file.name:<6}{file.problem}"
    flags = [
        f"{'64' if file.use64bit else '32'}-bit",
        "kod-encoded" if file.kod_encoded else "plain",
        "compressed" if file.compressed else "uncompressed",
    ]
    if file.own_kod:
        flags.append("own-kod")
    return f"{file.name:<6}{file.version}  {file.generation:<7}  " + "  ".join(flags)
```

- In `format_counts`, replace the loop body with:

```python
        for file in database.files:
            if file.version is None or file.generation is None:
                problems += 1
            else:
                counts[(file.version, file.generation)] += 1
```

- In `format_jsonl`, replace the per-file dictionary with:

```python
                    {
                        "name": file.name,
                        "version": file.version,
                        "generation": file.generation,
                        "use64bit": file.use64bit,
                        "kod_encoded": file.kod_encoded,
                        "compressed": file.compressed,
                        "own_kod": file.own_kod,
                        "problem": file.problem,
                    }
```

`survey_file`'s name rule was `path.name[3:-4] or path.name`; `name` in `survey_databases` is the file name, so `name[3:-4] or name` is the same rule.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_api_info.py tests/test_survey.py tests/test_cli_characterisation.py`
Expected: all pass. The survey's text, `--counts` and `--jsonl` outputs are unchanged: every existing survey test passes without other edits.

- [ ] **Step 5: Run the suite and linters, then commit**

```bash
fail() { echo "STOPPED: $*"; exit 1; }
uv run pytest -q > /tmp/t5-pytest.txt 2>&1 || fail pytest
uv run ruff check > /tmp/t5-ruff.txt 2>&1 || fail ruff
uv run ruff format --check > /tmp/t5-format.txt 2>&1 || fail format
uv run ty check > /tmp/t5-ty.txt 2>&1 || fail ty
test -z "$(git diff master -- tests/golden)" || fail golden
git add src/cronos_extract/_format/header.py src/cronos_extract/_api/info.py src/cronos_extract/survey.py tests/test_api_info.py tests/test_survey.py
git commit -F - <<'EOF' || fail commit
Describe Cro files with FileInfo in the survey and the API

FileInfo replaces the survey's SurveyedFile, so bank.info and the
survey report a file the same way. Headers are read through
open_regular_file, which checks the open descriptor, so a file swapped
for a FIFO between a stat and an open can no longer block the survey.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 6: The survey streams its results

Spec: P6 "Carried-forward item".

**Files:**
- Modify: `src/cronos_extract/survey.py`, `src/cronos_extract/cli.py`
- Test: `tests/test_survey.py`

**Interfaces:**
- Consumes: Task 5's `SurveyedDatabase`.
- Produces:
  - `survey_databases(root: Path, on_problem: Callable[[OSError], object] | None = None) -> Iterator[SurveyedDatabase]`
  - `survey_roots(roots: Iterable[Path], on_problem: Callable[[OSError], object] | None = None) -> Iterator[SurveyedDatabase]`

- [ ] **Step 1: Write the failing tests**

In `tests/test_survey.py`, change `from cronos_extract.survey import survey_databases` to `from cronos_extract.survey import survey_databases, survey_roots`, and in `test_survey_reports_a_directory_it_cannot_list` change `survey_databases(tmp_path, problems)` to `survey_databases(tmp_path, problems.append)`. Append:

```python
def test_survey_roots_yields_a_database_before_walking_the_roots_after_it(tmp_path: Path) -> None:
    write_database(tmp_path / "first" / "db", [])
    (tmp_path / "second").mkdir()

    databases = survey_roots([tmp_path / "first", tmp_path / "second"])
    first = next(databases)
    write_database(tmp_path / "second" / "db", [])
    rest = list(databases)

    assert first.directory == tmp_path / "first" / "db"
    assert [database.directory for database in rest] == [tmp_path / "second" / "db"]


@pytest.mark.skipif(os.getuid() == 0, reason="root can list a directory whatever its permissions are")
def test_survey_roots_reports_an_unlistable_directory_when_the_walk_reaches_it(tmp_path: Path) -> None:
    write_database(tmp_path / "a" / "db", [])
    write_header_only_datafile(tmp_path / "b" / "locked", "Stru")
    write_database(tmp_path / "c" / "db", [])
    (tmp_path / "b" / "locked").chmod(0o000)
    events: list[tuple[str, str]] = []

    try:
        for database in survey_roots(
            [tmp_path / "a", tmp_path / "b", tmp_path / "c"],
            lambda problem: events.append(("problem", str(problem.filename))),
        ):
            events.append(("database", str(database.directory)))
    finally:
        (tmp_path / "b" / "locked").chmod(0o700)

    assert events == [
        ("database", str(tmp_path / "a" / "db")),
        ("problem", str(tmp_path / "b" / "locked")),
        ("database", str(tmp_path / "c" / "db")),
    ]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/test_survey.py`
Expected: `test_survey_roots_yields_a_database_before_walking_the_roots_after_it` FAILS with `TypeError: 'list' object is not an iterator`; the unlistable-directory tests FAIL with `AttributeError: 'function' object has no attribute 'append'` (or `'builtin_function_or_method'`).

- [ ] **Step 3: Implement**

In `src/cronos_extract/survey.py`, add `Callable` to the `collections.abc` import. Replace `survey_databases`'s signature, the last sentence of its docstring and the `os.walk` call:

```python
def survey_databases(root: Path, on_problem: Callable[[OSError], object] | None = None) -> Iterator[SurveyedDatabase]:
```

docstring's last sentence: "A directory that cannot be listed is passed to `on_problem` when the walk reaches it; without `on_problem` such a directory is passed over in silence."

```python
    for directory, subdirectories, filenames in os.walk(root, onerror=on_problem, followlinks=False):
```

Replace `survey_roots` with:

```python
def survey_roots(
    roots: Iterable[Path], on_problem: Callable[[OSError], object] | None = None
) -> Iterator[SurveyedDatabase]:
    """
    Survey every directory in `roots` in order, yielding each database as the walk finds it.

    A database found under more than one root, because the roots overlap or repeat, is yielded once.
    A directory that cannot be listed is passed to `on_problem` when the walk reaches it.
    """
    seen: set[Path] = set()
    for root in roots:
        for database in survey_databases(root, on_problem):
            resolved = database.directory.resolve()
            if resolved not in seen:
                seen.add(resolved)
                yield database
```

In `src/cronos_extract/cli.py`, add before `run_survey`:

```python
def warn_unlistable(problem: OSError) -> None:
    """Report on stderr a directory the survey cannot list."""
    print(f"warning: {problem.filename} cannot be listed: {problem.strerror}; skipping it", file=sys.stderr)
```

and replace the first four lines of `run_survey`'s body with:

```python
    databases = survey.survey_roots(collect_roots(args, parser), warn_unlistable)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_survey.py tests/test_cli_characterisation.py`
Expected: all pass.

- [ ] **Step 5: Run the suite and linters, then commit**

```bash
fail() { echo "STOPPED: $*"; exit 1; }
uv run pytest -q > /tmp/t6-pytest.txt 2>&1 || fail pytest
uv run ruff check > /tmp/t6-ruff.txt 2>&1 || fail ruff
uv run ruff format --check > /tmp/t6-format.txt 2>&1 || fail format
uv run ty check > /tmp/t6-ty.txt 2>&1 || fail ty
test -z "$(git diff master -- tests/golden)" || fail golden
git add src/cronos_extract/survey.py src/cronos_extract/cli.py tests/test_survey.py
git commit -F - <<'EOF' || fail commit
Stream survey results as the walk finds them

survey_roots is a generator, so cronos-extract survey prints each
database as soon as it is found, and a warning about a directory that
cannot be listed appears when the walk reaches it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---
### Task 7: Records, fields and values

Spec: P4, P6 (eager decoding), P8, P12 "Data types".

**Files:**
- Create: `src/cronos_extract/_api/values.py`, `tests/test_api_values.py`

**Interfaces:**
- Consumes: Task 3's `Diagnostic`, `DiagnosticKind`; Task 1's `erdgeist_table_definition`; Task 2's `TableDefinition(..., warn=...)`.
- Produces, in `cronos_extract._api.values`:
  - `FieldDefinition` (frozen): `name: str`, `type: int`
  - `FileReference` (frozen): `name: str`, `extension: str`, `record: int | None`
  - `EmbeddedFile` (frozen): `record: int`, `data: bytes`, `name: str | None`
  - `type FieldValue = str | datetime.date | datetime.time | FileReference | None`
  - `Field` (frozen): `definition: FieldDefinition`, `value: FieldValue`, `text: str`, `raw: bytes`
  - `Record` (frozen): `number: int`, `fields: tuple[Field, ...]`, `diagnostics: tuple[Diagnostic, ...]`, `__getitem__(name: str) -> Field`
  - `decode_record(number: int, table: str, definitions: Sequence[FieldDefinition], fielddefs: Sequence[Datamodel.FieldDefinition], data: bytes) -> Record` — `data` is the CroBank record after its table id byte. It does not raise for undecodable fields; it requires `fielddefs[0]` to be the system number (type 0), which Task 9 checks when it opens a table.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_values.py`:

```python
# ABOUTME: Tests for how the API decodes records, with each field type's value, text, raw bytes and diagnostics.
# ABOUTME: Decodes records laid out by tests/cronos_builder.py against the real "erdgeist" table definition.
import dataclasses
import datetime

import pytest
from cronos_builder import (
    TEST_TABLE_FIELD_COUNT,
    TEST_TABLE_ID,
    bank_record,
    erdgeist_table_definition,
    file_reference_field,
)

from cronos_extract._api.diagnostics import Diagnostic, DiagnosticKind
from cronos_extract._api.values import FieldDefinition, FileReference, Record, decode_record
from cronos_extract.Datamodel import TableDefinition

DATE, TIME, FILE, TEXT, LINK = 3, 4, 5, 0, 7


def decode(fields: list[bytes], number: int = 7) -> Record:
    """Decode a record of the erdgeist table holding `fields`, one per field after the system number."""
    table = TableDefinition(erdgeist_table_definition(), warn=lambda message: None)
    definitions = tuple(FieldDefinition(field.name, field.typ) for field in table.fields)
    return decode_record(number, "erdgeist", definitions, table.fields, bank_record(TEST_TABLE_ID, fields)[1:])


def with_field(index: int, data: bytes) -> list[bytes]:
    """The fields of a record whose field `index` (0 is Entry #1) holds `data` and whose other fields are empty."""
    fields = [b""] * TEST_TABLE_FIELD_COUNT
    fields[index] = data
    return fields


def invalid_value(field: str, message: str) -> Diagnostic:
    return Diagnostic(
        DiagnosticKind.INVALID_VALUE, message, file="CroBank.dat", table="erdgeist", record=7, field=field
    )


def test_the_system_number_is_the_record_number_as_text_with_no_raw_bytes() -> None:
    field = decode(with_field(TEXT, b""), number=42).fields[0]

    assert field.definition == FieldDefinition("Системный номер", 0)
    assert (field.value, field.text, field.raw) == ("42", "42", b"")


def test_a_record_has_one_field_per_field_definition_in_order() -> None:
    record = decode(with_field(TEXT, b"x"))

    assert [field.definition.name for field in record.fields] == [
        "Системный номер",
        *(f"Entry #{number}" for number in range(1, 12)),
    ]


def test_a_text_field_is_its_text() -> None:
    field = decode(with_field(TEXT, b"Hammersley")).fields[1]

    assert (field.value, field.text, field.raw) == ("Hammersley", "Hammersley", b"Hammersley")


def test_an_empty_field_has_no_value() -> None:
    field = decode(with_field(TEXT, b"x"))["Entry #4"]

    assert (field.value, field.text, field.raw) == (None, "", b"")


def test_a_full_date_is_a_date() -> None:
    record = decode(with_field(DATE, b"1240315"))

    assert (record["Entry #4"].value, record["Entry #4"].text, record["Entry #4"].raw) == (
        datetime.date(2024, 3, 15),
        "2024-03-15",
        b"1240315",
    )
    assert record.diagnostics == ()


def test_a_year_only_date_is_its_text_without_a_diagnostic() -> None:
    record = decode(with_field(DATE, b"850000"))

    assert (record["Entry #4"].value, record["Entry #4"].text) == ("1985-00-00", "1985-00-00")
    assert record.diagnostics == ()


def test_a_date_field_holding_words_is_its_text_with_a_diagnostic() -> None:
    record = decode(with_field(DATE, "до 1990".encode("cp1251")))

    assert record["Entry #4"].value == "до 1990"
    assert record.diagnostics == (invalid_value("Entry #4", "the value is not a date; it is kept as text"),)


def test_a_date_with_month_13_is_its_text_with_a_diagnostic() -> None:
    record = decode(with_field(DATE, b"851301"))

    assert record["Entry #4"].value == "1985-13-01"
    assert record.diagnostics == (invalid_value("Entry #4", "the value is not a valid date; it is kept as text"),)


def test_a_date_with_only_a_zero_day_is_its_text_with_a_diagnostic() -> None:
    record = decode(with_field(DATE, b"850300"))

    assert record["Entry #4"].value == "1985-03-00"
    assert [diagnostic.kind for diagnostic in record.diagnostics] == [DiagnosticKind.INVALID_VALUE]


def test_a_time_is_a_time() -> None:
    record = decode(with_field(TIME, b"0930"))

    assert (record["Entry #5"].value, record["Entry #5"].text) == (datetime.time(9, 30), "09:30")
    assert record.diagnostics == ()


def test_a_time_past_midnight_is_its_text_with_a_diagnostic() -> None:
    record = decode(with_field(TIME, b"2561"))

    assert record["Entry #5"].value == "25:61"
    assert record.diagnostics == (invalid_value("Entry #5", "the value is not a valid time; it is kept as text"),)


def test_a_time_field_holding_a_letter_is_its_text_with_a_diagnostic() -> None:
    record = decode(with_field(TIME, b"x"))

    assert record["Entry #5"].value == "x"
    assert record.diagnostics == (invalid_value("Entry #5", "the value is not a time; it is kept as text"),)


def test_a_file_reference_is_a_file_reference_whose_raw_bytes_omit_the_complex_field_header() -> None:
    stored = file_reference_field("report", "pdf", 12)

    field = decode(with_field(FILE, stored))["Entry #6"]

    assert field.value == FileReference(name="report", extension="pdf", record=12)
    assert field.text == "report pdf 12"
    assert field.raw == stored[5:]


@pytest.mark.parametrize("record_text", ["+12", " 12", "1_2", "x", "", "9" * 5000])
def test_a_file_reference_whose_record_is_not_ascii_digits_has_no_record(record_text: str) -> None:
    field = decode(with_field(FILE, file_reference_field("report", "pdf", record_text)))["Entry #6"]

    assert isinstance(field.value, FileReference)
    assert field.value.record is None


def test_a_link_field_is_its_hex_text() -> None:
    field = decode(with_field(LINK, b"\x01\x02"))["Entry #8"]

    assert isinstance(field.value, str)
    assert field.value == field.text
    assert field.raw == b"\x01\x02"


def test_a_field_that_cannot_be_decoded_leaves_it_and_the_rest_empty_with_a_diagnostic() -> None:
    record = decode([b"\x1b\xff\xff\xff\x7f"], number=7)

    assert len(record.fields) == 12
    assert [field.value for field in record.fields[1:]] == [None] * 11
    (diagnostic,) = record.diagnostics
    assert (diagnostic.kind, diagnostic.file, diagnostic.table, diagnostic.record, diagnostic.field) == (
        DiagnosticKind.UNDECODABLE_FIELD,
        "CroBank.dat",
        "erdgeist",
        7,
        "Entry #1",
    )
    assert "could not be decoded" in diagnostic.message


def test_a_record_looks_fields_up_by_name() -> None:
    record = decode(with_field(TEXT, b"x"))

    assert record["Entry #1"] is record.fields[1]
    with pytest.raises(KeyError):
        record["Entry #12"]


def test_diagnostic_messages_hold_no_field_data() -> None:
    record = decode(with_field(DATE, b"secret-value"))

    assert all("secret" not in diagnostic.message for diagnostic in record.diagnostics)


def test_records_and_fields_are_frozen() -> None:
    record = decode(with_field(TEXT, b"x"))

    with pytest.raises(dataclasses.FrozenInstanceError):
        record.number = 8  # ty: ignore[invalid-assignment]
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.fields[1].text = "y"  # ty: ignore[invalid-assignment]
```

`"9" * 5000` has more digits than `int()` converts by default (4,300), so it checks that such a record number gives `None` instead of raising.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/test_api_values.py`
Expected: collection fails with `ModuleNotFoundError: No module named 'cronos_extract._api.values'`.

- [ ] **Step 3: Implement**

Create `src/cronos_extract/_api/values.py`:

```python
# ABOUTME: The API's record types: field definitions, fields with typed values, records, file references and files.
# ABOUTME: decode_record turns a CroBank record decoded by Datamodel into them, with field problems as diagnostics.
import datetime
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from ..Datamodel import Field as DecodedField
from ..Datamodel import FieldDefinition as DecodedFieldDefinition
from ..Datamodel import Record as DecodedRecord
from .diagnostics import Diagnostic, DiagnosticKind

FIELD_TYPE_DATE = 4
FIELD_TYPE_TIME = 5
FIELD_TYPE_FILE = 6
BANK_FILE = "CroBank.dat"
# Datamodel formats a date as the year, month and day, and a time as the hour and minute.
DATE_TEXT = re.compile(r"(-?[0-9]+)-([0-9]{2})-([0-9]{2})")
TIME_TEXT = re.compile(r"([0-9]{2}):([0-9]{2})")
ASCII_DIGITS = re.compile(r"[0-9]+")


@dataclass(frozen=True)
class FieldDefinition:
    """A field of a table: its name and its CronosPro field type code."""

    name: str
    type: int


@dataclass(frozen=True)
class FileReference:
    """A field's reference to a file stored in the Files table: the file's name, extension and CroBank record."""

    name: str
    extension: str
    record: int | None


@dataclass(frozen=True)
class EmbeddedFile:
    """
    A file stored in the Files table: its CroBank record number and its bytes.

    `name` is "name.extension" when the file was read through a FileReference, and None from Bank.files(), because
    the Files table stores no names.
    """

    record: int
    data: bytes
    name: str | None


type FieldValue = str | datetime.date | datetime.time | FileReference | None


@dataclass(frozen=True)
class Field:
    """
    One field of a record.

    `text` is the field for display. `value` is a datetime.date or datetime.time for a date or time field, a
    FileReference for a file field, None for an empty field, and otherwise the text; a date stored with only its
    year, and a date or time that does not parse, are the text. `raw` is the field's bytes in the record, without
    the field separator or a complex field's marker and length.
    """

    definition: FieldDefinition
    value: FieldValue
    text: str
    raw: bytes


@dataclass(frozen=True)
class Record:
    """A record of a table: its CroBank record number, one field per field definition, and its diagnostics."""

    number: int
    fields: tuple[Field, ...]
    diagnostics: tuple[Diagnostic, ...]

    def __getitem__(self, name: str) -> Field:
        """The first field named `name`. Raises KeyError when there is none."""
        for field in self.fields:
            if field.definition.name == name:
                return field
        raise KeyError(name)


def parse_date(text: str) -> tuple[FieldValue, str | None]:
    """The value of a date field whose text is `text`, and the problem with it, if any."""
    match = DATE_TEXT.fullmatch(text)
    if match is None:
        return text, "the value is not a date; it is kept as text"
    try:
        year, month, day = (int(part) for part in match.groups())
        if month == 0 and day == 0:
            return text, None
        return datetime.date(year, month, day), None
    except ValueError:
        return text, "the value is not a valid date; it is kept as text"


def parse_time(text: str) -> tuple[FieldValue, str | None]:
    """The value of a time field whose text is `text`, and the problem with it, if any."""
    match = TIME_TEXT.fullmatch(text)
    if match is None:
        return text, "the value is not a time; it is kept as text"
    try:
        return datetime.time(int(match[1]), int(match[2])), None
    except ValueError:
        return text, "the value is not a valid time; it is kept as text"


def record_number(text: str) -> int | None:
    """The record number `text` holds when it is ASCII decimal digits that make a number, else None."""
    if not ASCII_DIGITS.fullmatch(text):
        return None
    try:
        return int(text)
    except ValueError:
        return None


def convert_field(definition: FieldDefinition, decoded: DecodedField) -> tuple[Field, str | None]:
    """The public Field for the field `decoded` described by `definition`, and the problem with its value, if any."""
    raw = cast(bytes, decoded.data)
    text = cast(str, decoded.content)
    if not raw:
        return Field(definition, None, "", b""), None
    if definition.type == FIELD_TYPE_DATE:
        value, problem = parse_date(text)
    elif definition.type == FIELD_TYPE_TIME:
        value, problem = parse_time(text)
    elif definition.type == FIELD_TYPE_FILE:
        value = FileReference(decoded.filename, decoded.extname, record_number(decoded.filedatarecord))
        problem = None
    else:
        value, problem = text, None
    return Field(definition, value, text, raw), problem


def decode_record(
    number: int,
    table: str,
    definitions: Sequence[FieldDefinition],
    fielddefs: Sequence[DecodedFieldDefinition],
    data: bytes,
) -> Record:
    """
    Decode CroBank record `number` of the table named `table` from `data`, the record after its table id byte.

    `fielddefs` are the table's Datamodel field definitions, which `definitions` describe one for one; the first
    is the system number. A field that cannot be decoded is left empty, as are the fields after it, and reported
    as undecodable_field; a date or time that does not parse is reported as invalid_value.
    """
    decoded = DecodedRecord(number, list(fielddefs), data)
    diagnostics = [
        Diagnostic(
            DiagnosticKind.UNDECODABLE_FIELD,
            f"the field could not be decoded ({error}) and is left empty",
            file=BANK_FILE,
            table=table,
            record=number,
            field=name,
        )
        for name, error in decoded.errors
    ]
    system_number = decoded.fields[0].content
    fields = [Field(definitions[0], system_number, system_number, b"")]
    for definition, decoded_field in zip(definitions[1:], decoded.fields[1:], strict=True):
        field, problem = convert_field(definition, decoded_field)
        fields.append(field)
        if problem is not None:
            diagnostics.append(
                Diagnostic(
                    DiagnosticKind.INVALID_VALUE,
                    problem,
                    file=BANK_FILE,
                    table=table,
                    record=number,
                    field=definition.name,
                )
            )
    return Record(number, tuple(fields), tuple(diagnostics))
```

`Datamodel.Record.errors` messages come from `describe_error`, which names the exception type and message; they hold no record bytes. Check that `Datamodel.Record.decode` passes `str(recno)` as the system number's data and that its field errors hold no data; if either differs, stop and report.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_api_values.py`
Expected: all pass.

- [ ] **Step 5: Run the suite and linters, then commit**

```bash
fail() { echo "STOPPED: $*"; exit 1; }
uv run pytest -q > /tmp/t7-pytest.txt 2>&1 || fail pytest
uv run ruff check > /tmp/t7-ruff.txt 2>&1 || fail ruff
uv run ruff format --check > /tmp/t7-format.txt 2>&1 || fail format
uv run ty check > /tmp/t7-ty.txt 2>&1 || fail ty
git add src/cronos_extract/_api/values.py tests/test_api_values.py
git commit -F - <<'EOF' || fail commit
Decode records into the API's fields and typed values

A field has a value, its display text and its raw bytes. Dates and
times parse to datetime values, a year-only date stays text, a value
that does not parse stays text with an invalid_value diagnostic, and
an undecodable field becomes an undecodable_field diagnostic.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 8: Finding and opening a database's Cro file pairs

Spec: P3 (exceptions, `unreadable_file`), P12 "Opening and errors", Hostile input.

**Files:**
- Create: `src/cronos_extract/_api/datafiles.py`, `tests/test_api_datafiles.py`

**Interfaces:**
- Consumes: Task 2's `open_regular_file`, `Datafile(..., warn=...)`; Task 3's diagnostics and errors; Task 4's `Kod`, `kod_coder`; Task 5's `FileInfo`, `info_from_header`, `info_from_problem`, `read_file_info`.
- Produces, in `cronos_extract._api.datafiles`:
  - `database_directory(path: str | os.PathLike[str]) -> Path` — `TypeError` for `bytes`.
  - `list_directory(directory: Path) -> list[str]` — sorted names; `OSError` propagates.
  - `warn_into(log: DiagnosticLog, filename: str, prefix: str = "") -> Callable[[str], None]`
  - `open_datafile(directory: Path, names: list[str], base: str, *, compact: bool, kod: Kod | None, log: DiagnosticLog) -> tuple[Datafile, FileInfo]` — raises `NotACronosFile` or `UnsupportedVersion`.
  - `optional_file_info(directory: Path, names: list[str], base: str, log: DiagnosticLog) -> FileInfo | None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_datafiles.py`:

```python
# ABOUTME: Tests for finding a database's Cro file pairs and opening them, including hostile file systems.
# ABOUTME: Uses databases from tests/cronos_builder.py with FIFOs, sockets, symlinks and broken headers put in place.
import os
import socket
from pathlib import Path

import pytest
from cronos_builder import write_database, write_header_only_datafile

from cronos_extract._api.datafiles import (
    database_directory,
    list_directory,
    open_datafile,
    optional_file_info,
    warn_into,
)
from cronos_extract._api.diagnostics import Diagnostic, DiagnosticKind, DiagnosticLog
from cronos_extract._api.errors import NotACronosFile, UnsupportedVersion
from cronos_extract._format.files import NotARegularFile


def built(tmp_path: Path, version: bytes = b"01.04", index_records: list[bytes | None] | None = None) -> Path:
    return Path(write_database(tmp_path / "db", [], version=version, index_records=index_records))


def open_stru(directory: Path, log: DiagnosticLog | None = None):
    return open_datafile(
        directory, list_directory(directory), "Stru", compact=False, kod=None, log=log or DiagnosticLog(None)
    )


def test_a_pair_opens_as_a_datafile_with_its_file_info(tmp_path: Path) -> None:
    dbdir = built(tmp_path)

    datafile, info = open_stru(dbdir)
    datafile.close()

    assert (datafile.name, datafile.version) == ("Stru", b"01.04")
    assert (info.name, info.path, info.version, info.problem) == ("Stru", dbdir / "CroStru.dat", "01.04", None)


def test_file_names_match_case_insensitively(tmp_path: Path) -> None:
    dbdir = built(tmp_path)
    (dbdir / "CroStru.dat").rename(dbdir / "crostru.DAT")

    datafile, info = open_stru(dbdir)
    datafile.close()

    assert (info.name, info.path) == ("stru", dbdir / "crostru.DAT")


def test_two_names_differing_only_in_case_use_the_first_sorted_and_report_the_other(tmp_path: Path) -> None:
    dbdir = built(tmp_path)
    (dbdir / "CROSTRU.DAT").write_bytes((dbdir / "CroStru.dat").read_bytes())
    log = DiagnosticLog(None)

    datafile, info = open_stru(dbdir, log)
    datafile.close()

    assert info.path == dbdir / "CROSTRU.DAT"
    (diagnostic,) = log.kept
    assert (diagnostic.kind, diagnostic.file) == (DiagnosticKind.UNEXPECTED_STRUCTURE, "CroStru.dat")
    assert "reading CROSTRU.DAT" in diagnostic.message


def test_a_missing_pair_is_not_a_cronos_file(tmp_path: Path) -> None:
    with pytest.raises(NotACronosFile, match=r"has no CroStru\.dat and CroStru\.tad"):
        open_stru(tmp_path)


def test_a_dat_without_its_tad_is_not_a_cronos_file(tmp_path: Path) -> None:
    dbdir = built(tmp_path)
    (dbdir / "CroStru.tad").unlink()

    with pytest.raises(NotACronosFile, match=r"has CroStru\.dat but no CroStru\.tad"):
        open_stru(dbdir)


def test_a_tad_without_its_dat_is_not_a_cronos_file(tmp_path: Path) -> None:
    dbdir = built(tmp_path)
    (dbdir / "CroStru.dat").unlink()

    with pytest.raises(NotACronosFile, match=r"has CroStru\.tad but no CroStru\.dat"):
        open_stru(dbdir)


def test_a_fifo_is_not_a_cronos_file(tmp_path: Path) -> None:
    dbdir = built(tmp_path)
    (dbdir / "CroStru.dat").unlink()
    os.mkfifo(dbdir / "CroStru.dat")

    with pytest.raises(NotACronosFile, match="is not a regular file") as raised:
        open_stru(dbdir)

    assert isinstance(raised.value.__cause__, NotARegularFile)


def test_a_directory_named_like_a_cro_file_is_not_a_cronos_file(tmp_path: Path) -> None:
    dbdir = built(tmp_path)
    (dbdir / "CroStru.tad").unlink()
    (dbdir / "CroStru.tad").mkdir()

    with pytest.raises(NotACronosFile, match="is not a regular file"):
        open_stru(dbdir)


def test_a_socket_is_not_a_cronos_file(tmp_path: Path) -> None:
    dbdir = built(tmp_path)
    (dbdir / "CroStru.tad").unlink()
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(str(dbdir / "CroStru.tad"))

        with pytest.raises(NotACronosFile, match="cannot be opened") as raised:
            open_stru(dbdir)

    assert isinstance(raised.value.__cause__, OSError)


def test_a_dangling_symlink_is_not_a_cronos_file(tmp_path: Path) -> None:
    dbdir = built(tmp_path)
    (dbdir / "CroStru.dat").unlink()
    (dbdir / "CroStru.dat").symlink_to(tmp_path / "missing")

    with pytest.raises(NotACronosFile, match="cannot be opened") as raised:
        open_stru(dbdir)

    assert isinstance(raised.value.__cause__, FileNotFoundError)


@pytest.mark.parametrize(
    ("content", "message"),
    [(b"CroFile\x00", "shorter than its 19-byte header"), (b"NotACronosFile" + bytes(20), "not a Cronos file")],
)
def test_a_broken_header_is_not_a_cronos_file(tmp_path: Path, content: bytes, message: str) -> None:
    dbdir = built(tmp_path)
    (dbdir / "CroStru.dat").write_bytes(content)

    with pytest.raises(NotACronosFile, match=message):
        open_stru(dbdir)


@pytest.mark.parametrize(("version", "generation"), [(b"01.19", "v7"), (b"09.99", "unknown")])
def test_a_version_that_is_not_v3_or_v4_is_unsupported(tmp_path: Path, version: bytes, generation: str) -> None:
    dbdir = built(tmp_path)
    write_header_only_datafile(dbdir, "Stru", version=version)

    with pytest.raises(UnsupportedVersion, match=rf"version {version.decode()} \({generation}\)"):
        open_stru(dbdir)


@pytest.mark.parametrize(("version", "header_size"), [(b"01.04", 8), (b"01.11", 16)])
def test_a_tad_shorter_than_its_header_is_not_a_cronos_file(tmp_path: Path, version: bytes, header_size: int) -> None:
    dbdir = built(tmp_path, version=version)
    (dbdir / "CroStru.tad").write_bytes(bytes(header_size - 1))

    with pytest.raises(NotACronosFile, match=rf"CroStru\.tad in .* is shorter than its {header_size}-byte header"):
        open_stru(dbdir)


def test_leftover_tad_bytes_are_an_unexpected_structure_diagnostic(tmp_path: Path) -> None:
    dbdir = built(tmp_path)
    with (dbdir / "CroStru.tad").open("ab") as tad:
        tad.write(b"\x00")
    log = DiagnosticLog(None)

    datafile, _ = open_stru(dbdir, log)
    datafile.close()

    assert list(log.kept) == [
        Diagnostic(DiagnosticKind.UNEXPECTED_STRUCTURE, "leftover data in .tad", file="CroStru.dat")
    ]


def test_warn_into_strips_the_printed_prefix_and_adds_its_own() -> None:
    log = DiagnosticLog(None)

    warn_into(log, "CroStru.dat", prefix="Base001: ")("Warning: FieldDefinition section not terminated")
    warn_into(log, "CroStru.dat")("WARN: expected dbinfo to start with 0x03")

    assert [diagnostic.message for diagnostic in log.kept] == [
        "Base001: FieldDefinition section not terminated",
        "expected dbinfo to start with 0x03",
    ]


def test_an_optional_file_that_is_absent_has_no_info(tmp_path: Path) -> None:
    dbdir = built(tmp_path)
    log = DiagnosticLog(None)

    assert optional_file_info(dbdir, list_directory(dbdir), "Index", log) is None
    assert list(log.kept) == []


def test_a_readable_optional_file_has_info_even_when_it_is_v7(tmp_path: Path) -> None:
    dbdir = built(tmp_path)
    write_header_only_datafile(dbdir, "Index")
    (dbdir / "CroIndex.tad").write_bytes(bytes(8))
    log = DiagnosticLog(None)

    info = optional_file_info(dbdir, list_directory(dbdir), "Index", log)

    assert info is not None
    assert (info.generation, info.problem) == ("v7", None)
    assert list(log.kept) == []


@pytest.mark.parametrize("hazard", ["garbage", "fifo", "dangling", "no-tad", "no-dat"])
def test_an_unreadable_optional_file_is_reported_as_unreadable(tmp_path: Path, hazard: str) -> None:
    dbdir = built(tmp_path, index_records=[])
    if hazard == "garbage":
        (dbdir / "CroIndex.dat").write_bytes(b"garbage")
    elif hazard == "fifo":
        (dbdir / "CroIndex.dat").unlink()
        os.mkfifo(dbdir / "CroIndex.dat")
    elif hazard == "dangling":
        (dbdir / "CroIndex.dat").unlink()
        (dbdir / "CroIndex.dat").symlink_to(tmp_path / "missing")
    elif hazard == "no-tad":
        (dbdir / "CroIndex.tad").unlink()
    else:
        (dbdir / "CroIndex.dat").unlink()
    log = DiagnosticLog(None)

    info = optional_file_info(dbdir, list_directory(dbdir), "Index", log)

    assert info is not None
    assert info.problem is not None
    (diagnostic,) = log.kept
    assert (diagnostic.kind, diagnostic.file, diagnostic.message) == (
        DiagnosticKind.UNREADABLE_FILE,
        "CroIndex.dat",
        info.problem,
    )


def test_a_bytes_path_is_refused() -> None:
    with pytest.raises(TypeError, match="not bytes"):
        database_directory(b"/some/database")  # ty: ignore[invalid-argument-type]


def test_listing_a_file_raises_not_a_directory(tmp_path: Path) -> None:
    (tmp_path / "file").write_bytes(b"")

    with pytest.raises(NotADirectoryError):
        list_directory(tmp_path / "file")


def test_listing_a_missing_directory_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        list_directory(tmp_path / "missing")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/test_api_datafiles.py`
Expected: collection fails with `ModuleNotFoundError: No module named 'cronos_extract._api.datafiles'`.

- [ ] **Step 3: Implement**

Create `src/cronos_extract/_api/datafiles.py`:

```python
# ABOUTME: Finds a database's Cro*.dat and Cro*.tad pairs by case-insensitive name and opens them as Datafiles.
# ABOUTME: A missing, unopenable, non-Cronos or unsupported CroStru or CroBank raises; CroIndex and CroSys are reported.
import os
import re
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path

from .._format.files import open_regular_file
from .._format.header import read_dat_header
from ..Datafile import Datafile
from .diagnostics import Diagnostic, DiagnosticKind, DiagnosticLog
from .errors import NotACronosFile, UnsupportedVersion
from .info import FileInfo, info_from_header, info_from_problem, read_file_info
from .kod import Kod, kod_coder

# The size of a .tad file's header for each generation the readers support.
TAD_HEADER_SIZES = {"v3": 8, "v4": 16}
# The prefixes the internal readers put before a warning they print.
WARNING_PREFIX = re.compile(r"^(?:WARN|Warning): ")


def database_directory(path: str | os.PathLike[str]) -> Path:
    """`path` as a Path. Raises TypeError for bytes, whose directory listing would hold bytes names that never match."""
    location = os.fspath(path)
    if not isinstance(location, str):
        raise TypeError(f"a database path must be str or os.PathLike[str], not bytes: {location!r}")
    return Path(location)


def list_directory(directory: Path) -> list[str]:
    """The names in `directory`, sorted. OSError propagates, including NotADirectoryError for a file."""
    return sorted(os.listdir(directory))


def warn_into(log: DiagnosticLog, filename: str, prefix: str = "") -> Callable[[str], None]:
    """A warn hook for the internal readers that records each warning about `filename` as unexpected_structure."""

    def warn(message: str) -> None:
        log.record(
            Diagnostic(
                DiagnosticKind.UNEXPECTED_STRUCTURE, prefix + WARNING_PREFIX.sub("", message, count=1), file=filename
            )
        )

    return warn


def find_file(directory: Path, names: list[str], filename: str, log: DiagnosticLog) -> Path | None:
    """
    The path of `filename` among `names`, matched case-insensitively, or None.

    When several names match, the first in sorted order is used and an unexpected_structure diagnostic names it.
    """
    matches = [name for name in names if name.lower() == filename.lower()]
    if not matches:
        return None
    if len(matches) > 1:
        log.record(
            Diagnostic(
                DiagnosticKind.UNEXPECTED_STRUCTURE,
                f"{directory} holds {len(matches)} files named {filename} in different cases; reading {matches[0]}",
                file=filename,
            )
        )
    return directory / matches[0]


def missing_pair_message(
    directory: Path, datname: str, tadname: str, datpath: Path | None, tadpath: Path | None
) -> str:
    """Say which of the `datname` and `tadname` pair `directory` lacks, given the paths found for each."""
    if datpath is not None:
        return f"{directory} has {datname} but no {tadname}"
    if tadpath is not None:
        return f"{directory} has {tadname} but no {datname}"
    return f"{directory} has no {datname} and {tadname}"


def open_datafile(
    directory: Path, names: list[str], base: str, *, compact: bool, kod: Kod | None, log: DiagnosticLog
) -> tuple[Datafile, FileInfo]:
    """
    Open the Cro<base>.dat and Cro<base>.tad pair in `directory`, listed as `names`, as a Datafile with its FileInfo.

    Raises NotACronosFile when the pair is incomplete, a file is not a regular file or cannot be opened, the .dat
    header is short or has an unknown magic, or the .tad is shorter than its header; UnsupportedVersion when the
    version is neither v3 nor v4. Warnings from the Datafile are recorded in `log`.
    """
    datname, tadname = f"Cro{base}.dat", f"Cro{base}.tad"
    datpath = find_file(directory, names, datname, log)
    tadpath = find_file(directory, names, tadname, log)
    if datpath is None or tadpath is None:
        raise NotACronosFile(missing_pair_message(directory, datname, tadname, datpath, tadpath))
    with ExitStack() as stack:
        try:
            dat = stack.enter_context(open_regular_file(datpath))
            tad = stack.enter_context(open_regular_file(tadpath))
        except OSError as e:
            raise NotACronosFile(f"{datname} or {tadname} in {directory} cannot be opened: {e}") from e
        try:
            header = read_dat_header(dat, where=datname)
        except ValueError as e:
            raise NotACronosFile(f"{e}, in {directory}") from e
        tad_header_size = TAD_HEADER_SIZES.get(header.generation)
        if tad_header_size is None:
            raise UnsupportedVersion(
                f"{datname} in {directory} is CronosPro version {header.version_text} ({header.generation}), "
                "which this release cannot read"
            )
        if os.fstat(tad.fileno()).st_size < tad_header_size:
            raise NotACronosFile(f"{tadname} in {directory} is shorter than its {tad_header_size}-byte header")
        datafile = Datafile(base, dat, tad, compact, kod_coder(kod), warn_into(log, datname))
        stack.pop_all()
    return datafile, info_from_header(datpath.name[3:-4], datpath, header)


def optional_file_info(directory: Path, names: list[str], base: str, log: DiagnosticLog) -> FileInfo | None:
    """
    The FileInfo of Cro<base>.dat, a file reading tables does not need, or None when neither it nor its .tad exists.

    A pair with a half missing, or a header that cannot be read, gives a FileInfo with a problem, which is also
    recorded in `log` as unreadable_file.
    """
    datname, tadname = f"Cro{base}.dat", f"Cro{base}.tad"
    datpath = find_file(directory, names, datname, log)
    tadpath = find_file(directory, names, tadname, log)
    if datpath is None and tadpath is None:
        return None
    if datpath is None or tadpath is None:
        problem = missing_pair_message(directory, datname, tadname, datpath, tadpath)
        info = info_from_problem(
            base if datpath is None else datpath.name[3:-4], datpath or directory / datname, problem
        )
    else:
        info = read_file_info(datpath.name[3:-4], datpath)
    if info.problem is not None:
        log.record(Diagnostic(DiagnosticKind.UNREADABLE_FILE, info.problem, file=datname))
    return info
```

The `NotARegularFile` message is "CroStru.dat is not a regular file", so `test_a_fifo_is_not_a_cronos_file` matches the text of the chained error inside "cannot be opened: CroStru.dat is not a regular file".

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_api_datafiles.py`
Expected: all pass.

- [ ] **Step 5: Run the suite and linters, then commit**

```bash
fail() { echo "STOPPED: $*"; exit 1; }
uv run pytest -q > /tmp/t8-pytest.txt 2>&1 || fail pytest
uv run ruff check > /tmp/t8-ruff.txt 2>&1 || fail ruff
uv run ruff format --check > /tmp/t8-format.txt 2>&1 || fail format
uv run ty check > /tmp/t8-ty.txt 2>&1 || fail ty
git add src/cronos_extract/_api/datafiles.py tests/test_api_datafiles.py
git commit -F - <<'EOF' || fail commit
Find and open a database's Cro file pairs for the API

Pairs are matched case-insensitively and opened as regular files only.
A missing, unopenable, non-Cronos or unsupported CroStru or CroBank
raises NotACronosFile or UnsupportedVersion; an unreadable CroIndex or
CroSys is reported as unreadable_file.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---
### Task 9: `open()`, `Bank` and `Table`

Spec: P3, P6 (what `open()` reads), P8 (`Table`), P12 (`unused_kod`, table warnings, `abbreviation`, `files_abbreviation`, closing), Architecture "What `open()` does".

**Files:**
- Create: `src/cronos_extract/_api/bank.py`, `tests/test_api_open.py`

**Interfaces:**
- Consumes: Task 2's `Database.from_datafiles`, `TableDefinition(..., warn=...)`; Task 3; Task 4's `Kod`, `kod_coder`; Task 5's `FileInfo`; Task 7's `FieldDefinition`; Task 8's `database_directory`, `list_directory`, `open_datafile`, `optional_file_info`, `warn_into`.
- Produces, in `cronos_extract._api.bank`:
  - `DEFAULT_KOD: Kod`
  - `open(path: str | os.PathLike[str], *, kod: Kod | None = DEFAULT_KOD, compact: bool = False, on_diagnostic: Callable[[Diagnostic], object] | None = None) -> Bank`
  - `Bank`: properties `tables: tuple[Table, ...]`, `info: tuple[FileInfo, ...]`, `diagnostics: Sequence[Diagnostic]`, `diagnostic_counts: Mapping[DiagnosticKind, int]`, `files_abbreviation: str | None`; `close() -> None` (idempotent); context manager; `_check_open() -> None` raising `ValueError`. Task 10 adds `_read`, `_records`, `files`, `read_file`.
  - `Table`: properties `id: int`, `name: str`, `abbreviation: str`, `fields: tuple[FieldDefinition, ...]`; `records() -> Iterator[Record]` (Task 10 implements the iteration).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_open.py`:

```python
# ABOUTME: Tests for cronos_extract's open(): what it raises, the tables and file information it reads, and diagnostics.
# ABOUTME: Uses real databases from tests/cronos_builder.py, and checks that opening prints nothing.
import os
from pathlib import Path

import pytest
from cronos_builder import (
    database_with_extra_definition_key,
    database_with_missing_definition,
    database_with_wrong_kod_record_out_of_range,
    patched_table_definition,
    random_kod,
    stru_records_from_test_db,
    table_definition_without_fields,
    write_database,
)

from cronos_extract._api.bank import Bank
from cronos_extract._api.bank import open as open_bank
from cronos_extract._api.diagnostics import Diagnostic, DiagnosticKind
from cronos_extract._api.errors import DatabaseDefinitionError, NotACronosFile, UnsupportedVersion
from cronos_extract._api.kod import Kod
from cronos_extract._api.values import FieldDefinition
from cronos_extract.koddecoder import INITIAL_KOD

SECTION_2_WARNINGS = [
    Diagnostic(
        DiagnosticKind.UNEXPECTED_STRUCTURE,
        f"{key}: FieldDefinition Section 2 not marked with a 2",
        file="CroStru.dat",
    )
    for key in ("Base000", "Base001")
]


@pytest.fixture(autouse=True)
def prints_nothing(capfd: pytest.CaptureFixture[str]):
    yield
    captured = capfd.readouterr()
    assert (captured.out, captured.err) == ("", "")


def kinds(bank: Bank) -> list[DiagnosticKind]:
    return [diagnostic.kind for diagnostic in bank.diagnostics]


def test_open_reads_the_tables_of_a_database(tmp_path: Path) -> None:
    with open_bank(write_database(tmp_path / "db", [])) as bank:
        (table,) = bank.tables
        assert (table.id, table.name, table.abbreviation) == (1, "erdgeist", "ER")
        assert table.fields[0] == FieldDefinition("Системный номер", 0)
        assert table.fields[4] == FieldDefinition("Entry #4", 4)
        assert len(table.fields) == 12
        assert bank.files_abbreviation == "FL"


def test_open_reports_the_section_2_warning_of_each_table_definition(tmp_path: Path) -> None:
    with open_bank(write_database(tmp_path / "db", [])) as bank:
        assert list(bank.diagnostics) == SECTION_2_WARNINGS
        assert dict(bank.diagnostic_counts) == {DiagnosticKind.UNEXPECTED_STRUCTURE: 2}


def test_open_accepts_a_path_object(tmp_path: Path) -> None:
    with open_bank(Path(write_database(tmp_path / "db", []))) as bank:
        assert [table.name for table in bank.tables] == ["erdgeist"]


def test_bank_info_lists_the_files_found_in_order(tmp_path: Path) -> None:
    dbdir = Path(write_database(tmp_path / "db", [], index_records=[]))

    with open_bank(dbdir) as bank:
        assert [(info.name, info.path, info.version, info.problem) for info in bank.info] == [
            ("Stru", dbdir / "CroStru.dat", "01.04", None),
            ("Bank", dbdir / "CroBank.dat", "01.04", None),
            ("Index", dbdir / "CroIndex.dat", "01.04", None),
        ]


@pytest.mark.parametrize("version", [b"01.02", b"01.03", b"01.04", b"01.05", b"01.11"])
def test_open_reads_every_version_the_builder_writes(tmp_path: Path, version: bytes) -> None:
    with open_bank(write_database(tmp_path / "db", [], version=version)) as bank:
        assert [table.name for table in bank.tables] == ["erdgeist"]
        assert bank.info[0].version == version.decode()


def test_an_unreadable_index_is_reported_and_reading_goes_on(tmp_path: Path) -> None:
    dbdir = Path(write_database(tmp_path / "db", [], index_records=[]))
    (dbdir / "CroIndex.dat").write_bytes(b"NotACronosFile" + bytes(20))

    with open_bank(dbdir) as bank:
        assert [table.name for table in bank.tables] == ["erdgeist"]
        assert bank.info[2].problem is not None
        assert kinds(bank) == [DiagnosticKind.UNREADABLE_FILE, *(d.kind for d in SECTION_2_WARNINGS)]


def test_a_directory_name_that_is_not_valid_utf8_opens(tmp_path: Path) -> None:
    dbdir = tmp_path / os.fsdecode(b"db-\xff\xfe")
    write_database(dbdir, [])

    with open_bank(dbdir) as bank:
        assert [table.name for table in bank.tables] == ["erdgeist"]
        assert bank.info[0].path == dbdir / "CroStru.dat"


def test_a_missing_directory_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        open_bank(tmp_path / "missing")


def test_a_file_path_raises_not_a_directory(tmp_path: Path) -> None:
    (tmp_path / "file").write_bytes(b"")

    with pytest.raises(NotADirectoryError):
        open_bank(tmp_path / "file")


def test_a_bytes_path_raises_type_error(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        open_bank(bytes(tmp_path))  # ty: ignore[invalid-argument-type]


def test_a_directory_without_a_bank_is_not_a_cronos_file(tmp_path: Path) -> None:
    dbdir = Path(write_database(tmp_path / "db", []))
    (dbdir / "CroBank.dat").unlink()
    (dbdir / "CroBank.tad").unlink()

    with pytest.raises(NotACronosFile, match=r"no CroBank\.dat and CroBank\.tad"):
        open_bank(dbdir)


def test_a_v7_bank_is_unsupported(tmp_path: Path) -> None:
    dbdir = Path(write_database(tmp_path / "db", []))
    data = bytearray((dbdir / "CroBank.dat").read_bytes())
    data[10:15] = b"01.19"
    (dbdir / "CroBank.dat").write_bytes(bytes(data))

    with pytest.raises(UnsupportedVersion, match=r"01\.19 \(v7\)"):
        open_bank(dbdir)


def test_a_database_without_records_in_stru_has_no_definition(tmp_path: Path) -> None:
    dbdir = database_with_missing_definition(tmp_path / "db", [])

    with pytest.raises(DatabaseDefinitionError, match=r"holds no records.*cronos_extract\.crack_kod"):
        open_bank(dbdir)


def test_a_deleted_definition_record_is_a_definition_error(tmp_path: Path) -> None:
    dbdir = database_with_missing_definition(tmp_path / "db", [None, *stru_records_from_test_db()[1:]])

    with pytest.raises(DatabaseDefinitionError, match="is deleted"):
        open_bank(dbdir)


def test_a_wrong_kod_is_a_definition_error(tmp_path: Path) -> None:
    dbdir, wrong_kod_hex = database_with_wrong_kod_record_out_of_range(tmp_path / "db")

    with pytest.raises(DatabaseDefinitionError, match="does not hold"):
        open_bank(dbdir, kod=Kod.from_hex(wrong_kod_hex))


def test_a_table_definition_that_cannot_be_decoded_is_left_out(tmp_path: Path) -> None:
    dbdir = database_with_extra_definition_key(tmp_path / "db", "Base002", b"\x00")

    with open_bank(dbdir) as bank:
        assert [table.name for table in bank.tables] == ["erdgeist"]
        (diagnostic,) = [d for d in bank.diagnostics if d.kind == DiagnosticKind.UNDECODABLE_TABLE]
        assert (diagnostic.file, diagnostic.message.startswith("Base002 cannot be decoded")) == ("CroStru.dat", True)


def test_a_table_without_the_system_number_field_is_left_out(tmp_path: Path) -> None:
    dbdir = database_with_extra_definition_key(tmp_path / "db", "Base002", table_definition_without_fields(tableid=2))

    with open_bank(dbdir) as bank:
        assert [table.id for table in bank.tables] == [1]
        (diagnostic,) = [d for d in bank.diagnostics if d.kind == DiagnosticKind.UNDECODABLE_TABLE]
        assert (diagnostic.table, diagnostic.message) == (
            "erdgeist",
            "Base002 is left out: it does not start with the system number field",
        )


def test_a_table_with_an_id_above_255_is_kept(tmp_path: Path) -> None:
    dbdir = database_with_extra_definition_key(tmp_path / "db", "Base002", patched_table_definition(tableid=300))

    with open_bank(dbdir) as bank:
        assert [table.id for table in bank.tables] == [1, 300]


def test_a_duplicate_definition_key_is_an_unexpected_structure(tmp_path: Path) -> None:
    dbdir = database_with_extra_definition_key(tmp_path / "db", "BankName", b"again")

    with open_bank(dbdir) as bank:
        assert Diagnostic(DiagnosticKind.UNEXPECTED_STRUCTURE, "duplicate key: BankName", file="CroStru.dat") in list(
            bank.diagnostics
        )


@pytest.mark.parametrize(
    ("version", "written_with", "opened_with", "reported"),
    [
        (b"01.04", None, Kod.from_table(random_kod(seed=1)), True),
        (b"01.02", None, Kod.from_table(random_kod(seed=1)), True),
        (b"01.04", random_kod(seed=1), Kod.from_table(random_kod(seed=1)), False),
        (b"01.04", None, Kod.from_table(INITIAL_KOD), False),
        (b"01.04", None, None, False),
    ],
    ids=["unencoded-own-kod-version", "default-kod-version", "encoded-with-it", "default-table", "no-kod"],
)
def test_a_kod_that_no_file_uses_is_reported(
    tmp_path: Path, version: bytes, written_with: list[int] | None, opened_with: Kod | None, reported: bool
) -> None:
    dbdir = write_database(tmp_path / "db", [], written_with, version=version)

    with open_bank(dbdir, kod=opened_with) as bank:
        assert (DiagnosticKind.UNUSED_KOD in kinds(bank)) is reported


def test_an_exception_from_on_diagnostic_during_open_reaches_the_caller(tmp_path: Path) -> None:
    class StopReading(Exception):
        pass

    def on_diagnostic(diagnostic: Diagnostic) -> None:
        raise StopReading

    with pytest.raises(StopReading):
        open_bank(write_database(tmp_path / "db", []), on_diagnostic=on_diagnostic)


def test_on_diagnostic_receives_the_diagnostics_of_open(tmp_path: Path) -> None:
    seen: list[Diagnostic] = []

    with open_bank(write_database(tmp_path / "db", []), on_diagnostic=seen.append):
        assert seen == SECTION_2_WARNINGS


def test_closing_twice_is_harmless_and_a_closed_bank_refuses_to_read(tmp_path: Path) -> None:
    bank = open_bank(write_database(tmp_path / "db", []))
    table = bank.tables[0]

    bank.close()
    bank.close()

    with pytest.raises(ValueError, match="is closed"):
        table.records()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/test_api_open.py`
Expected: collection fails with `ModuleNotFoundError: No module named 'cronos_extract._api.bank'`.

- [ ] **Step 3: Implement**

Create `src/cronos_extract/_api/bank.py`:

```python
# ABOUTME: open() and the Bank and Table classes, the public way to read a CronosPro database.
# ABOUTME: Drives the internal Database, TableDefinition and Datafile readers and reports problems as diagnostics.
import os
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import ExitStack
from pathlib import Path
from types import TracebackType
from typing import Self, cast, override

from ..Database import Database
from ..Datamodel import TableDefinition, describe_error
from .datafiles import database_directory, list_directory, open_datafile, optional_file_info, warn_into
from .diagnostics import Diagnostic, DiagnosticKind, DiagnosticLog
from .errors import DatabaseDefinitionError
from .info import FileInfo
from .kod import Kod, kod_coder
from .values import FieldDefinition, Record

DEFAULT_KOD = Kod.default()
STRU_FILE = "CroStru.dat"
FIELD_TYPE_SYSTEM_NUMBER = 0
DEFINITION_HINT = (
    "If the KOD used to read this database is not its own, the definition decodes as garbage; "
    "cronos_extract.crack_kod can recover the database's KOD."
)


class Table:
    """A table of a bank: its id, names and field definitions, and its records, read lazily."""

    def __init__(self, bank: "Bank", definition: TableDefinition) -> None:
        self._bank = bank
        self._definition = definition
        self._fields = tuple(FieldDefinition(field.name, field.typ) for field in definition.fields)

    @property
    def id(self) -> int:
        """The table id, which the first byte of each of its CroBank records holds."""
        return int(self._definition.tableid)

    @property
    def name(self) -> str:
        return str(self._definition.tablename)

    @property
    def abbreviation(self) -> str:
        return str(self._definition.abbrev)

    @property
    def fields(self) -> tuple[FieldDefinition, ...]:
        """The field definitions; the first is the system number, and each describes the record field at its index."""
        return self._fields

    def records(self) -> Iterator[Record]:
        """
        The table's records in CroBank order, read one CroBank record per step.

        Raises ValueError when the bank is closed, now or at any later step.
        """
        self._bank._check_open()
        return self._bank._records(self)

    @override
    def __repr__(self) -> str:
        return f"Table(id={self.id}, name={self.name!r})"


class Bank:
    """
    An open CronosPro database. Close it, or use it as a context manager, to close its files.

    A Bank is not thread-safe. Generators from one bank may be interleaved on one thread.
    """

    def __init__(self, directory: Path, database: Database, info: tuple[FileInfo, ...], log: DiagnosticLog) -> None:
        self._directory = directory
        self._database = database
        self._info = info
        self._log = log
        self._closed = False
        self._tables: tuple[Table, ...] = ()
        self._files_table_id: int | None = None
        self._files_abbreviation: str | None = None

    @property
    def tables(self) -> tuple[Table, ...]:
        """The tables, in database-definition order, without the Files table."""
        return self._tables

    @property
    def info(self) -> tuple[FileInfo, ...]:
        """The Cro files found, in the order Stru, Bank, Index, Sys."""
        return self._info

    @property
    def diagnostics(self) -> Sequence[Diagnostic]:
        """The first 1,000 diagnostics, a read-only sequence that grows while reading."""
        return self._log.kept

    @property
    def diagnostic_counts(self) -> Mapping[DiagnosticKind, int]:
        """The number of diagnostics of each kind that occurred, counting every one."""
        return self._log.counts

    @property
    def files_abbreviation(self) -> str | None:
        """The Files table's abbreviation, or None when the database has no Files table."""
        return self._files_abbreviation

    def close(self) -> None:
        """Close the bank's files. Closing a closed bank does nothing."""
        if not self._closed:
            self._closed = True
            self._database.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        self.close()

    @override
    def __repr__(self) -> str:
        return f"Bank({str(self._directory)!r})"

    def _check_open(self) -> None:
        if self._closed:
            raise ValueError(f"the bank in {self._directory} is closed")

    def _records(self, table: Table) -> Iterator[Record]:
        raise NotImplementedError("Task 10 reads records")

    def _load_tables(self) -> None:
        """Decode the database definition and every table definition in it."""
        try:
            definition = self._database.read_db_definition()
        except OSError:
            raise
        except Exception as e:
            raise DatabaseDefinitionError(
                f"the database definition in {STRU_FILE} of {self._directory} cannot be decoded: "
                f"{describe_error(e)}. {DEFINITION_HINT}"
            ) from e
        tables = []
        for key, value in definition.items():
            if not (key.startswith("Base") and key[4:].isnumeric()):
                continue
            try:
                table_definition = TableDefinition(
                    value, definition.get("BaseImage" + key[4:], b""), warn_into(self._log, STRU_FILE, f"{key}: ")
                )
            except Exception as e:
                self._log.record(
                    Diagnostic(
                        DiagnosticKind.UNDECODABLE_TABLE,
                        f"{key} cannot be decoded and is left out: {describe_error(e)}",
                        file=STRU_FILE,
                    )
                )
                continue
            if key[4:] == "000":
                self._files_table_id = table_definition.tableid
                self._files_abbreviation = table_definition.abbrev
            elif not table_definition.fields or table_definition.fields[0].typ != FIELD_TYPE_SYSTEM_NUMBER:
                self._log.record(
                    Diagnostic(
                        DiagnosticKind.UNDECODABLE_TABLE,
                        f"{key} is left out: it does not start with the system number field",
                        file=STRU_FILE,
                        table=table_definition.tablename,
                    )
                )
            else:
                tables.append(Table(self, table_definition))
        self._tables = tuple(tables)


def open(
    path: str | os.PathLike[str],
    *,
    kod: Kod | None = DEFAULT_KOD,
    compact: bool = False,
    on_diagnostic: Callable[[Diagnostic], object] | None = None,
) -> Bank:
    """
    Open the CronosPro database in the directory `path`.

    `kod` is the KOD table to decode records with, or None to read them without KOD decoding. `compact` reads the
    CroStru and CroBank indexes from disk instead of memory. `on_diagnostic` is called with each diagnostic as it is
    recorded.

    Raises OSError when `path` does not exist, is not a directory or cannot be listed; TypeError for a bytes path;
    NotACronosFile or UnsupportedVersion when CroStru or CroBank cannot be read; DatabaseDefinitionError when the
    database definition cannot be decoded.
    """
    directory = database_directory(path)
    names = list_directory(directory)
    log = DiagnosticLog(on_diagnostic)
    with ExitStack() as stack:
        stru, stru_info = open_datafile(directory, names, "Stru", compact=compact, kod=kod, log=log)
        stack.callback(stru.close)
        bank_file, bank_info = open_datafile(directory, names, "Bank", compact=compact, kod=kod, log=log)
        stack.callback(bank_file.close)
        optional = [optional_file_info(directory, names, base, log) for base in ("Index", "Sys")]
        if (
            kod is not None
            and kod != DEFAULT_KOD
            and not any(info.own_kod and info.kod_encoded for info in (stru_info, bank_info))
        ):
            log.record(
                Diagnostic(
                    DiagnosticKind.UNUSED_KOD,
                    "the KOD given is not used: neither CroStru.dat nor CroBank.dat is encrypted with its own KOD",
                )
            )
        database = Database.from_datafiles(
            str(directory), compact, kod_coder(kod), stru, bank_file, warn_into(log, STRU_FILE)
        )
        bank = Bank(directory, database, (stru_info, bank_info, *(info for info in optional if info is not None)), log)
        bank._load_tables()
        stack.pop_all()
    return bank
```

`Bank._records` raises `NotImplementedError` in this task only; Task 10 replaces it. No test in this task iterates records.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_api_open.py`
Expected: all pass. If `test_a_wrong_kod_is_a_definition_error` or the deleted-definition test show a message other than the one matched, read the `ValueError` raised in `Database.read_db_definition` or `decode_db_definition` and match its actual words; do not loosen the match to `.*`.

- [ ] **Step 5: Run the suite and linters, then commit**

```bash
fail() { echo "STOPPED: $*"; exit 1; }
uv run pytest -q > /tmp/t9-pytest.txt 2>&1 || fail pytest
uv run ruff check > /tmp/t9-ruff.txt 2>&1 || fail ruff
uv run ruff format --check > /tmp/t9-format.txt 2>&1 || fail format
uv run ty check > /tmp/t9-ty.txt 2>&1 || fail ty
git add src/cronos_extract/_api/bank.py tests/test_api_open.py
git commit -F - <<'EOF' || fail commit
Open a database as a Bank with its tables

open() opens only CroStru and CroBank, reads the database definition
and every table definition, and reports what it survives as
diagnostics: warnings from the readers, undecodable tables, unreadable
CroIndex or CroSys files and a KOD that no file uses.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 10: Reading records and files

Spec: P3 (`corrupt_record`, `unresolved_file_reference`), P6, P8 (`unsupported_table`, `EmbeddedFile`), P9, P12 (closed bank, deduplication, bit set, no `Base000`), Hostile input (any exception reading one record), Testing (parity, cap).

**Files:**
- Modify: `src/cronos_extract/_api/bank.py`
- Create: `tests/test_api_bank.py`

**Interfaces:**
- Consumes: Task 9's `Bank`, `Table`; Task 7's `decode_record`, `EmbeddedFile`, `FileReference`; Task 3's `RecordNumbers`.
- Produces: `Bank.files() -> Iterator[EmbeddedFile]`; `Bank.read_file(reference: FileReference) -> EmbeddedFile | None`; `Table.records()` yields records.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_bank.py`:

```python
# ABOUTME: Tests for reading records and files through the cronos_extract API: laziness, diagnostics and closing.
# ABOUTME: Compares the API with Database.enumerate_records on every version tests/cronos_builder.py writes.
import datetime
from pathlib import Path

import pytest
from cronos_builder import (
    TEST_TABLE_FILE_FIELD_INDEX,
    TEST_TABLE_ID,
    bank_record,
    corrupt_compressed_record,
    database_with_extra_definition_key,
    database_without_files_table,
    file_record,
    file_reference_field,
    patched_table_definition,
    random_kod,
    write_database,
)

from cronos_extract._api.bank import Bank
from cronos_extract._api.bank import open as open_bank
from cronos_extract._api.diagnostics import DIAGNOSTICS_KEPT, Diagnostic, DiagnosticKind
from cronos_extract._api.kod import Kod
from cronos_extract._api.values import EmbeddedFile, FileReference
from cronos_extract.Database import Database
from cronos_extract.koddecoder import INITIAL_KOD, KODcoding

KOD = random_kod(seed=11)
FIELDS = [b"42", b"Hammersley", "Привет".encode("cp1251"), b"1240315", b"0930", b"", b"seven", b"", b"", b"", b"x"]


def person(*, date: bytes = b"1240315", file_field: bytes = b"") -> bytes:
    fields = list(FIELDS)
    fields[3] = date
    fields[TEST_TABLE_FILE_FIELD_INDEX] = file_field
    return bank_record(TEST_TABLE_ID, fields)


def counts(bank: Bank, kind: DiagnosticKind) -> int:
    return bank.diagnostic_counts.get(kind, 0)


@pytest.fixture
def prints_nothing(capfd: pytest.CaptureFixture[str]):
    yield
    captured = capfd.readouterr()
    assert (captured.out, captured.err) == ("", "")


@pytest.mark.usefixtures("prints_nothing")
def test_records_are_read_in_crobank_order_skipping_other_tables_and_deleted_records(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [person(), file_record(b"file"), None, person(date=b"850000")])

    with open_bank(dbdir) as bank:
        records = list(bank.tables[0].records())

    assert [record.number for record in records] == [1, 4]
    assert records[0]["Entry #4"].value == datetime.date(2024, 3, 15)
    assert records[1]["Entry #4"].value == "1985-00-00"
    assert records[0]["Entry #2"].text == "Hammersley"


@pytest.mark.usefixtures("prints_nothing")
def test_records_are_read_one_crobank_record_per_step(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [person(), corrupt_compressed_record(), person()])

    with open_bank(dbdir) as bank:
        records = bank.tables[0].records()
        assert next(records).number == 1
        assert counts(bank, DiagnosticKind.CORRUPT_RECORD) == 0
        assert next(records).number == 3
        assert counts(bank, DiagnosticKind.CORRUPT_RECORD) == 1


@pytest.mark.usefixtures("prints_nothing")
def test_a_corrupt_record_is_reported_once_however_many_tables_are_read(tmp_path: Path) -> None:
    dbdir = database_with_extra_definition_key(
        tmp_path / "db",
        "Base002",
        patched_table_definition(tableid=2),
        [person(), corrupt_compressed_record(), bank_record(2, FIELDS)],
    )

    with open_bank(dbdir) as bank:
        first, second = bank.tables
        assert [record.number for record in first.records()] == [1]
        assert [record.number for record in second.records()] == [3]
        assert [record.number for record in first.records()] == [1]
        corrupt = [d for d in bank.diagnostics if d.kind == DiagnosticKind.CORRUPT_RECORD]

    (diagnostic,) = corrupt
    assert (diagnostic.file, diagnostic.record, diagnostic.table, diagnostic.field) == ("CroBank.dat", 2, None, None)
    assert "CroBank record 2 is corrupt" in diagnostic.message


@pytest.mark.usefixtures("prints_nothing")
def test_record_diagnostics_are_recorded_each_time_a_record_is_decoded(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [person(date=b"851301")])

    with open_bank(dbdir) as bank:
        (record,) = bank.tables[0].records()
        list(bank.tables[0].records())

        assert [d.kind for d in record.diagnostics] == [DiagnosticKind.INVALID_VALUE]
        assert counts(bank, DiagnosticKind.INVALID_VALUE) == 2


@pytest.mark.usefixtures("prints_nothing")
def test_a_table_with_an_id_above_255_yields_nothing_and_is_reported_once(tmp_path: Path) -> None:
    dbdir = database_with_extra_definition_key(tmp_path / "db", "Base002", patched_table_definition(tableid=300))

    with open_bank(dbdir) as bank:
        table = bank.tables[1]
        assert list(table.records()) == []
        assert list(table.records()) == []
        (diagnostic,) = [d for d in bank.diagnostics if d.kind == DiagnosticKind.UNSUPPORTED_TABLE]

    assert (diagnostic.table, diagnostic.file) == ("erdgeist", "CroStru.dat")
    assert "255" in diagnostic.message


@pytest.mark.usefixtures("prints_nothing")
def test_the_bank_keeps_the_first_diagnostics_and_counts_them_all(tmp_path: Path) -> None:
    corrupt_records = DIAGNOSTICS_KEPT + 1
    dbdir = write_database(tmp_path / "db", [corrupt_compressed_record()] * corrupt_records)
    seen: list[Diagnostic] = []

    with open_bank(dbdir, on_diagnostic=seen.append) as bank:
        assert list(bank.tables[0].records()) == []

        assert len(bank.diagnostics) == DIAGNOSTICS_KEPT
        assert counts(bank, DiagnosticKind.CORRUPT_RECORD) == corrupt_records
        assert sum(bank.diagnostic_counts.values()) == corrupt_records + 2
        assert len(seen) == corrupt_records + 2


@pytest.mark.usefixtures("prints_nothing")
def test_an_exception_from_on_diagnostic_stops_reading_and_the_bank_still_closes(tmp_path: Path) -> None:
    class StopReading(Exception):
        pass

    def on_diagnostic(diagnostic: Diagnostic) -> None:
        if diagnostic.kind == DiagnosticKind.CORRUPT_RECORD:
            raise StopReading

    dbdir = write_database(tmp_path / "db", [person(), corrupt_compressed_record(), person()])

    with open_bank(dbdir, on_diagnostic=on_diagnostic) as bank:
        records = bank.tables[0].records()
        assert next(records).number == 1
        with pytest.raises(StopReading):
            next(records)


@pytest.mark.usefixtures("prints_nothing")
def test_a_generator_stops_with_value_error_once_its_bank_is_closed(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [person(), person()])
    bank = open_bank(dbdir)
    records = bank.tables[0].records()
    next(records)

    bank.close()

    with pytest.raises(ValueError, match="is closed"):
        next(records)
    assert counts(bank, DiagnosticKind.CORRUPT_RECORD) == 0


@pytest.mark.usefixtures("prints_nothing")
def test_files_and_read_file_refuse_a_closed_bank(tmp_path: Path) -> None:
    bank = open_bank(write_database(tmp_path / "db", []))
    bank.close()

    with pytest.raises(ValueError, match="is closed"):
        bank.files()
    with pytest.raises(ValueError, match="is closed"):
        bank.read_file(FileReference("a", "b", 1))


@pytest.mark.usefixtures("prints_nothing")
def test_generators_from_two_tables_can_be_interleaved(tmp_path: Path) -> None:
    dbdir = database_with_extra_definition_key(
        tmp_path / "db",
        "Base002",
        patched_table_definition(tableid=2),
        [person(), bank_record(2, FIELDS), person(), bank_record(2, FIELDS)],
    )

    with open_bank(dbdir) as bank:
        first, second = (table.records() for table in bank.tables)
        numbers = [next(first).number, next(second).number, next(first).number, next(second).number]

    assert numbers == [1, 2, 3, 4]


@pytest.mark.usefixtures("prints_nothing")
def test_files_yields_the_files_table_records_without_names(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [person(), file_record(b"first"), None, file_record(b"second")])

    with open_bank(dbdir) as bank:
        assert list(bank.files()) == [EmbeddedFile(2, b"first", None), EmbeddedFile(4, b"second", None)]


@pytest.mark.usefixtures("prints_nothing")
@pytest.mark.parametrize(("extension", "name"), [("pdf", "report.pdf"), ("", "report")])
def test_read_file_follows_a_reference_and_names_the_file(tmp_path: Path, extension: str, name: str) -> None:
    reference = file_reference_field("report", extension, 2)
    dbdir = write_database(tmp_path / "db", [person(file_field=reference), file_record(b"%PDF")])

    with open_bank(dbdir) as bank:
        (record,) = bank.tables[0].records()
        value = record["Entry #6"].value
        assert isinstance(value, FileReference)
        assert bank.read_file(value) == EmbeddedFile(2, b"%PDF", name)


@pytest.mark.usefixtures("prints_nothing")
@pytest.mark.parametrize(
    ("reference", "reason"),
    [
        (FileReference("a", "b", None), "its record number is not a number"),
        (FileReference("a", "b", 0), "CroBank has no record 0"),
        (FileReference("a", "b", 99), "CroBank has no record 99"),
        (FileReference("a", "b", 3), "CroBank record 3 is deleted or corrupt"),
        (FileReference("a", "b", 4), "CroBank record 4 is deleted or corrupt"),
        (FileReference("a", "b", 1), "CroBank record 1 is not a record of the Files table"),
    ],
    ids=["no-number", "zero", "past-the-end", "deleted", "corrupt", "not-a-file"],
)
def test_a_reference_that_cannot_be_resolved_is_reported(tmp_path: Path, reference: FileReference, reason: str) -> None:
    dbdir = write_database(tmp_path / "db", [person(), file_record(b"x"), None, corrupt_compressed_record()])

    with open_bank(dbdir) as bank:
        assert bank.read_file(reference) is None
        (diagnostic,) = [d for d in bank.diagnostics if d.kind == DiagnosticKind.UNRESOLVED_FILE_REFERENCE]

    assert (diagnostic.file, diagnostic.record) == ("CroBank.dat", reference.record)
    assert diagnostic.message.endswith(reason)


@pytest.mark.usefixtures("prints_nothing")
def test_a_database_without_a_files_table_has_no_files(tmp_path: Path) -> None:
    dbdir = database_without_files_table(tmp_path / "db", [file_record(b"x")])

    with open_bank(dbdir) as bank:
        assert bank.files_abbreviation is None
        assert list(bank.files()) == []
        assert bank.read_file(FileReference("a", "b", 1)) is None
        (diagnostic,) = [d for d in bank.diagnostics if d.kind == DiagnosticKind.UNRESOLVED_FILE_REFERENCE]
        assert diagnostic.message.endswith("the database has no Files table")


PARITY_CASES = [
    (b"01.02", None),
    (b"01.03", None),
    (b"01.04", None),
    (b"01.04", KOD),
    (b"01.05", KOD),
    (b"01.11", KOD),
]


@pytest.mark.parametrize(
    ("version", "kod"),
    PARITY_CASES,
    ids=lambda value: value.decode() if isinstance(value, bytes) else ("kod" if value else "default"),
)
def test_field_text_matches_database_enumerate_records(
    tmp_path: Path, capfd: pytest.CaptureFixture[str], version: bytes, kod: list[int] | None
) -> None:
    records = [
        person(),
        person(date=b"850000", file_field=file_reference_field("report", "pdf", 3)),
        file_record(b"%PDF"),
        corrupt_compressed_record(),
        person(date="до 1990".encode("cp1251")),
        bank_record(TEST_TABLE_ID, [b"\x1b\xff\xff\xff\x7f"]),
    ]
    if version != b"01.11":
        records.insert(3, None)
    dbdir = write_database(tmp_path / "db", records, kod, version=version)

    with Database(dbdir, False, KODcoding(kod if kod else INITIAL_KOD)) as db:
        expected = [
            (record.recno, [field.content for field in record.fields])
            for table in db.enumerate_tables()
            for record in db.enumerate_records(table)
        ]
    capfd.readouterr()

    with open_bank(dbdir, kod=Kod.from_table(kod) if kod else Kod.default()) as bank:
        actual = [
            (record.number, [field.text for field in record.fields])
            for table in bank.tables
            for record in table.records()
        ]

    assert actual == expected
    assert len(actual) == 4
    captured = capfd.readouterr()
    assert (captured.out, captured.err) == ("", "")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/test_api_bank.py`
Expected: FAIL — the record tests with `NotImplementedError: Task 10 reads records`, the file tests with `AttributeError: 'Bank' object has no attribute 'files'` (or `'read_file'`).

- [ ] **Step 3: Implement**

In `src/cronos_extract/_api/bank.py`, change the imports: `from .diagnostics import Diagnostic, DiagnosticKind, DiagnosticLog, RecordNumbers` and `from .values import EmbeddedFile, FieldDefinition, FileReference, Record, decode_record`. Add constants:

```python
BANK_FILE = "CroBank.dat"
# Record data holds the table id in one byte.
LARGEST_TABLE_ID = 255
```

In `Bank.__init__`, add:

```python
        self._corrupt_records = RecordNumbers(database.bank.nrofrecords)
        self._unsupported_tables: set[int] = set()
```

Replace the `_records` placeholder with these methods of `Bank`:

```text
    def files(self) -> Iterator[EmbeddedFile]:
        """
        The files stored in the Files table, in CroBank order, read one CroBank record per step, without names.

        Raises ValueError when the bank is closed, now or at any later step.
        """
        self._check_open()
        return self._files()

    def read_file(self, reference: FileReference) -> EmbeddedFile | None:
        """
        The file `reference` refers to, named after the reference.

        Returns None, recording unresolved_file_reference, when the reference's record is not a readable record of
        the Files table. Raises ValueError when the bank is closed.
        """
        self._check_open()
        record = reference.record
        if record is None:
            return self._unresolved(reference, "its record number is not a number")
        if self._files_table_id is None:
            return self._unresolved(reference, "the database has no Files table")
        if not 1 <= record <= self._database.bank.nrofrecords:
            return self._unresolved(reference, f"CroBank has no record {record}")
        data = self._read(record)
        if data is None:
            return self._unresolved(reference, f"CroBank record {record} is deleted or corrupt")
        if not data or data[0] != self._files_table_id:
            return self._unresolved(reference, f"CroBank record {record} is not a record of the Files table")
        name = f"{reference.name}.{reference.extension}" if reference.extension else reference.name
        return EmbeddedFile(record, data[1:], name)

    def _unresolved(self, reference: FileReference, reason: str) -> None:
        self._log.record(
            Diagnostic(
                DiagnosticKind.UNRESOLVED_FILE_REFERENCE,
                f"a file reference cannot be read: {reason}",
                file=BANK_FILE,
                record=reference.record,
            )
        )

    def _read(self, number: int) -> bytes | None:
        """
        CroBank record `number`, or None when it is deleted or cannot be read.

        A record that cannot be read is reported as corrupt_record the first time only. OSError propagates.
        Raises ValueError when the bank is closed.
        """
        self._check_open()
        try:
            return cast(bytes | None, self._database.bank.readrec(number))
        except OSError:
            raise
        except Exception as e:
            if self._corrupt_records.add(number):
                self._log.record(
                    Diagnostic(
                        DiagnosticKind.CORRUPT_RECORD,
                        f"CroBank record {number} is corrupt and is skipped: {describe_error(e)}",
                        file=BANK_FILE,
                        record=number,
                    )
                )
            return None

    def _records(self, table: Table) -> Iterator[Record]:
        if table.id > LARGEST_TABLE_ID:
            if table.id not in self._unsupported_tables:
                self._unsupported_tables.add(table.id)
                self._log.record(
                    Diagnostic(
                        DiagnosticKind.UNSUPPORTED_TABLE,
                        f"the table has id {table.id}, but this release reads only tables with ids up to "
                        f"{LARGEST_TABLE_ID}, so its records are not read",
                        file=STRU_FILE,
                        table=table.name,
                    )
                )
            return
        for number in range(1, self._database.bank.nrofrecords + 1):
            data = self._read(number)
            if not data or data[0] != table.id:
                continue
            record = decode_record(number, table.name, table.fields, table._definition.fields, data[1:])
            for diagnostic in record.diagnostics:
                self._log.record(diagnostic)
            yield record

    def _files(self) -> Iterator[EmbeddedFile]:
        if self._files_table_id is None:
            return
        for number in range(1, self._database.bank.nrofrecords + 1):
            data = self._read(number)
            if data and data[0] == self._files_table_id:
                yield EmbeddedFile(number, data[1:], None)
```

`describe_error` of a zlib or struct error names the exception and its message only, never record bytes; check this in `Datafile.decompress` and `readextendedrecord`, and stop and report if a message there embeds data.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_api_bank.py tests/test_api_open.py`
Expected: all pass. In the parity test, the corrupt record and the deleted record are skipped by both readers, and the record with an undecodable field is kept by both, so four records compare.

- [ ] **Step 5: Try hostile input by hand**

Run this in `/tmp` and confirm it prints only `ok` lines and no traceback:

```bash
uv run python - <<'EOF'
import os, sys, tempfile
sys.path.insert(0, "tests")
from pathlib import Path
from cronos_builder import write_database, bank_record, TEST_TABLE_ID
from cronos_extract._api.bank import open as open_bank
root = Path(tempfile.mkdtemp(prefix="t10-"))
dbdir = Path(write_database(root / "db", [bank_record(TEST_TABLE_ID, [b"x"])]))
data = bytearray((dbdir / "CroBank.dat").read_bytes())
for position in range(len(data) - 1, 255, -1):
    data[position] ^= 0xFF
(dbdir / "CroBank.dat").write_bytes(bytes(data))
with open_bank(dbdir) as bank:
    for table in bank.tables:
        list(table.records())
    list(bank.files())
    print("ok", dict(bank.diagnostic_counts))
(dbdir / "CroBank.tad").write_bytes((dbdir / "CroBank.tad").read_bytes() + os.urandom(1000))
with open_bank(dbdir) as bank:
    for table in bank.tables:
        list(table.records())
    print("ok", dict(bank.diagnostic_counts))
EOF
```

If a traceback appears, write a failing test for that input in `tests/test_api_bank.py`, fix it, and report it.

- [ ] **Step 6: Run the suite and linters, then commit**

```bash
fail() { echo "STOPPED: $*"; exit 1; }
uv run pytest -q > /tmp/t10-pytest.txt 2>&1 || fail pytest
uv run ruff check > /tmp/t10-ruff.txt 2>&1 || fail ruff
uv run ruff format --check > /tmp/t10-format.txt 2>&1 || fail format
uv run ty check > /tmp/t10-ty.txt 2>&1 || fail ty
test -z "$(git diff master -- tests/golden)" || fail golden
git add src/cronos_extract/_api/bank.py tests/test_api_bank.py
git commit -F - <<'EOF' || fail commit
Read records and files lazily through the Bank

Table.records() and Bank.files() read one CroBank record per step. A
record that cannot be read is reported once per bank, a table id above
255 is reported instead of silently yielding nothing, and read_file
reports a reference it cannot resolve. The API's field text matches
Database.enumerate_records on every version the builder writes.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---
### Task 11: `crack_kod` over cracking steps shared with crodump

Spec: P7, P12 "Cracking".

**Files:**
- Create: `src/cronos_extract/_api/crack.py`, `tests/test_api_crack.py`
- Modify: `src/cronos_extract/crodump.py`
- Test: `tests/test_crack.py`

**Interfaces:**
- Consumes: Task 4's `Kod`; Task 8's `database_directory`, `list_directory`, `open_datafile`; Task 3's `DiagnosticLog`, errors.
- Produces, in `cronos_extract._api.crack`:
  - `DBCRACK_RECORD_LIMIT = 10000`
  - `readable_records(datafile: Datafile, limit: int | None = None) -> Iterator[tuple[int, bytes | None]]`
  - `stru_xref(stru: Datafile) -> list[list[int]]`
  - `bank_and_index_xref(bank: Datafile, index: Datafile) -> list[list[int]]`
  - `kod_from_xref(xref: list[list[int]]) -> tuple[list[int], list[int]]` (moved from `crodump.py`, unchanged)
  - `fill_single_gap(kod: list[int], confidence: list[int]) -> None`
  - `kod_is_resolved(kod: list[int], confidence: list[int]) -> bool`
  - `crack_kod(path: str | os.PathLike[str], method: Literal["strucrack", "dbcrack"]) -> Kod | None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_crack.py`:

```python
# ABOUTME: Tests for crack_kod, which recovers a database's KOD table from its encrypted records without printing.
# ABOUTME: Uses encrypted databases from tests/cronos_builder.py whose KOD table is known, and checks crodump agrees.
from pathlib import Path
from typing import Any, cast

import pytest
from cronos_builder import (
    TEST_TABLE_ID,
    UNUSED_TABLE_ID,
    bank_record,
    corrupt_compressed_record,
    crackable_database,
    random_kod,
    write_database,
)

from cronos_extract import crodump
from cronos_extract._api.crack import crack_kod
from cronos_extract._api.errors import NotACronosFile
from cronos_extract._api.kod import Kod
from cronos_extract.koddecoder import KODcoding

KOD = random_kod(seed=7)
PERSON_FIELDS = [b"42", b"Hammersley", b"", b"1240315", b"0930", b"", b"", b"", b"", b"", b""]
METHODS = ["strucrack", "dbcrack"]


@pytest.fixture(autouse=True)
def prints_nothing(capfd: pytest.CaptureFixture[str]):
    yield
    captured = capfd.readouterr()
    assert (captured.out, captured.err) == ("", "")


@pytest.fixture
def encrypted_db(tmp_path: Path) -> str:
    return crackable_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, PERSON_FIELDS)], KOD)


@pytest.mark.parametrize("method", METHODS)
def test_crack_kod_recovers_the_kod_of_an_encrypted_database(encrypted_db: str, method: str) -> None:
    assert crack_kod(encrypted_db, cast(Any, method)) == Kod.from_table(KOD)


@pytest.mark.parametrize("method", METHODS)
def test_crack_kod_agrees_with_crodump(encrypted_db: str, method: str, capfd: pytest.CaptureFixture[str]) -> None:
    expected = crodump.crack_kod(method, encrypted_db, False)
    capfd.readouterr()

    kod = crack_kod(Path(encrypted_db), cast(Any, method))

    assert kod is not None
    assert list(kod.table) == expected


@pytest.mark.parametrize("method", METHODS)
def test_crack_kod_returns_none_when_too_few_records_resolve_the_kod(tmp_path: Path, method: str) -> None:
    dbdir = write_database(
        tmp_path / "db", [bank_record(TEST_TABLE_ID, PERSON_FIELDS)], KOD, index_records=[bytes(12)] * 3
    )

    assert crack_kod(dbdir, cast(Any, method)) is None


def test_dbcrack_returns_none_without_an_index(encrypted_db: str) -> None:
    for name in ("CroIndex.dat", "CroIndex.tad"):
        (Path(encrypted_db) / name).unlink()

    assert crack_kod(encrypted_db, "dbcrack") is None


def test_strucrack_does_not_need_an_index(encrypted_db: str) -> None:
    for name in ("CroIndex.dat", "CroIndex.tad"):
        (Path(encrypted_db) / name).unlink()

    assert crack_kod(encrypted_db, "strucrack") == Kod.from_table(KOD)


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("missing", ["Stru", "Bank"])
def test_crack_kod_needs_stru_and_bank(encrypted_db: str, method: str, missing: str) -> None:
    for extension in ("dat", "tad"):
        (Path(encrypted_db) / f"Cro{missing}.{extension}").unlink()

    with pytest.raises(NotACronosFile, match=f"Cro{missing}"):
        crack_kod(encrypted_db, cast(Any, method))


def test_crack_kod_refuses_an_unknown_method(encrypted_db: str) -> None:
    with pytest.raises(ValueError, match="unknown crack method 'guess'"):
        crack_kod(encrypted_db, cast(Any, "guess"))


def crackable_database_with_a_record_that_looks_compressed(directory: Path) -> str:
    """A crackable database whose last CroStru record, read without a KOD, looks compressed but is not."""
    zero_byte_records = [bytes([UNUSED_TABLE_ID]) + bytes(11)] * 300
    stru_recno = 4 + 8 + 1
    looks_compressed = KODcoding(KOD).decode(stru_recno, corrupt_compressed_record())
    return write_database(
        directory,
        [bank_record(TEST_TABLE_ID, PERSON_FIELDS), *zero_byte_records],
        KOD,
        extra_stru_records=[*[bytes(256)] * 8, looks_compressed],
        index_records=zero_byte_records,
    )


def test_strucrack_skips_a_record_it_cannot_read(tmp_path: Path) -> None:
    dbdir = crackable_database_with_a_record_that_looks_compressed(tmp_path / "db")

    assert crack_kod(dbdir, "strucrack") == Kod.from_table(KOD)
```

`stru_recno` is 13 because `stru_records_from_test_db()` holds 4 records and 8 zero records follow; if the builder's test database holds a different number of CroStru records, compute `len(stru_records_from_test_db()) + 8 + 1` instead and say so.

Append to `tests/test_crack.py` (add `corrupt_compressed_record`, `UNUSED_TABLE_ID` to the `cronos_builder` import and `from cronos_extract.koddecoder import KODcoding`, sorted):

```python
def test_crodump_strucrack_skips_a_stru_record_it_cannot_read(tmp_path: Path) -> None:
    zero_byte_records = [bytes([UNUSED_TABLE_ID]) + bytes(11)] * 300
    looks_compressed = KODcoding(KOD).decode(4 + 8 + 1, corrupt_compressed_record())
    dbdir = write_database(
        tmp_path / "db",
        [bank_record(TEST_TABLE_ID, PERSON_FIELDS), *zero_byte_records],
        KOD,
        extra_stru_records=[*[bytes(256)] * 8, looks_compressed],
        index_records=zero_byte_records,
    )

    assert crack_kod("strucrack", dbdir, False) == KOD
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/test_api_crack.py tests/test_crack.py`
Expected: `test_api_crack.py` fails to collect with `ModuleNotFoundError: No module named 'cronos_extract._api.crack'`; `test_crodump_strucrack_skips_a_stru_record_it_cannot_read` FAILS with `ValueError: corrupt compressed data: ...`.

- [ ] **Step 3: Implement the shared steps and `crack_kod`**

Create `src/cronos_extract/_api/crack.py`:

```python
# ABOUTME: Recovers a database's KOD table from byte statistics of its encrypted records, printing nothing.
# ABOUTME: crack_kod uses these steps, and so do crodump's strucrack and dbcrack subcommands.
import os
from collections.abc import Iterator
from contextlib import ExitStack
from typing import Literal, cast

from ..Datafile import Datafile
from .datafiles import database_directory, list_directory, open_datafile
from .diagnostics import DiagnosticLog
from .errors import NotACronosFile, UnsupportedVersion
from .kod import Kod

# dbcrack reads at most this many records of CroBank and of CroIndex.
DBCRACK_RECORD_LIMIT = 10000


def readable_records(datafile: Datafile, limit: int | None = None) -> Iterator[tuple[int, bytes | None]]:
    """
    Yield (record number, data) for the first `limit` records of `datafile`, or all of them.

    The data is None for a deleted record and for one that cannot be read, which encrypted records read without a
    KOD can be when they look compressed by chance. OSError propagates.
    """
    count = datafile.nrofrecords if limit is None else min(limit, datafile.nrofrecords)
    for recno in range(1, count + 1):
        try:
            data = cast(bytes | None, datafile.readrec(recno))
        except OSError:
            raise
        except Exception:
            data = None
        yield recno, data


def new_xref() -> list[list[int]]:
    """An empty count table: xref[shift][encrypted byte]."""
    return [[0] * 256 for _ in range(256)]


def stru_xref(stru: Datafile) -> list[list[int]]:
    """
    Count, for every shift, how often each encrypted byte occurs in the readable records of `stru`.

    Most bytes of CroStru records are zero, so the commonest encrypted byte at a shift is the one that decodes to zero.
    """
    xref = new_xref()
    for recno, data in readable_records(stru):
        if not data:
            continue
        for offset, byte in enumerate(data):
            xref[(offset + recno) % 256][byte] += 1
    return xref


def bank_and_index_xref(bank: Datafile, index: Datafile) -> list[list[int]]:
    """
    Count the fourth byte of the first DBCRACK_RECORD_LIMIT readable records of `bank` and `index` longer than 11 bytes.

    Compressed records start with a uint16 size, 0x08 and 0x00, so the fourth byte decodes to zero.
    """
    xref = new_xref()
    for datafile in (bank, index):
        for recno, data in readable_records(datafile, DBCRACK_RECORD_LIMIT):
            if data and len(data) > 11:
                xref[(recno + 3) % 256][data[3]] += 1
    return xref
```

Move `kod_from_xref` from `crodump.py` into `crack.py` below `bank_and_index_xref`, with its docstring and body unchanged, adding the annotations `def kod_from_xref(xref: list[list[int]]) -> tuple[list[int], list[int]]:`. Then add:

```python
def fill_single_gap(kod: list[int], confidence: list[int]) -> None:
    """
    When exactly one entry of `kod` is unset and exactly one value is unused, assume they belong together.

    The entry gets confidence 1.
    """
    used = {value for entry, value in enumerate(kod) if confidence[entry] > 0}
    unset_entries = [entry for entry in range(256) if confidence[entry] == 0]
    unused_values = sorted(set(range(256)).difference(used))
    if len(unset_entries) == 1 and len(unused_values) == 1:
        kod[unset_entries[0]] = unused_values[0]
        confidence[unset_entries[0]] = 1


def kod_is_resolved(kod: list[int], confidence: list[int]) -> bool:
    """Whether every entry has a positive confidence and `kod` is a permutation of 0-255, so it can decode."""
    return all(value > 0 for value in confidence) and sorted(kod) == list(range(256))


def crack_kod(path: str | os.PathLike[str], method: Literal["strucrack", "dbcrack"]) -> Kod | None:
    """
    Recover the KOD table of the database in the directory `path` from its encrypted records, printing nothing.

    "strucrack" reads CroStru; "dbcrack" reads CroBank and CroIndex. Returns None when the method cannot recover a
    permutation of 0-255, including when dbcrack finds no readable CroIndex. Records that cannot be read are
    skipped. Raises NotACronosFile or UnsupportedVersion when CroStru or CroBank cannot be read, and ValueError for
    an unknown method.
    """
    if method not in ("strucrack", "dbcrack"):
        raise ValueError(f"unknown crack method {method!r}; use 'strucrack' or 'dbcrack'")
    directory = database_directory(path)
    names = list_directory(directory)
    log = DiagnosticLog(None)
    with ExitStack() as stack:
        stru, _ = open_datafile(directory, names, "Stru", compact=True, kod=None, log=log)
        stack.callback(stru.close)
        bank, _ = open_datafile(directory, names, "Bank", compact=True, kod=None, log=log)
        stack.callback(bank.close)
        if method == "strucrack":
            kod, confidence = kod_from_xref(stru_xref(stru))
            fill_single_gap(kod, confidence)
        else:
            try:
                index, _ = open_datafile(directory, names, "Index", compact=True, kod=None, log=log)
            except (NotACronosFile, UnsupportedVersion):
                return None
            stack.callback(index.close)
            kod, confidence = kod_from_xref(bank_and_index_xref(bank, index))
    return Kod.from_table(kod) if kod_is_resolved(kod, confidence) else None
```

- [ ] **Step 4: Make crodump use the shared steps**

In `src/cronos_extract/crodump.py`:
- Add `from ._api.crack import bank_and_index_xref, fill_single_gap, kod_from_xref, kod_is_resolved, stru_xref`.
- Delete `kod_from_xref` (now in `crack.py`).
- In `derive_kod_from_stru`, replace the `xref = ...` line and the loop that fills it with `xref = stru_xref(table)`. Replace the block from `kod_set = set([v for o, v in enumerate(KOD) if KOD_CONFIDENCE[o] > 0])` through `KOD_CONFIDENCE[entry] = 1` (the single-gap fill and its comment) with `fill_single_gap(KOD, KOD_CONFIDENCE)`. Replace `is_resolved = unset_count == 0 and sorted(KOD) == list(range(256))` with `is_resolved = kod_is_resolved(KOD, KOD_CONFIDENCE)`, keeping the comment above it and the `unset_count` line, which the messages use.
- In `derive_kod_from_bank_and_index`, keep the loop's missing-file check but move it before counting:

```python
    for dbfile in db.bank, db.index:
        if not dbfile:
            if not args.silent:
                print(f"no data file found in {args.dbdir}")
            return None

    KOD, KOD_CONFIDENCE = kod_from_xref(bank_and_index_xref(db.bank, db.index))
```

  and replace `if unset_count > 0 or sorted(KOD) != list(range(256)):` with `if not kod_is_resolved(KOD, KOD_CONFIDENCE):`, keeping the `unset_count` line.

The `for i, data in enumerate(records)` dump loop further down in `derive_kod_from_stru` keeps `table.enumrecords()`; it runs only interactively.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_api_crack.py tests/test_crack.py tests/test_cli_characterisation.py`
Expected: all pass, and `git diff master -- tests/golden` is empty.

- [ ] **Step 6: Run the suite and linters, then commit**

```bash
fail() { echo "STOPPED: $*"; exit 1; }
uv run pytest -q > /tmp/t11-pytest.txt 2>&1 || fail pytest
uv run ruff check > /tmp/t11-ruff.txt 2>&1 || fail ruff
uv run ruff format --check > /tmp/t11-format.txt 2>&1 || fail format
uv run ty check > /tmp/t11-ty.txt 2>&1 || fail ty
test -z "$(git diff master -- tests/golden)" || fail golden
git add src/cronos_extract/_api/crack.py src/cronos_extract/crodump.py tests/test_api_crack.py tests/test_crack.py
git commit -F - <<'EOF' || fail commit
Add crack_kod and share the cracking steps with crodump

crack_kod recovers a KOD with strucrack or dbcrack without printing,
opening only the files its method reads. The byte counting, the
single-gap fill and the permutation check move into _api/crack.py,
which crodump uses too. Records that cannot be read are skipped, so a
CroStru record that looks compressed no longer stops strucrack.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 12: Tests against Ben's real databases

Spec: P10, P11 (layout check), P12 "Builder and tests" (`realdata` output, v4 flags), Open items (v4 deleted records).

**Files:**
- Create: `tests/test_realdata.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: everything above; Task 1's `tad_layout`.
- Produces: the `realdata` marker, deselected by default.

These tests read `local/mash_datasets_with_CroIndex_dat.txt`, which only Ben's machine has. Never print, commit or report a path from it. Report results as counts and test ids (`db00`, `db01`, …) only.

- [ ] **Step 1: Register the marker and deselect it by default**

In `pyproject.toml`, change `[tool.pytest.ini_options]` to:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = ["-ra", "--strict-markers", "--strict-config", "-m", "not realdata"]
markers = [
    "realdata: reads the real databases listed in the git-ignored local/mash_datasets_with_CroIndex_dat.txt; run with -m realdata",
]
filterwarnings = ["error"]
```

- [ ] **Step 2: Write the tests**

Create `tests/test_realdata.py`:

```python
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
```

- [ ] **Step 3: Check the marker is deselected by default and selected on request**

```bash
fail() { echo "STOPPED: $*"; exit 1; }
uv run pytest -q --collect-only tests/test_realdata.py > /tmp/t12-default.txt 2>&1
grep -q "deselected" /tmp/t12-default.txt || fail "realdata tests are not deselected by default"
uv run pytest -q -m realdata --collect-only tests/test_realdata.py > /tmp/t12-selected.txt 2>&1 || fail "collect realdata"
grep -c "test_realdata.py::" /tmp/t12-selected.txt
```

Expected: the default run reports the tests as deselected; the `-m realdata` run lists them with ids `db00`, `db01`, … and no path.

- [ ] **Step 4: Run the real-data tests**

Run: `uv run pytest -q -m realdata tests/test_realdata.py -p no:cacheprovider > /tmp/t12-realdata.txt 2>&1; echo "exit=$?"`

Read `/tmp/t12-realdata.txt` yourself. Report to the controller only: pass, fail and skip counts per test function, and for each failure its test id and the assertion message with any path removed. Do not paste the file. These are tests of real data, not of the code's intent: a failure is information to report, not something to fix by changing an assertion. In particular:
- If `test_dbcrack_recovers_a_kod_that_opens_a_v4_database` fails, report whether `crack_kod` returned `None` or the bank failed to open.
- If `test_v4_tad_entries_never_use_the_v3_deleted_length` fails, that contradicts the count recorded in the spec's open items: report it.
- If `test_field_text_matches_database_enumerate_records` fails, report the table id and whether the record numbers or the texts differ.

- [ ] **Step 5: Run the default suite and linters, then commit**

```bash
fail() { echo "STOPPED: $*"; exit 1; }
uv run pytest -q > /tmp/t12-pytest.txt 2>&1 || fail pytest
uv run ruff check > /tmp/t12-ruff.txt 2>&1 || fail ruff
uv run ruff format --check > /tmp/t12-format.txt 2>&1 || fail format
uv run ty check > /tmp/t12-ty.txt 2>&1 || fail ty
git status --short | grep -q "local/" && fail "local/ shows in git status"
git add pyproject.toml tests/test_realdata.py
git commit -F - <<'EOF' || fail commit
Test the API against the real databases in local/

The realdata tests read the git-ignored list of real databases and are
deselected unless run with -m realdata. They check that opening raises
only CronosError and prints nothing, that field text matches
Database.enumerate_records, that bank.info agrees with the survey,
that the builder's .tad layouts match real files, and that dbcrack
opens the v4 databases.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 13: The public names, documentation and `py.typed`

Spec: P2, P12 (`__all__` includes `open`, `compact=True` documentation), Architecture "Documentation".

**Files:**
- Modify: `src/cronos_extract/__init__.py`, `README.md`, `CLAUDE.md`, every `tests/test_api_*.py` that imports a public name from `cronos_extract._api`
- Create: `src/cronos_extract/py.typed`, `tests/test_api_public.py`

**Interfaces:**
- Consumes: every public name from Tasks 3–11.
- Produces: `cronos_extract.__all__ == ["Bank", "CronosError", "DatabaseDefinitionError", "Diagnostic", "DiagnosticKind", "EmbeddedFile", "Field", "FieldDefinition", "FileInfo", "FileReference", "Kod", "NotACronosFile", "Record", "Table", "UnsupportedVersion", "crack_kod", "open"]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_public.py`:

```python
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
        assert getattr(cronos_extract, name).__module__.startswith("cronos_extract._api.")


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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/test_api_public.py`
Expected: FAIL with `AttributeError: module 'cronos_extract' has no attribute '__all__'`, and the `py.typed` test fails.

- [ ] **Step 3: Implement**

Replace `src/cronos_extract/__init__.py` (its second ABOUTME line, "Exposes no names of its own", is no longer true) with:

```python
# ABOUTME: The cronos_extract library API: open a CronosPro database and read its tables, records and files.
# ABOUTME: Every public name is re-exported here and listed in __all__; everything else in the package is private.
"""
Read CronosPro databases.

    import cronos_extract

    with cronos_extract.open("path/to/database") as bank:
        for table in bank.tables:
            for record in table.records():
                print(record["Entry #4"].value)

This API promises:

- Only the names in ``__all__`` are public. Other modules and names in the package are private and may change.
- Iteration is lazy: ``Table.records()`` and ``Bank.files()`` read one CroBank record per step. Each
  ``records()`` call walks all of CroBank.
- A ``Bank`` is not thread-safe. Generators from one bank may be interleaved on one thread.
- The library never prints. Problems reading survives are ``Diagnostic``s: ``bank.diagnostics`` keeps the first
  1,000, ``bank.diagnostic_counts`` counts every one, and ``on_diagnostic`` receives every one. Diagnostics from
  decoding a record are recorded each time the record is decoded. Later versions may add ``DiagnosticKind`` members.
- ``Field.value`` is ``str``, ``datetime.date``, ``datetime.time``, ``FileReference`` or ``None``; later versions may
  add types. Numbers are ``str``. A date stored with only its year is ``str``, such as ``"1985-00-00"``.
- ``compact=True`` reads the CroStru and CroBank indexes from disk instead of memory, for very large databases.
- ``from cronos_extract import *`` replaces the built-in ``open``; use ``import cronos_extract``.
"""

from ._api.bank import Bank, Table, open
from ._api.crack import crack_kod
from ._api.diagnostics import Diagnostic, DiagnosticKind
from ._api.errors import CronosError, DatabaseDefinitionError, NotACronosFile, UnsupportedVersion
from ._api.info import FileInfo
from ._api.kod import Kod
from ._api.values import EmbeddedFile, Field, FieldDefinition, FileReference, Record

__all__ = [
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
```

Create the empty file `src/cronos_extract/py.typed`.

In the `tests/test_api_*.py` files, import every public name from `cronos_extract` instead of `cronos_extract._api.*` (for example `from cronos_extract import Kod`, and `import cronos_extract` with `cronos_extract.open` in place of `open as open_bank`). Keep private names (`decode_record`, `DiagnosticLog`, `RecordNumbers`, `DIAGNOSTICS_KEPT`, `kod_coder`, `read_file_info`, `open_datafile`, `optional_file_info`, `warn_into`, `database_directory`, `list_directory`) imported from their `_api` modules.

- [ ] **Step 4: Check the wheel carries `py.typed`**

```bash
fail() { echo "STOPPED: $*"; exit 1; }
rm -rf /tmp/t13-dist
uv build --wheel -o /tmp/t13-dist > /tmp/t13-build.txt 2>&1 || fail build
uv run python -m zipfile -l /tmp/t13-dist/*.whl | grep -q "cronos_extract/py.typed" || fail "py.typed missing from wheel"
```

- [ ] **Step 5: Document the API**

In `README.md`, add after the "Surveying databases" section:

````markdown
# Python API

cronos-extract is also a library. The command line is being rebuilt on it.

```python
import cronos_extract

with cronos_extract.open("path/to/database") as bank:
    for table in bank.tables:
        for record in table.records():
            print(record["Entry #4"].value)
    print(bank.diagnostic_counts)
```

`open` takes `kod=` (a `cronos_extract.Kod`, or `None` to read without KOD decoding), `compact=True` for very large
databases, and `on_diagnostic=` for a function to call with each problem found while reading. The library never
prints: records it cannot read are skipped and reported as diagnostics, and a database it cannot read at all raises
a `cronos_extract.CronosError`. `cronos_extract.crack_kod(path, "strucrack")` or `"dbcrack"` recovers the KOD of a
database encrypted with its own. The module docstring (`help(cronos_extract)`) lists what the API promises.
````

In `CLAUDE.md`, under "## Architecture", add as the first bullet of the layer list:

```markdown
- **Public API** (`cronos_extract/__init__.py`, implemented in `_api/`): `open()` returns a `Bank` of `Table`s whose
  `records()` yield `Record`s of `Field`s with `value`, `text` and `raw`; problems it survives are `Diagnostic`s,
  and a database it cannot read raises a `CronosError`. It drives `Datafile`, `Database.read_db_definition`,
  `TableDefinition` and `Datamodel.Record` directly, never the printing `enumerate_*` generators, and passes a
  `warn` hook to the readers that print. Only names in `__all__` are public. `_format/files.py`'s
  `open_regular_file` is the one way Cro files are opened.
```

and under "## Commands", after `uv run pytest -q`:

```bash
uv run pytest -q -m realdata                # the real databases listed in local/, deselected by default; a node id needs -m realdata too
```

- [ ] **Step 6: Run the suite and linters, then commit**

```bash
fail() { echo "STOPPED: $*"; exit 1; }
uv run pytest -q > /tmp/t13-pytest.txt 2>&1 || fail pytest
uv run ruff check > /tmp/t13-ruff.txt 2>&1 || fail ruff
uv run ruff format --check > /tmp/t13-format.txt 2>&1 || fail format
uv run ty check > /tmp/t13-ty.txt 2>&1 || fail ty
test -z "$(git diff master -- tests/golden)" || fail golden
git add src/cronos_extract/__init__.py src/cronos_extract/py.typed README.md CLAUDE.md tests/test_api_*.py
git commit -F - <<'EOF' || fail commit
Publish the API from cronos_extract and mark the package typed

cronos_extract re-exports the public names and lists them in __all__,
and its docstring states what the API promises. py.typed ships in the
wheel. The README and CLAUDE.md describe the API.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 14: Whole-branch review, then record the outcome

This task is for the controller, not an implementer subagent.

- [ ] **Step 1: Whole-branch review by Fable**

Dispatch a reviewer on the model `fable` with the diff `master...phase1-public-api`, the spec and this plan. Ask it to review architecture, correctness against the spec, tests and hostile input, and to try, in `/tmp`, at least: FIFOs, sockets and dangling symlinks named like each Cro file; directory and file names that are not valid UTF-8; binary garbage in place of each `.dat` and `.tad`; truncated `.dat` and `.tad` files; a CroStru definition of random bytes; a wrong KOD; a table id above 255; a CroBank of thousands of corrupt records; and an `on_diagnostic` that raises. Verify each finding against the code before acting on it; fix the real ones test-first, each in its own commit.

- [ ] **Step 2: Record the outcome**

Append `## Outcome (YYYY-MM-DD)` to this plan: the commits, where the code diverged from the plan and why, what the reviews found and what was declined with evidence, and the `realdata` results as counts. Update the roadmap spec: its status line (Phase 1 complete, pending merge), the Phase 1 carried-forward item (done), the Phase 3 stat-then-open item (closed by `open_regular_file`), and the new Phase 3 items from the Phase 1 spec's "Open items this phase records". Commit.

- [ ] **Step 3: Stop for Ben**

Report to Ben and wait for his approval before pushing and opening the PR.
