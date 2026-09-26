# Phase 3c: bank reading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read CroBank in time proportional to its records, choose the KOD in one function that reports a KOD that does
not fit, report an unresolved file reference where the reference is, and settle the two items 3b left.

**Architecture:** `Bank` keeps a lazily filled index of CroBank (a scan position plus an array of record numbers per
table-id byte) that every table's generator shares; `koddecoder.select_kod` replaces `Datafile`'s inline KOD choice and
`open()`'s `unused_kod` check; `FileReference` carries the table, record and field it was read from.

**Tech Stack:** Python 3.12+, `array`, pytest, ruff, ty, uv.

**Spec:** `docs/superpowers/specs/2026-09-26-phase3c-bank-reading-design.md` (decisions C1–C7). Read it before any
task; where this plan and the spec disagree, the spec wins and the divergence is reported.

## Global Constraints

- Every code file keeps its two `ABOUTME: ` lines; update them when a file's job changes.
- `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check` and `uv run ty check` are clean before every
  commit (the pre-commit hook runs them). pytest runs with `filterwarnings = error`.
- Tests build databases with `tests/cronos_builder.py`; no mocks. A wrapper that delegates to the real method and
  records what it was called with is allowed (C1's read count); nothing asserts on a stub's behaviour.
- Commit messages: imperative, subject ≤ 72 characters, ending with exactly one trailer line:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never `git checkout -- <file>` or `git stash` to undo work; copy a file aside and restore it by hand.
- Never open, quote or commit entries of `local/mash_datasets_with_CroIndex_dat.txt`; report realdata as counts only.
- A golden file changes only by `uv run pytest --update-golden`, and `git diff tests/golden` must show only the
  change the task names.
- Diagnostic messages never hold CroBank record content (names, text); record numbers are allowed (C3).

## Review Focus

1. A generator abandoned part-way through the scan (the caller stops iterating) while another table's generator
   continues: the other generator must still see all its records, each once.
2. `records()` called again after a complete scan must not read any record of another table.
3. `on_diagnostic` that starts a `records()` loop of its own during a scan step must not duplicate a record in the
   index (the position check of C1).
4. A v4 or `01.04` file whose header is **not** KOD-encoded, opened with the default KOD, reports nothing and is read
   with no KOD (C2, `kod_encoded` first).
5. A file reference read by a table that reads from the index (not the first table read) still carries its table,
   referrer and field.

Each is pinned by a test in the task that owns it (Tasks 2, 3 and 4).

---

### Task 1: The two items 3b left (C4, C5)

**Files:**
- Modify: `src/cronos_extract/Datamodel.py` (the `except Exception` after `except EOFError` around
  `self.terminator = rd.readdword()`)
- Modify: `src/cronos_extract/_cli/inspect.py` (`destruct_sys3_def`, `destruct_sys_definition`, the `--type` help)
- Modify: `README.md` (the `destruct` sentence near line 144, if it mentions `-t 3`)
- Test: `tests/test_cli_inspect.py`

**Interfaces:**
- Produces: nothing later tasks use.

- [ ] **Step 1: Write the failing test** in `tests/test_cli_inspect.py`, using `run_command` as the file's other
  destruct tests do:

```python
def test_destruct_of_a_crosys_type_3_record_says_it_cannot_be_decoded() -> None:
    result = run_command("cli", ["inspect", "destruct", "-t", "3"], stdin=b"03 00 00 00 00")

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        "Error: the definition on stdin cannot be decoded: "
        "CroSys record type 3 cannot be decoded: its layout is not known\n"
    )
```

  Match `stdin`'s type and the hex format to the neighbouring destruct tests; if `describe_error` prefixes the
  exception type (e.g. `ValueError: `), pin what it prints and report it.

- [ ] **Step 2: Run it and see it fail** (today: exit 0, nothing printed).
  Run: `uv run pytest -q tests/test_cli_inspect.py -k crosys_type_3`

- [ ] **Step 3: Implement.** Delete `destruct_sys3_def`; for `systype == 3`, `destruct_sys_definition` raises
  `ValueError("CroSys record type 3 cannot be decoded: its layout is not known")`. `--type` help:
  `"what type of record to destruct: 1 database, 2 table or 3 CroSys definition (CroSys type 3 records are recognised
  but not decoded)"`. Delete the unreachable `except Exception as e: self.report_structure(f"Error '{e}' parsing
  Tabledefinition")` clause in `TableDefinition.decode`. Update the README sentence if it describes `-t 3`.

- [ ] **Step 4: Run the tests.** `uv run pytest -q` — all pass, golden files unchanged.

- [ ] **Step 5: Commit** — `Report that CroSys type 3 records cannot be decoded` (one commit for C5 with C4, or two
  commits; C4's is `Remove an unreachable branch from TableDefinition.decode`).

---

### Task 2: One KOD-selection function (C2)

**Files:**
- Modify: `src/cronos_extract/_diagnostic.py` (`DiagnosticKind.MISMATCHED_KOD = "mismatched_kod"`, after
  `UNUSED_KOD`)
- Modify: `src/cronos_extract/koddecoder.py` (add `select_kod`)
- Modify: `src/cronos_extract/Datafile.py` (`__init__` uses `select_kod`)
- Modify: `src/cronos_extract/_api/bank.py` (remove `open()`'s `unused_kod` block; `DEFAULT_KOD` stays as `open`'s
  default)
- Modify: `src/cronos_extract/_cli/crack.py` (`raw_datafile`'s `report_once` drops `MISMATCHED_KOD`)
- Modify: `tests/golden/export-postgres-nokod.stderr` (via `--update-golden`)
- Test: `tests/test_koddecoder.py`, `tests/test_api_open.py`, `tests/test_api_diagnostics.py`,
  `tests/test_cli_inspect.py`, `tests/test_cli_crack.py`

**Interfaces:**
- Produces: `koddecoder.select_kod(header: DatHeader, kod: KODcoding | None, filename: str) -> tuple[KODcoding | None,
  Diagnostic | None]` — the coder to decode the file's records with (None: no KOD decoding) and at most one
  diagnostic, whose `file` is `filename`. `DiagnosticKind.MISMATCHED_KOD`.

The rules (spec C2's table; `kod_encoded` is tested first, `own_kod` only for an encoded file; "default" means
`kod.kod == INITIAL_KOD`):

| `kod` | header | returns | diagnostic kind: message |
|---|---|---|---|
| None | encoded | None | `mismatched_kod`: `the file is KOD-encoded, but is read without KOD decoding` |
| None | not encoded | None | — |
| default | not encoded | None | — |
| other | not encoded | None | `unused_kod`: `the file is not KOD-encoded, so the KOD given is not used for it` |
| default | encoded, not own | `koddecoder.new()` | — |
| other | encoded, not own | `koddecoder.new()` | `unused_kod`: `the file is encrypted with the default KOD, so the KOD given is not used for it` |
| default | encoded, own | `kod` | `mismatched_kod`: `the file is encrypted with its own KOD, but is read with the default one; if its records do not decode, recover its KOD by cracking it` |
| other | encoded, own | `kod` | — |

- [ ] **Step 1: Write the failing tests.**
  - `tests/test_koddecoder.py`: `test_select_kod_chooses_and_reports` parametrised over the eight rows above, with
    ids naming them, on `DatHeader(version, 0, encoding, 0x40)` headers: `01.02` for "not own", `01.04` for "own",
    encoding `1` or `0`; plus a ninth row, `01.11` not encoded with the default KOD → `(None, None)` (Review Focus 4).
    Assert the returned coder's table (`coder.kod`) or `None`, and the diagnostic as a whole
    `Diagnostic(kind, message, file="CroStru.dat")`.
  - `tests/test_api_diagnostics.py`: the stable-values list gains `"mismatched_kod"` after `"unused_kod"`.
  - `tests/test_api_open.py`: replace `test_a_kod_that_no_file_uses_is_reported` with
    `test_each_file_reports_a_kod_that_does_not_fit_it`, parametrised as today plus two rows (written with
    `random_kod(seed=1)` at `01.04` and opened with `Kod.default()`; the same opened with `kod=None`), asserting the
    list of `(kind, file)` pairs of the KOD kinds in `bank.diagnostics`: `[(UNUSED_KOD, "CroStru.dat"), (UNUSED_KOD,
    "CroBank.dat")]` for the two unused rows, `[]` for the three silent rows, and `[(MISMATCHED_KOD, "CroStru.dat"),
    (MISMATCHED_KOD, "CroBank.dat")]` for the two new rows. Opening the two new rows may raise
    `DatabaseDefinitionError`; if so, collect with `on_diagnostic` and assert on what was collected.
  - `tests/test_cli_inspect.py`: `test_strudump_with_a_kod_the_database_does_not_use_warns` — `inspect strudump --kod
    <random_kod(seed=1) as hex> <write_database(... default version)>` prints
    `warning: unused_kod: CroStru.dat: the file is encrypted with the default KOD, so the KOD given is not used for it`
    on stderr (match the default version's actual encoding; `write_database` writes KOD-encoded only when given a KOD
    or `encoded=True`).
  - `tests/test_cli_crack.py`: `test_strucrack_prints_no_mismatched_kod` — on a `crackable_database`, stderr holds no
    `mismatched_kod`.

- [ ] **Step 2: Run them and see them fail.**

- [ ] **Step 3: Implement** `select_kod` in `koddecoder.py` (it imports `DatHeader` from `._format.header` and
  `Diagnostic`, `DiagnosticKind` from `._diagnostic`; check for an import cycle and report one). In `Datafile.__init__`,
  replace the inline choice with `self.kod, problem = select_kod(self.header, kod, f"Cro{self.name}.dat")`, report
  `problem` when not None, and build `RecordSource` with `self.kod` (no more `if self.encoding & 1`: `select_kod`
  already returns None for an unencoded file). Remove `open()`'s `unused_kod` block and any import it leaves unused.
  In `raw_datafile`, drop a diagnostic whose kind is `MISMATCHED_KOD` before `report_once` passes it on, with a
  comment: crack reads the encoded bytes on purpose.

- [ ] **Step 4: Update the golden file and check the diff.** `uv run pytest -q --update-golden
  tests/test_cli_characterisation.py`; `git diff tests/golden` must show exactly one new line in
  `export-postgres-nokod.stderr`, `warning: mismatched_kod: CroStru.dat: the file is KOD-encoded, but is read without
  KOD decoding`, and its summary line counting it. Anything else: stop and report.

- [ ] **Step 5: Run everything.** `uv run pytest -q` — fix any test whose exact stderr now holds a new KOD line only
  when the new line is what C2 specifies; report each such test.

- [ ] **Step 6: Update `CLAUDE.md`'s KOD section:** `Datafile` chooses through `koddecoder.select_kod`, which reports
  `unused_kod` and `mismatched_kod` per file; `crack` drops `mismatched_kod`.

- [ ] **Step 7: Commit** — `Choose each file's KOD in one function and report misfits`.

---

### Task 3: File references carry their context (C3)

**Files:**
- Modify: `src/cronos_extract/_api/values.py` (`FileReference`, `convert_field`, `decode_record`)
- Modify: `src/cronos_extract/_api/bank.py` (`read_file`, `_unresolved`)
- Modify: `src/cronos_extract/_diagnostic.py` (the `Diagnostic` docstring: record numbers are locations; the promise
  is about record content)
- Test: `tests/test_api_bank.py`, `tests/test_cli_export.py`, `tests/test_cronos_builder.py`

**Interfaces:**
- Produces: `FileReference(name: str, extension: str, record: int | None, table: str | None = None, referrer: int |
  None = None, field: str | None = None)`, frozen, all fields compared. `convert_field` gains the table name and record
  number it needs (keyword parameters `table: str, referrer: int`).

Messages of `unresolved_file_reference` (location `file="CroBank.dat"`, `table=reference.table`,
`record=reference.referrer`, `field=reference.field`):

| condition | message |
|---|---|
| `reference.record is None` | `the file cannot be read: its record number is not a number` |
| no Files table | `the file in CroBank record {n} cannot be read: the database has no Files table` |
| out of range | `the file in CroBank record {n} cannot be read: CroBank has no such record` |
| deleted or corrupt | `the file in CroBank record {n} cannot be read: the record is deleted or corrupt` |
| another table's record | `the file in CroBank record {n} cannot be read: the record is not in the Files table` |

- [ ] **Step 1: Write the failing tests.**
  - `tests/test_api_bank.py`: `test_a_reference_that_cannot_be_resolved_is_reported` keeps its six cases with the new
    reasons and asserts `(diagnostic.file, diagnostic.table, diagnostic.record, diagnostic.field) == ("CroBank.dat",
    None, None, None)` for the hand-built references; the no-Files-table test's message ends with `the database has no
    Files table`.
  - `tests/test_api_bank.py`: `test_a_decoded_reference_carries_where_it_was_read` — a `person(file_field=
    file_reference_field("report", "pdf", 99))` at CroBank record 1 decodes to `FileReference("report", "pdf", 99,
    "erdgeist", 1, "Entry #6")` (use the test table's real name and field name), and `read_file` reports
    `Diagnostic(UNRESOLVED_FILE_REFERENCE, "the file in CroBank record 99 cannot be read: CroBank has no such record",
    file="CroBank.dat", table=<table name>, record=1, field="Entry #6")`.
  - The same for a table read second (Review Focus 5): with `database_with_extra_definition_key(..., "Base002",
    patched_table_definition(tableid=2), [...])`, read table 1 fully first, then table 2, whose record holds a file
    field; its reference carries table 2's name and its own record number. (If table 2's definition has no file field
    at that position, put the reference in table 1's second-read instead: read `bank.tables[0].records()` twice and
    check the second pass.)
  - `tests/test_cli_export.py`: the three expected lines in `test_csv_export_skips_unreadable_file_references`, and
    those in `test_a_corrupt_referenced_file_gets_one_accurate_warning` and
    `test_a_file_reference_to_a_record_of_another_table_is_skipped`, become the `table "…", record N, field "…"` form,
    e.g. `warning: unresolved_file_reference: table "<name>", record 6, field "<field>": the file in CroBank record 99
    cannot be read: CroBank has no such record`. Take the table and field names from the builder's test table.
  - `tests/test_cronos_builder.py` lines comparing a decoded value to `FileReference(...)` gain the three context
    values.

- [ ] **Step 2: Run them and see them fail.**

- [ ] **Step 3: Implement.** Add the three fields; `decode_record` passes its `table` and `number` to `convert_field`,
  which fills `table`, `referrer` and `field` (the definition's name). `read_file` builds its messages from the table
  above and `_unresolved` locates the diagnostic from the reference. Update `FileReference`'s docstring, and the
  `Diagnostic` docstring's promise to: "The message never holds CroBank record content; it may name record numbers."

- [ ] **Step 4: Run everything.** `uv run pytest -q`; golden files unchanged (`git diff tests/golden` empty). Report
  any golden file that changes.

- [ ] **Step 5: Commit** — `Report an unresolved file reference where the reference is`.

---

### Task 4: The lazily filled CroBank index (C1)

**Files:**
- Modify: `src/cronos_extract/_api/bank.py` (`Bank.__init__`, `_records`, `_files`, a new private generator; the
  `open()` docstring)
- Modify: `src/cronos_extract/__init__.py` (the laziness and `compact` promises)
- Test: `tests/test_api_bank.py`, `tests/test_cli_export.py`

**Interfaces:**
- Consumes: `Bank._read(number) -> bytes | None` (unchanged), Task 3's `decode_record`.
- Produces: `Bank._table_records(table_id: int) -> Iterator[tuple[int, bytes]]` — each CroBank record number of
  `table_id` with its data (table-id byte included), in CroBank order, lazily. `_records` and `_files` are built on
  it. No public change.

State on `Bank`: `self._scan_position = 1`, `self._index: dict[int, array[int]] = {}`, and the type code, `"I"` when
`array("I").itemsize == 4` and `nrofrecords < 2**32`, else `"Q"`.

The algorithm (C1), which the tests do not fully determine:

```python
def _table_records(self, table_id):
    listed = self._index.setdefault(table_id, array(self._typecode))
    taken = 0
    while True:
        if taken < len(listed):
            number = listed[taken]
            taken += 1
            data = self._read(number)
            if data and data[0] == table_id:
                yield number, data
            continue
        number = self._scan_position
        if number > self._bank_file.nrofrecords:
            return
        data = self._read(number)
        if self._scan_position != number:
            continue  # a re-entrant call from on_diagnostic indexed this record meanwhile
        if data:
            self._index.setdefault(data[0], array(self._typecode)).append(number)
        self._scan_position = number + 1
        if data and data[0] == table_id:
            taken += 1  # the record just appended to `listed`
            yield number, data
```

- [ ] **Step 1: Write the failing tests** in `tests/test_api_bank.py`, over a database built with
  `database_with_extra_definition_key(tmp_path / "db", "Base002", patched_table_definition(tableid=2), [...])` holding
  records of table 1, table 2 and the Files table, some deleted and one `corrupt_compressed_record()`:
  - `test_a_table_read_after_another_reads_only_its_own_records` — wrap `bank._bank_file.read_record` with a function
    that appends the number to a list and returns the real method's result; read table 1 fully, clear the list, read
    table 2 fully: the list equals table 2's record numbers.
  - `test_an_export_reads_each_live_record_at_most_twice` — the same wrapper around reading every table and
    `bank.files()`: `max(Counter(numbers).values()) <= 2`, and the records yielded equal those of a fresh bank's.
  - `test_interleaved_generators_yield_what_sequential_ones_do` — `next()` alternately on table 1's and table 2's
    generators until both end; the numbers per table equal a fresh bank's sequential reads (extends the existing
    interleaving test).
  - `test_an_abandoned_generator_leaves_the_index_whole` (Review Focus 1) — take one record from table 1's generator,
    drop it, read table 2 fully and then table 1 fully: both equal a fresh bank's.
  - `test_a_second_pass_reads_no_other_table` (Review Focus 2) — after reading every table, the wrapper records only
    table 1's numbers during a second `records()` of table 1.
  - `test_a_records_loop_started_from_on_diagnostic_does_not_duplicate_records` (Review Focus 3) — an `on_diagnostic`
    that, on the first `corrupt_record`, runs `list(bank.tables[1].records())` (bind `bank` through a list or
    nonlocal); afterwards table 1 and table 2 each yield their records exactly once, as a fresh bank's.
  - Keep `test_records_are_read_one_crobank_record_per_step`, `test_generators_from_two_tables_can_be_interleaved` and
    the two `StopReading` tests unchanged; they must pass.

- [ ] **Step 2: Run them and see the new ones fail** (today a second table rereads everything).

- [ ] **Step 3: Implement** `_table_records` as above; `_records(table)` keeps its `unsupported_table` check first,
  then decodes each `(number, data)` from `_table_records(table.id)` with `data[1:]`; `_files()` yields
  `EmbeddedFile(number, data[1:], None)` from `_table_records(self._files_table_id)`. Update the docstrings: `records()`
  and `files()` read CroBank lazily, one record per step, and the first to reach a record indexes it for every table;
  `open()`'s `compact` sentence gains that the table index (up to 4 bytes per CroBank record) is held in memory either
  way. In `src/cronos_extract/__init__.py`, replace "Each ``records()`` call walks all of CroBank." with "CroBank is
  read at most once for all tables together; a table's later records come from an index of about 4 bytes per CroBank
  record." and add the index's memory to the `compact=True` line.

- [ ] **Step 4: Run everything.** `uv run pytest -q`; `git diff tests/golden` empty.

- [ ] **Step 5: Commit** — `Index CroBank once, as it is read, for every table`.

---

### Task 5: Realdata on the single pass (C1)

**Files:**
- Modify: `tests/test_realdata.py` (remove `MAX_BANK_TAD_BYTES`, `bank_is_small` and its five skip sites)
- Modify (git-ignored, not committed): `local/realdata-fingerprints.json`

- [ ] **Step 1: Remove the size limit** and its comment; each test that called `bank_is_small` runs on every database
  its other conditions allow.

- [ ] **Step 2: Write the missing fingerprints.** Run in the foreground with a long timeout:
  `uv run pytest -q -m realdata tests/test_realdata.py -k fingerprint --update-golden`. Check that entries already in
  the file are unchanged (compare a copy taken before the run: only new keys may appear). A changed existing entry is a
  regression: stop and report.

- [ ] **Step 3: Run the whole realdata suite** in the foreground: `uv run pytest -q -m realdata --durations=10`, and
  record the pass/skip/fail/xfail counts and the longest durations. Time the largest database's export on its own with
  `/usr/bin/time` over `uv run cronos-extract export --jsonl --compact -o <scratch file> <that directory>`, choosing it
  by the largest `CroBank.tad` among the listed databases, and record only its time and record count, never its path.

- [ ] **Step 4: Run** `uv run pytest -q` and the linters; **commit** `Read every real database now that CroBank is
  read once`. Report the counts and the timing to the controller for the Outcome.

---

### Task 6: Records (C6)

**Files:**
- Modify: `docs/superpowers/specs/2026-09-15-modernisation-roadmap-design.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Roadmap.** In "Open items carried forward", mark done, citing Phase 3c: the single pass (`Table.
  records()` reads all of CroBank on every call), KOD selection (an own-KOD file read with `Kod.default()`; `kod=None`
  on a KOD-encoded file) and file-reference context. "After 1.0" gains "CroSys record type 3, given a real CroSys file".
  The status line says Phase 3c is designed in `2026-09-26-phase3c-bank-reading-design.md` and implemented on branch
  `phase3c-bank-reading`, pull request pending.

- [ ] **Step 2: `CLAUDE.md`.** The `Datafile` paragraph and the KOD section describe `select_kod` (if Task 2 has not
  already), the Public API paragraph says `Bank` indexes CroBank as it reads it, and the Tests section no longer implies
  a size limit on realdata.

- [ ] **Step 3: Check** `uv run ruff format --check` (it formats Markdown code blocks) and **commit** `Record Phase 3c
  in the roadmap and CLAUDE.md`.

The controller appends this plan's Outcome section after the whole-branch review.

## Outcome

Implemented on branch `phase3c-bank-reading` in 10 commits after the plan (`a566e41`..`3986414`, plus this record),
subagent-driven: an implementer and a task review per task, then a whole-branch review by Fable.

- **Tests:** 875 passed on the branch before Task 2 and 898 after Task 4 (10 realdata tests deselected); ruff, format
  and ty clean. **Golden files:** only `export-postgres-nokod.stderr` changed, by one `mismatched_kod` line for CroStru
  and its summary line, as C2 predicted.
- **Realdata (counts only):** fingerprints rewritten with `--update-golden`: 24 passed, 6 skipped (databases that do
  not open with the default KOD); the 19 entries already in the file were unchanged and 5 databases the size limit
  used to skip were added. The full run was cut off by a 9,000 s timeout after 194 of 252 tests (171 passed, 18
  skipped, 5 xfailed, none failed); the rest, `-k "postgres or csv"`, then gave 33 passed, 27 skipped in 1 h 40 min.
  Every realdata test has run on this branch, with no failure.
- **Timing:** the database behind Phase 2's 19.8-minute export (v4; one data table and a Files table; 28,191 records
  and 61,133 files) takes 1,311 s for one full API read with the index. It never had a tables × records factor: its
  `.tad` holds 22,870,344 entries, nearly all read as live (flag `02`, a Phase 3d item), each KOD-decoded byte by byte
  at about 120 µs a record. The largest listed CroBank (2.05 GB `.tad`) does not open with the default KOD. The
  roadmap's 3c and v4 items and `CLAUDE.md` now say so.

### Divergences from the plan and their rulings

- Task 1: the `Error:` line carries `describe_error`'s `ValueError: ` prefix, as the plan allowed.
- Task 3: `tests/test_api_values.py` also compared a decoded `FileReference` and gained the context values.
- Task 4: an extra test pins an `on_diagnostic` exception at a live record (a scan that moved its position before
  indexing passed every listed test). The plan's docstring sentences "CroBank is read at most once" and "up to 4 bytes
  per CroBank record" were false and were reworded (`db6492d`).
- Task 5: the implementer removed the size limit; the controller ran the realdata commands, because subagents have
  stalled on long background runs. The size limit stays removed even though a full realdata run now takes about four
  hours.

### Final review

Fable, `f169e6d..a496465`: ready to merge with fixes; no behavioural defect under hostile, interleaved, abandoned and
re-entrant probing, and a crafted 1,000,000-entry `.tad` built a 4.0 MB index. Two Important findings, both
documentation: `select_kod`'s docstring was false for `kod=None`, and `CLAUDE.md` gave the Files table a
`records()`. Fixed in `3986414`; a scoped re-review found both addressed. The throwaway `array` that `setdefault` built
for every scanned record in `_table_records`, a minor Fable left and Copilot raised on the pull request, was removed
afterwards with a `_listed` helper. Minors left as Fable triaged them: four test-style points
(the type-3 destruct test could join the parametrised one; the per-file KOD test branches on its expected value; the
strudump `unused_kod` test checks membership only; the interleaving test indexes a tuple with a bool).
