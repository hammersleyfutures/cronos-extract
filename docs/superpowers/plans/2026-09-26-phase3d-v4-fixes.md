# Phase 3d: what the v4 evidence settles — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Skip v4 records marked deleted, refuse to decode an own-KOD v4 CroBank with the default KOD, report how many
deleted records CroBank holds, make the realdata checks per file and garbage-aware, and correct 3c's records.

**Architecture:** `_format/tad.py`'s v4 layout gains the deleted bit; `open()` gains one header check that raises a
new `OwnKodRequired` and exposes `Bank.deleted_records`; the export prints a note and gives JSON Lines one line through
a new `Writer` method; the builder writes deleted v4 records and real `.tad` header counts.

**Tech Stack:** Python 3.12+, pytest, ruff, ty, uv.

**Spec:** `docs/superpowers/specs/2026-09-26-phase3d-v4-fixes-design.md` (D1–D7). Read it before any task; where this
plan and the spec disagree, the spec wins and the divergence is reported.

## Global Constraints

- Every code file keeps its two `ABOUTME: ` lines; update them when a file's job changes.
- `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check` and `uv run ty check` are clean before every
  commit (the pre-commit hook runs them). pytest runs with `filterwarnings = error`.
- Tests build databases with `tests/cronos_builder.py`; no mocks, no stubs returning fake data.
- Commit messages: imperative, subject ≤ 72 characters, ending with exactly one trailer line:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never `git checkout -- <file>` or `git stash` to undo work; copy a file aside and restore it by hand.
- Never open, quote or commit entries of `local/mash_datasets_with_CroIndex_dat.txt`; do not run `-m realdata` (the
  controller runs it; it takes hours).
- A golden file changes only by `uv run pytest --update-golden`, and `git diff tests/golden` must show only the
  change the task names.
- Diagnostic messages never hold CroBank record content; record numbers and counts are allowed.

## Review Focus

1. A v4 `.tad` entry with the deleted bit and other bits (`06`, `07`) is deleted; `04` and `00` are not; `08` and `0c`
   (unexplained) stay live.
2. `OwnKodRequired` is raised only for a v4, KOD-encoded CroBank with the default KOD: not for `01.04`/`01.05`, not for
   `kod=None`, not for a non-default KOD, not for an unencoded v4 CroBank, and never from `crack_kod` or `inspect`.
3. A hostile `.tad` header whose deleted count exceeds its entries: capped, reported once, no crash.
4. The JSON Lines `deleted_records` line comes after the diagnostics found while opening and before the first table.
5. A built database with deleted v3 records now has a nonzero header count, so tests that pin a built database's full
   export stderr gain the note; each such change is the note and nothing else.

Each is pinned by a test in the task that owns it (Tasks 1–3).

---

### Task 1: v4 deleted entries (D1)

**Files:**
- Modify: `src/cronos_extract/_format/tad.py` (v4 `parse`, the flag comment, `V4_DELETED_FLAG`)
- Modify: `src/cronos_extract/Datafile.py` (`dump`: a v4 deleted entry is dumped with a `<deleted>` marker)
- Modify: `tests/cronos_builder.py` (deleted v4 records, header deleted counts, a header-count override)
- Test: `tests/test_tad.py`, `tests/test_api_bank.py`, `tests/test_cli_inspect.py`, `tests/test_cronos_builder.py`,
  `tests/golden/api/` (via `--update-golden`)

**Interfaces:**
- Produces: `tad.V4_DELETED_FLAG = 0x02`. A v4 `TadEntry` has `deleted = length == DELETED_LENGTH or bool(flags &
  V4_DELETED_FLAG)` and `inline = bool(flags & ~V4_DELETED_FLAG)`; offset, length and flags are kept as parsed.
- Produces (builder): `DeletedRecord(data: bytes)`, a frozen dataclass; `write_datafile` accepts `bytes | None |
  DeletedRecord` items. For v4, `DeletedRecord` writes the record's data as usual with its entry's flags ORed with
  `0x02` (so `06` inline, `02` extended); `None` for v4 still raises. For v3, `DeletedRecord` raises `ValueError` (v3
  deleted entries keep no length; use `None`). Every `.tad` header's deleted count is the number of deleted entries
  written; the first-deleted field stays 0. `write_raw_datafile` gains `deleted_count: int | None = None` (None: count
  the entries whose length is `DELETED_RECORD_LENGTH` or, for v4, whose offset's top byte has bit `0x02`).

- [ ] **Step 1: Write the failing tests.**
  - `tests/test_tad.py`: `test_a_v4_entry_with_the_deleted_bit_is_deleted` parametrised over flag bytes
    `0x02, 0x06, 0x07` (deleted) and `0x00, 0x04, 0x08, 0x0c` (live), asserting `deleted`, `inline`
    (`flags & ~0x02 != 0`), `offset` and `length` kept.
  - `tests/test_cronos_builder.py`: a v4 `DeletedRecord` writes flag `06` (inline) or `02` (`extended=True`) with its
    data; a v3 `DeletedRecord` raises; the header deleted count equals the deleted entries for v3 (`None`) and v4
    (`DeletedRecord`); `deleted_count=` overrides it.
  - `tests/test_api_bank.py`: `test_a_deleted_v4_record_is_not_read` — a `01.11` database with `[person(),
    DeletedRecord(person()), person()]` (and the same `extended=True`) yields records 1 and 3; the golden cases'
    `golden_records` writes `DeletedRecord(...)` at index 3 for `01.11` instead of leaving it out.
  - `tests/test_cli_inspect.py`: `test_crodump_shows_a_deleted_v4_record_with_its_marker` — `inspect crodump` on that
    database prints record 2's line with its data and ending `<deleted>`; record 1's line has no marker.

- [ ] **Step 2: Run them and see them fail.**

- [ ] **Step 3: Implement.** `tad.py` as the Interfaces say, with the flag comment rewritten from the spec's
  Evidence (bit `0x02` deleted, header counts match in every real file; `04`, `08`, `0c`, `07` unexplained, Phase 3e).
  In `Datafile.dump`, an entry whose length is `DELETED_LENGTH` prints as today; any other deleted entry (v4) is read
  and printed like a live one with ` <deleted>` appended after any `<checksum mismatch>`. The builder as the
  Interfaces say.

- [ ] **Step 4: Update the golden files and check.** `uv run pytest -q --update-golden tests/test_api_bank.py`; `git
  diff tests/golden` must show only the `01.11` files under `tests/golden/api/`, each with record numbers shifted by
  the deleted record now written. `inspect-crodump.stdout` (over `test_data`, v3) must not change. Report anything else.

- [ ] **Step 5: Run everything.** `uv run pytest -q`. A test pinning a built database's full stderr or output may
  change only if Task 1 changed what it builds; report each.

- [ ] **Step 6: Commit** — `Skip v4 records whose .tad entry has the deleted bit`.

---

### Task 2: `OwnKodRequired` (D2)

**Files:**
- Modify: `src/cronos_extract/_api/errors.py`, `src/cronos_extract/__init__.py` (`__all__`, the docstring's errors)
- Modify: `src/cronos_extract/_api/bank.py` (`open()`: the check and its docstring; `OWN_KOD_HINT`)
- Modify: `src/cronos_extract/_cli/report.py` (`error_message` replaces `OWN_KOD_HINT` too)
- Modify: `src/cronos_extract/Database.py` or `_cli/report.py` (the command line's hint text, next to `KOD_HINT`)
- Test: `tests/test_api_open.py`, `tests/test_cli_export.py`, `tests/test_api_public.py`

**Interfaces:**
- Consumes: `FileInfo.generation`, `FileInfo.kod_encoded` (the CroBank `FileInfo` `open()` already has).
- Produces: `class OwnKodRequired(CronosError)`, public. `open()` raises it when `bank_info.generation == "v4"`,
  `bank_info.kod_encoded`, and `kod == DEFAULT_KOD`, after CroBank is opened and before `_load_tables`.

Messages:
- API: `CroBank.dat in {directory} is encrypted with the database's own KOD, which the default KOD would decode as
  garbage. ` + `OWN_KOD_HINT`, where `OWN_KOD_HINT = 'cronos_extract.crack_kod(path, "dbcrack") can recover the
  database\'s KOD.'`
- Command line: `OWN_KOD_HINT` replaced by `export --crack dbcrack uses the KOD that cronos-extract crack dbcrack
  derives.`

- [ ] **Step 1: Write the failing tests.** A helper builds a database whose CroStru is `01.02` from
  `stru_records_from_test_db()` and whose CroBank is `01.11` encoded with `random_kod(seed=1)`, holding `[person(),
  person()]` (compose `write_datafile` calls; add a builder function if two tests need it).
  - `tests/test_api_open.py`: `test_an_own_kod_v4_bank_is_refused_with_the_default_kod` — `open(dbdir)` and
    `open(dbdir, kod=Kod.default())` raise `OwnKodRequired` whose message contains `CroBank.dat` and
    `crack_kod(path, "dbcrack")`; `open(dbdir, kod=Kod.from_table(random_kod(seed=1)))` yields two records;
    `open(dbdir, kod=None)` opens and reports `mismatched_kod` for CroBank.
  - The same file, parametrised negatives (Review Focus 2): an `01.04` CroBank written with `encoded=True` opened with
    the default is not refused (it keeps `test_a_kod_that_…`/`own-kod-read-with-the-default`'s current outcome); an
    unencoded `01.11` CroBank with the default is not refused; `crack_kod(dbdir, "dbcrack")` on the refused database
    does not raise `OwnKodRequired`.
  - `tests/test_api_public.py`: `OwnKodRequired` is in `__all__` and is a `CronosError`.
  - `tests/test_cli_export.py`: `export --jsonl` on the refused database exits 1, its last stderr line is `Error: ` +
    the API message with the command line's hint, and `mismatched_kod` for CroBank precedes it; `inspect strudump` on
    it does not print `Error:` for this reason.

- [ ] **Step 2: Run them and see them fail.**

- [ ] **Step 3: Implement** as the Interfaces say; `error_message` replaces both hints.

- [ ] **Step 4: Run everything**, `git diff tests/golden` empty; commit — `Refuse to read an own-KOD v4 CroBank with
  the default KOD`.

---

### Task 3: `Bank.deleted_records` and the export's note (D3)

**Files:**
- Modify: `src/cronos_extract/_api/bank.py` (`Bank.deleted_records`, the cap and its diagnostic, `open()`'s docstring)
- Modify: `src/cronos_extract/__init__.py` (the docstring)
- Modify: `src/cronos_extract/_cli/export.py` (`Writer.deleted_records`, the note, the call order)
- Modify: `src/cronos_extract/_cli/jsonl_out.py`, `csv_out.py`, `sql_out.py` (the new method)
- Modify: golden files via `--update-golden`
- Test: `tests/test_api_bank.py`, `tests/test_cli_export.py`, `tests/test_cli_characterisation.py`

**Interfaces:**
- Consumes: `Datafile.nrdeleted`, `Datafile.nrofrecords`; Task 1's builder header counts and `deleted_count=`.
- Produces: `Bank.deleted_records -> int` (property). `Writer.deleted_records(count: int) -> None`.

Exact text:
- Note (stderr): `note: CroBank.tad lists {n} deleted records, which are not exported; inspect crodump shows what
  remains of them` (`record` when n is 1).
- JSON Lines: `{"type": "deleted_records", "count": n}`.
- Cap diagnostic: `unexpected_structure`, file `CroBank.dat`: `the .tad header lists {n} deleted records, more than its
  {m} entries`.

- [ ] **Step 1: Write the failing tests.**
  - `tests/test_api_bank.py`: `deleted_records` is 1 for a v3 database with one `None`, 1 for a v4 database with one
    `DeletedRecord`, 0 with none; a `write_raw_datafile(..., deleted_count=999)` CroBank with 2 entries gives 2 and one
    `unexpected_structure` with the message above (Review Focus 3).
  - `tests/test_cli_export.py`: on a built database with one deleted record, `export --jsonl` stderr holds the note once
    (singular), stdout's lines are the open-time diagnostic lines, then `{"type": "deleted_records", "count": 1}`, then
    the first `"type": "table"` line (Review Focus 4); `export --postgres --strict` exits 0 and prints the note; with no
    deleted records there is no note and no line.

- [ ] **Step 2: Run them and see them fail.**

- [ ] **Step 3: Implement.** `open()` reads the CroBank `Datafile`'s `nrdeleted`, caps it and reports as above, and
  stores it on `Bank`. In `export.write`, after `problems.start(writer)` and before `walk`, when the count is nonzero:
  print the note on `sys.stderr` and call `writer.deleted_records(count)`. `JsonlWriter` writes the line; CSV and SQL
  writers do nothing (docstring says why). Update both docstrings.

- [ ] **Step 4: Update the golden files and check.** `uv run pytest -q --update-golden
  tests/test_cli_characterisation.py`; `git diff tests/golden` must show the note (85 records) in every `export-*`
  `.stderr` over `test_data` that reached the tables, and the JSON Lines line in `export-jsonl.stdout`, and nothing
  else. `export-postgres-nokod.stderr` fails before the tables: say whether it gained the note.

- [ ] **Step 5: Run everything** and update tests that pin a full export stderr or JSON Lines output of a database with
  deleted records, only by the note or line (Review Focus 5); list each. Commit — `Report how many deleted records
  CroBank holds`.

---

### Task 4: Realdata checks per file (D4)

**Files:**
- Modify: `tests/test_realdata.py`

- [ ] **Step 1: Implement** D4: `is_v4` from CroBank's header; the `.tad` check over every Cro file whose own header is
  v4, reading all entries in chunks of `TAD_ENTRIES_CHECKED`, asserting no `0xFFFFFFFF` length and header deleted count
  == entries with bit `0x02`; the dbcrack test for every database whose CroBank is v4; the new
  `test_live_records_belong_to_the_tables_the_definition_names` exactly as D4 says (90% of the first 10,000 live
  records; skip with none; the failure message counts ids of tables `undecodable_table` left out); the `V4_CRACK_XFAIL`
  reason left as it is until the controller's run shows which assertion those databases fail (the controller rewrites
  it). Remove nothing else.

- [ ] **Step 2: Verify without real data:** `uv run pytest -q` and `uv run pytest -m realdata --collect-only -q
  tests/test_realdata.py | tail -3` (collection only), linters. Commit — `Check real databases per file and for
  garbage`.

The controller then runs the realdata suite in the background, removes the refused database's fingerprint, rewrites
the xfail reason from the run, and records counts only.

---

### Task 5: Records (D5, D6)

**Files:**
- Modify: `docs/superpowers/specs/2026-09-15-modernisation-roadmap-design.md`,
  `docs/superpowers/specs/2026-09-26-phase3c-bank-reading-design.md` (a dated note under C2),
  `docs/superpowers/plans/2026-09-26-phase3c-bank-reading.md` (a dated correction under Outcome), `CLAUDE.md`

- [ ] **Step 1:** Make D5's corrections and D6's roadmap changes exactly as the spec says; the status line names 3d on
  branch `phase3d-v4-fixes`, pull request pending, and 3c merged as PR #14.
- [ ] **Step 2:** `uv run ruff format --check`; commit — `Record Phase 3d and correct 3c's account of the slow
  database`.

The controller appends this plan's Outcome after the whole-branch review, with the realdata run's length.
