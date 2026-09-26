# Phase 3b: definitions and diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The readers report the problems they survive as `Diagnostic`s with their proper kinds through a required
callback, `inspect` prints them in `export`'s escaped format, CP-1251 decodes with one policy, the reader modules are
annotated, and the `Database` methods only tests use are removed after golden files and local fingerprints replace
their oracle.

**Architecture:** `Diagnostic` and `DiagnosticKind` move to a package-level `_diagnostic.py` that the readers and the
API both import, with a `Reporter` type and one helper that prefixes a table definition's problems with its key.
`Datafile`, `Database` and `TableDefinition` take a required `report: Reporter` in place of `warn`. The API passes its
`DiagnosticLog.record`; `inspect` passes a `Report`'s `diagnostic`.

**Tech Stack:** Python 3.12+, uv, ruff (line length 120), ty (every rule an error), pytest (`filterwarnings = error`),
real files from `tests/cronos_builder.py`.

**Spec:** `docs/superpowers/specs/2026-09-26-phase3b-definitions-diagnostics-design.md` (B1–B7; B7 takes precedence
where it refines an earlier decision). Read it before any task.

## Global Constraints

- Work on branch `phase3b-definitions-diagnostics`. GitHub is `hammersleyfutures/cronos-extract`; its default branch is
  `main` (the local branch is still called `master` and tracks `origin/main`). Always pass
  `-R hammersleyfutures/cronos-extract` to `gh pr` commands.
- Test first for every behaviour change. Real files from `tests/cronos_builder.py` or bytes built in the test; never
  mock.
- One commit per task. Subject in imperative mood, at most 72 characters; body says what and why. Every commit message
  ends with exactly these two lines:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_01W65g7XvoLhDJL4UHJymUtd`
- Commits are GPG-signed by the user's git config. On a signing error, change no git or gpg setting, never use
  `--no-gpg-sign`: stop and report BLOCKED.
- New code files start with two `# ABOUTME: ` lines. Everything touched is fully annotated and ty-clean; values from
  still-unannotated code are narrowed with `int(...)`, `str(...)` or `typing.cast(...)`.
- Names and comments describe what code is, never its history. Never delete a comment unless it is false.
- Before every commit, each checked by exit code: `uv run ruff format`, `uv run ruff check`, `uv run ruff format
  --check`, `uv run ty check`, `uv run pytest -q`. Never pipe a checked command through `tail`. Long runs go in the
  foreground with a timeout, or in the background with the output file read directly; never wait on a notification.
- `export`'s golden files (`tests/golden/export-*`) and every golden stdout file must not change. The only golden file
  that changes in this plan is `tests/golden/inspect-strudump.stderr`, in Task 2, exactly as B7 predicts.
- `local/` holds git-ignored machine-local files naming real datasets: never commit anything from it, never quote a
  path or dataset name from it anywhere; report realdata results as counts only. Tests may read it through
  `tests/test_realdata.py` as they already do, and Task 5 writes `local/realdata-fingerprints.json`.
- When the plan and the code disagree about existing behaviour, follow the code and report it; never loosen an assertion
  to make it pass. A test replaced because its behaviour is abolished is named in the commit body.
- Plain, factual language; avoid critical, crucial, essential, significant, comprehensive, robust, elegant.

## Review Focus

1. **A `report` callback that raises inside `TableDefinition`'s broad `except` blocks** must reach the caller unchanged
   (`DiagnosticLog.guard_callback_errors`). Task 2, `test_a_raising_callback_escapes_the_table_definition_reader`.
2. **`inspect destruct -t 2` on a malformed table definition from stdin** prints its problems as escaped `warning:` lines
   with no file, and exits 0. Task 2, `test_destruct_type_2_reports_problems_as_warning_lines`.
3. **A duplicate definition key holding terminal escapes** is escaped on `inspect strudump`'s stderr. Task 2,
   `test_a_hostile_duplicate_key_is_escaped_on_inspect_stderr`.
4. **`crack strucrack` meeting a CroStru checksum mismatch** prints a `checksum_mismatch` warning, not
   `unexpected_structure`. Task 2, `test_strucrack_reports_a_crostru_checksum_mismatch_by_kind`.
5. **The fingerprint test on a machine with no fingerprint file**, under `-m realdata`, fails naming the command that
   writes it; without `-m realdata` it is never collected. Task 5, the fingerprint test's first branch.

## File Structure

- Create `src/cronos_extract/_diagnostic.py` — `DiagnosticKind`, `Diagnostic` (moved), `Reporter`,
  `for_table_definition`.
- Modify `src/cronos_extract/_api/diagnostics.py` (imports and re-exports the two types), `_api/datafiles.py`
  (`warn_into` and `WARNING_PREFIX` go), `_api/bank.py`, `Datafile.py`, `Database.py`, `Datamodel.py`, `readers.py`,
  `hexdump.py` (`warn_on_stderr` goes), `koddecoder.py`, `kodump.py`, `_cli/inspect.py`, `_cli/crack.py`.
- Create `tests/test_api_golden.py`, `tests/golden/api/*.jsonl`.
- Modify tests: `test_datafile.py`, `test_database.py`, `test_datamodel.py`, `test_api_values.py`,
  `test_cronos_builder.py`, `test_cli_inspect.py`, `test_cli_crack.py`, `test_api_bank.py`, `test_realdata.py`,
  `tests/golden/inspect-strudump.stderr`.
- Docs: `CLAUDE.md`, `tests/cronos_builder.py` (a docstring), the roadmap, this plan.

---

### Task 1: Commit this plan

- [ ] `git branch --show-current` prints `phase3b-definitions-diagnostics`; `uv run ruff format --check
  docs/superpowers/plans/2026-09-26-phase3b-definitions-diagnostics.md` exits 0; commit it with subject "Plan Phase
  3b: definitions and diagnostics" and the two trailer lines.

---

### Task 2: Readers report `Diagnostic`s; `inspect` prints them (B1, B2, B7)

**Files:** create `src/cronos_extract/_diagnostic.py`; modify `_api/diagnostics.py`, `_api/datafiles.py`,
`_api/bank.py`, `Datafile.py`, `Database.py`, `Datamodel.py`, `hexdump.py`, `_cli/inspect.py`, `_cli/crack.py`; tests
as listed below; regenerate `tests/golden/inspect-strudump.stderr`.

**Interfaces produced (later tasks rely on these):**

```python
# src/cronos_extract/_diagnostic.py
class DiagnosticKind(StrEnum): ...        # moved unchanged from _api/diagnostics.py, same members and order
@dataclass(frozen=True)
class Diagnostic: ...                     # moved unchanged
type Reporter = Callable[[Diagnostic], object]
STRU_FILE = "CroStru.dat"
def for_table_definition(report: Reporter, key: str) -> Reporter: ...

Datafile(name, dat, tad, compact, kod, report: Reporter)          # `report` required, replaces `warn`
Database(dbdir, compact, kod, report: Reporter, files=ALL_FILES)  # `report` required, replaces `warn`
Database.from_datafiles(dbdir, compact, kod, stru, bank, report)
TableDefinition(data, image=b"", *, report: Reporter)             # keyword-only, required
```

`_diagnostic.py`:

```python
# ABOUTME: Diagnostic and DiagnosticKind: a problem that reading survived, and the kinds there are.
# ABOUTME: The internal readers report them through a Reporter; the public API re-exports both types.
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum

# (DiagnosticKind and Diagnostic, moved here from _api/diagnostics.py with their docstrings unchanged)

# A callback that receives each problem a reader survives.
type Reporter = Callable[[Diagnostic], object]

STRU_FILE = "CroStru.dat"


def for_table_definition(report: Reporter, key: str) -> Reporter:
    """
    A Reporter for the problems of the table definition stored under `key`, such as "Base001".

    It names CroStru.dat as the file and prefixes each message with the key, as `export` has always shown them, then
    passes the problem to `report`.
    """

    def report_definition_problem(diagnostic: Diagnostic) -> None:
        report(replace(diagnostic, file=STRU_FILE, message=f"{key}: {diagnostic.message}"))

    return report_definition_problem
```

`_api/diagnostics.py` keeps `DiagnosticLog`, `DiagnosticsView`, `RecordNumbers` and imports
`from .._diagnostic import Diagnostic, DiagnosticKind` (re-exported for `cronos_extract/__init__.py` and the other `_api`
modules, which keep importing from `.diagnostics`).

**Each reader's problems (messages are exact: the API already records the unchanged ones with these texts, and
`export`'s golden files depend on them):**

| Where | Kind | Message | Location |
|---|---|---|---|
| `Datafile.readtad` leftover bytes | `UNEXPECTED_STRUCTURE` | `leftover data in .tad` (unchanged) | `file=f"Cro{name}.dat"` |
| `Datafile.readrec`, mismatched chunks | `CHECKSUM_MISMATCH` | `compressed data whose checksum does not match; it is kept` | `file`, `record=recno` |
| `Database.decode_db_definition` duplicate key | `UNEXPECTED_STRUCTURE` | `duplicate key: {keyname}` | `file=STRU_FILE`, `record=1` |
| `Database.decode_db_definition` reference record | `UNEXPECTED_STRUCTURE` | `expected refdata to start with 0x04` | `file=STRU_FILE`, `record=index_or_length` |
| `Database.read_db_definition` | `UNEXPECTED_STRUCTURE` | `expected dbinfo to start with 0x03` | `file=STRU_FILE`, `record=1` |
| `Database.dump_ns1` (both places) | `UNEXPECTED_STRUCTURE` | `NS1 is unexpectedly short` | `file=STRU_FILE` |
| `TableDefinition.decode` (four places) | `UNEXPECTED_STRUCTURE` | today's text without `Warning: ` (e.g. `FieldDefinition Section 2 not marked with a 2`, `Error '{e}' parsing FieldDefinitions`, `FieldDefinition section not terminated`, `Error '{e}' parsing Tabledefinition`) | none (the caller's `for_table_definition` adds file and key) |

`Datafile.readtad` runs during `__init__`, so `self.report` must be set before `readtad` is called (it is: `warn` is set
first today).

**Wiring:**

- `_api/datafiles.py`: delete `warn_into` and `WARNING_PREFIX`; `open_datafile` passes `log.record` to `Datafile`.
- `_api/bank.py`: `TableDefinition(value, image, report=for_table_definition(self._log.record, key))`;
  `Database.from_datafiles(..., log.record)`.
- `Database.dump_db_table_defs`: `TableDefinition(v, image, report=for_table_definition(self.report, k))`; the dead
  `enumerate_tables` (removed in Task 6) passes `report=for_table_definition(self.report, k)` too.
- `Database.recdump`: when the chosen file is None, raise `ValueError(f"no Cro{name}.dat and Cro{name}.tad in
  {self.dbdir}")` (name from the chosen attribute) instead of printing `.dat not found`.
- `_cli/inspect.py`: `open_database` builds `report = Report()` and passes `report.diagnostic` to `Database(...)`;
  `open_component`'s unreadable-file warning uses that same `report` (pass it in) instead of a new `Report()`.
  `run_recdump` checks before dumping: if the chosen file's attribute is None, raise `NotACronosFile(f"{args.dbdir} has
  no Cro{base}.dat and Cro{base}.tad")`. `run_destruct -t 2` builds `TableDefinition(data, report=Report().diagnostic)`.
- `_cli/crack.py`: unchanged (`raw_datafile` already passes a `DiagnosticLog(Report().diagnostic)` whose `record` now
  reaches `Datafile` directly).
- `hexdump.py`: delete `warn_on_stderr`.

**Tests (write first; each asserts nothing is printed with `capfd` where the reader is called directly):**

- `tests/test_datafile.py`: replace `test_leftover_tad_bytes_are_reported_through_the_warn_hook` with one asserting
  `[Diagnostic(DiagnosticKind.UNEXPECTED_STRUCTURE, "leftover data in .tad", file="CroBank.dat")]` (use the file name
  the test writes) and nothing on stderr; delete `test_leftover_tad_bytes_are_printed_without_a_warn_hook`, whose
  behaviour (a reader printing) B1 abolishes, and name it in the commit body. Rename
  `test_readrec_reports_a_checksum_mismatch_through_warn` to `..._through_report` and expect
  `[Diagnostic(DiagnosticKind.CHECKSUM_MISMATCH, "compressed data whose checksum does not match; it is kept",
  file="CroStru.dat", record=1)]`.
- `tests/test_database.py`: `test_a_duplicate_definition_key_is_reported_through_the_warn_hook` becomes
  `..._through_report`, expecting `[Diagnostic(DiagnosticKind.UNEXPECTED_STRUCTURE, "duplicate key: BankName",
  file="CroStru.dat", record=1)]`. Add `test_a_reference_record_not_starting_with_4_is_reported`: take
  `stru_records_from_test_db()`, append a record `b"\x05value"` as record N, append a key referencing it to record 1
  (a by-reference value has the high bit of its length clear: `bytes([len(name)]) + name + struct.pack("<L", N)`),
  write it with `write_datafile`, and expect `Diagnostic(DiagnosticKind.UNEXPECTED_STRUCTURE, "expected refdata to
  start with 0x04", file="CroStru.dat", record=N)`.
- `tests/test_datamodel.py`: `TableDefinition(erdgeist_table_definition(), report=problems.append)` records
  `Diagnostic(DiagnosticKind.UNEXPECTED_STRUCTURE, "FieldDefinition Section 2 not marked with a 2")`; with
  `report=for_table_definition(problems.append, "Base001")` it records file `CroStru.dat` and message `Base001:
  FieldDefinition Section 2 not marked with a 2`.
- `tests/test_api_diagnostics.py`: `test_a_raising_callback_escapes_the_table_definition_reader` — a diagnostic
  callback that raises a test-local exception class on the first `unexpected_structure` makes `cronos_extract.open`
  of TEST_DB raise that exception (TEST_DB's table definitions yield `FieldDefinition Section 2 not marked with a 2`).
  Use the callback parameter name `open` actually has.
- `tests/test_cli_inspect.py`:
  - The two tests asserting `WARN: expected dbinfo to start with 0x03` (near lines 115 and 254) now expect
    `warning: unexpected_structure: CroStru.dat record 1: expected dbinfo to start with 0x03`. So does
    `tests/test_cronos_builder.py` near line 144 while it still reads stderr (it moves to the API in Task 6).
  - `test_a_short_ns1_is_reported_as_a_warning_line`: TEST_DB already has an `NS1` key, so rename it first, as
    `database_with_files_abbreviation` renames `Base000`: `dbinfo.replace(b"\x03NS1", b"\x03XS1")` (assert the count
    is 1), then `definition_with_extra_key(..., "NS1", b"\x01")`; `inspect strudump` exits 0 and its stderr holds
    `warning: unexpected_structure: CroStru.dat: NS1 is unexpectedly short`.
  - `test_destruct_type_2_reports_problems_as_warning_lines`: `erdgeist_table_definition().hex()` on stdin to
    `inspect destruct -t 2` exits 0 and prints `warning: unexpected_structure: FieldDefinition Section 2 not marked
    with a 2` on stderr.
  - `test_a_hostile_duplicate_key_is_escaped_on_inspect_stderr`: apply `definition_with_extra_key(dbinfo,
    "X\x1b[31m", b"a")` twice to TEST_DB's record 1 and write it with `write_datafile`; `inspect strudump`'s stderr
    holds the duplicate-key line with the key escaped as `_cli/report.py`'s `escape` escapes ESC, and no ESC byte.
  - `test_recdump_of_an_absent_file_fails_naming_it`: `inspect recdump` choosing CroSys on a database written without
    CroSys exits 1 with stderr `Error: <dbdir> has no CroSys.dat and CroSys.tad`; this replaces the `.dat not found`
    print (spec B7). Use the flag `recdump` actually has for choosing the file.
- `tests/test_cli_crack.py`: `test_strucrack_reports_a_crostru_checksum_mismatch_by_kind` — `strucrack` reads a
  record through `readrec` for each `--text` (see `_cli/crack.py`). Write a CroStru with `write_datafile(dir, "Stru",
  records, kod=None)` whose records are TEST_DB's plus one `compressed_record(b"x" * 40, wrong_checksums={0})`, run
  `crack strucrack` with a `--text` naming that record (0-based, format in `TEXT_FORMAT`) and plaintext `x`, and
  assert a stderr line starts `warning: checksum_mismatch: CroStru.dat record ` and no line holds
  `unexpected_structure`. Follow what the code does and report any difference.
- Every other test that builds a `Datafile`, `Database` or `TableDefinition` directly passes `report=` a list's
  `append` (or `lambda diagnostic: None` where problems are irrelevant): `tests/test_database.py`,
  `tests/test_cronos_builder.py`, `tests/test_api_values.py`, `tests/test_api_bank.py`, `tests/test_cli_inspect.py`,
  `tests/test_realdata.py`, `tests/cronos_builder.py`. Run `rg -n 'Database\(|Datafile\(|TableDefinition\(|warn=' src
  tests` to find them all.

**Golden:** regenerate with `uv run pytest -q tests/test_cli_characterisation.py --update-golden`, then `git diff --
tests/golden` must show only `inspect-strudump.stderr` changing from the two `Warning: FieldDefinition Section 2 not
marked with a 2` lines to `warning: unexpected_structure: CroStru.dat: Base000: FieldDefinition Section 2 not marked
with a 2` and the same line for `Base001`. Anything else is a bug; stop and report it.

- [ ] Steps: write the tests; run them and see them fail; implement; run the focused files, the characterisation tests
  and the full suite; regenerate and check the golden diff; commit with subject "Report reader problems as diagnostics
  with their kinds" and a body naming B1, B2, B7 and the replaced test.

---

### Task 3: One CP-1251 policy (B3)

**Files:** modify `src/cronos_extract/readers.py`, `Datamodel.py`, `Database.py`, `hexdump.py` (a comment); tests in
`tests/test_readers.py`, `tests/test_datamodel.py`, `tests/test_api_values.py`, `tests/test_database.py`.

```python
# readers.py
def decode_cp1251(data: bytes) -> str:
    """`data` decoded as CP-1251; the one byte CP-1251 leaves undefined (0x98) becomes U+FFFD, so decoding never fails."""
    return data.decode("cp1251", "replace")
```

Use it in `ByteReader.readlongstring` and `readname`, in `Datamodel.TableImage` (file name), in `Datamodel.Field` (every
`decode("cp1251", "ignore")`: dates, times, file references, text), and for the NS1 password in `Database.dump_ns1`. In
`hexdump.strescape`, add a comment that it only receives values `Database.dump_db_definition`'s regex has let through,
which cannot hold `0x98`, so its strict decode cannot fail.

**Tests first:** `decode_cp1251(b"a\x98b") == "a�b"`; a text field holding `0x98` reads back with U+FFFD through
`cronos_extract.open()` (it was dropped); a file reference whose record number is `b"1\x98"` gives `FileReference.record
is None` (it resolved to 1 before) — state this change in the commit body; `inspect strudump` of a database whose NS1
password holds `0x98` exits 0 and prints the password with U+FFFD (build the NS1 value with the default KOD's `encode`,
as `Database.dump_ns1` decodes it).

- [ ] Commit subject "Decode CP-1251 with one policy that never drops a byte".

---

### Task 4: Annotate the reader modules (B4)

**Files:** `src/cronos_extract/readers.py`, `Datamodel.py`, `Database.py`, `hexdump.py`, `koddecoder.py`, `kodump.py`.

Annotate every function, method and attribute; `TableDefinition`'s `image` defaults to `b""`. Remove the casts in
`_api` and `_cli` that `ty` then reports as redundant (`redundant-cast`). No behaviour changes: the full suite and the
golden files pass unchanged. `uv run ty check` clean.

- [ ] Commit subject "Annotate the reader modules".

---

### Task 5: API golden files and realdata fingerprints (B5, B7)

**Files:** create `tests/test_api_golden.py` and `tests/golden/api/*.jsonl`; modify `tests/test_api_bank.py`,
`tests/test_realdata.py`.

- Move the parity records into a function in `tests/test_api_bank.py`, `parity_records(version: bytes) -> list[bytes |
  None]` (the list the parity test builds today, including the `None` inserted for versions other than `01.11`), used by
  both tests.
- `tests/test_api_golden.py`, parametrised over `PARITY_CASES` × `extended` in `(False, True)`, writes the database with
  `write_database(dir, parity_records(version), kod, version=version, extended=extended)`, opens it through the API with
  the matching KOD, and renders one JSON line per record: `{"table_id": ..., "table": ..., "record": ..., "fields":
  [texts]}` (`json.dumps(..., ensure_ascii=False, sort_keys=True)`), compared with
  `tests/golden/api/{version}-{kod or default}-{inline or extended}.jsonl` through the `golden` fixture (one file per
  case; the plan chooses this over sharing files between KOD variants, which the spec allowed, because it keeps each
  file's origin obvious).
- The existing parity test in `tests/test_api_bank.py` gains a second assertion: the rendered API output equals the
  golden file for that case (inline). This records in the history that the golden files equal `enumerate_records`'
  output.
- `tests/test_realdata.py`: add `FINGERPRINTS = LIST_FILE.parent / "realdata-fingerprints.json"` and

```python
def api_fingerprint(dbdir: Path) -> dict[str, object]:
    """The record count and a SHA-256 of the API's field texts for the records the parity test compares."""
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
    if not bank_is_small(dbdir):
        pytest.skip("CroBank is too large to walk once per table")
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
```

- **Generate the fingerprints now, while the parity test still passes** (the removal is Task 6): run
  `uv run pytest -q -m realdata tests/test_realdata.py -k "fingerprint or field_text" --update-golden` then the same
  without `--update-golden`, each in the background with its output file read directly (tens of minutes). Report counts
  only. `local/realdata-fingerprints.json` is git-ignored — confirm with `git status` that it is not listed.

- [ ] Commit subject "Pin the API's output with golden files and local fingerprints".

---

### Task 6: Remove the dead `Database` methods (B5)

**Files:** `src/cronos_extract/Database.py`; tests `tests/test_api_bank.py`, `tests/test_realdata.py`,
`tests/test_cronos_builder.py`, `tests/test_database.py`; `tests/cronos_builder.py` (the docstring of
`database_with_wrong_kod_record_out_of_range`).

- Delete `Database.enumerate_tables`, `enumerate_records`, `enumerate_files`, `incomplete_records`, `files_tableid`,
  `get_record`, `readbankrec_or_raise`, `readbankrec`, and imports that become unused (`base64`, `cached_property`,
  `Record`, `ashex`, ...).
- Delete `tests/test_api_bank.py::test_field_text_matches_database_enumerate_records` and
  `tests/test_realdata.py::test_field_text_matches_database_enumerate_records`: their oracle is gone; the golden files
  and fingerprints of Task 5 replace them. Name both in the commit body. Update `tests/test_api_bank.py`'s ABOUTME.
- Move the builder's tests (`tests/test_cronos_builder.py`) and `tests/test_database.py`'s
  `test_enumerate_tables_names_the_missing_crostru_files` from the removed methods to the API: `cronos_extract.open()`,
  `bank.tables`, `table.records()`, `bank.read_file(field.value)`; a missing CroStru is `NotACronosFile` naming the
  files. Keep each test's assertions about the database content.
- `rg -n 'enumerate_(tables|records|files)|incomplete_records|files_tableid|get_record|readbankrec' src tests` finds
  nothing afterwards.
- Run the fingerprint test once more (`-m realdata -k fingerprint`, background): all pass or skip as before.

- [ ] Commit subject "Remove the Database methods only tests used".

---

### Task 7: Documentation

- `CLAUDE.md`: the readers report `Diagnostic`s through a required `report` callback (`_diagnostic.py`, `Reporter`,
  `for_table_definition`); `inspect` prints them through `_cli/report.py`; CP-1251 decodes through
  `readers.decode_cp1251` with `replace`; remove the sentences about `warn` hooks, `enumerate_*`, `incomplete_records`
  and `Database.readbankrec`; the realdata fingerprints file under `local/`.
- The roadmap: status line (3b implemented on its branch, PR pending); in "Open items carried forward" mark done the
  items this phase closes (the `inspect` warning wording, CP-1251 policies, the dead methods and the parity tests, tables
  with ids above 255 and the Files table header as closed without code, the CroStru checksum mismatch's kind) and add
  any new ones the implementation found.
- [ ] `uv run ruff format --check README.md CLAUDE.md docs`; commit "Document the readers' diagnostics and CP-1251
  policy".

### Task 8: Outcome

- [ ] Add an Outcome section at the end of this plan: commits, test counts on `master` and the branch, the golden diff
  of Task 2, the realdata counts of Tasks 5 and 6 (counts only), every divergence from the plan and its ruling, and a
  "Final review" subsection holding "Recorded after the whole-branch review."; commit "Record the Phase 3b outcome".

## Outcome

Implemented on branch `phase3b-definitions-diagnostics` in 18 commits after the plan (`fcc83ef`..`da7dcaf`, plus this
record), subagent-driven: an implementer and a task review per task, then a whole-branch review.

- **Tests:** 841 passed on `main` (`ca0622c`), 874 on the branch (10 realdata tests deselected in both). ruff, ty and
  format checks clean.
- **Golden files:** `inspect-strudump.stderr` changed as Task 2 predicted, from two `Warning: FieldDefinition Section 2
  not marked with a 2` lines to `warning: unexpected_structure: CroStru.dat: Base000: ...` and the same for `Base001`.
  `export-postgres-nokod.stderr` changed too, which spec B1 said would not happen: its dbinfo warning now reads
  `CroStru.dat record 1: expected dbinfo to start with 0x03`, because the plan's table puts `record=1` on that
  diagnostic and on the duplicate key (ruled in Task 2: the location is more precise). `tests/golden/api/` holds 12 new
  files.
- **Realdata (counts only):** fingerprints written and checked in Task 5, 38 passed and 22 skipped in each run (12
  skips for CroBank too large to walk per table, 10 for databases that do not open with the default KOD). After the
  removal in Task 6, the fingerprint test alone: 19 passed, 11 skipped, 0 failed.

### Divergences from the plan and their rulings

- Task 2: `record=1` on the dbinfo and duplicate-key diagnostics, with the golden line above and two assertions
  updated; `tests/test_api_datafiles.py`'s `warn_into` test replaced by a `for_table_definition` test; two unlisted
  tests adjusted (`test_api_public.py` for the moved types, and the damaged-file `inspect` test, which now pins three
  `warning:` lines). The raising-callback test passed before the change: the API already guarded callbacks.
- Task 4: typing `Database.stru` and `.bank` as `Datafile | None` exposed a traceback on `main`: `inspect destruct -t 1`
  without CroStru, given a key stored by reference. Fixed in `e765239` (an `Error:` line), with an explicit CroStru
  check in `read_db_definition` and `Bank` taking the CroBank `Datafile` directly instead of a cast.
- Task 5: one golden file per case, as the plan chose; the extended-layout files are byte-identical to the inline ones,
  which the parity test compared with `enumerate_records`.
- Task 6: the parity helpers were renamed after the golden cases, and the three copies of the `prints_nothing` fixture
  became one in `tests/conftest.py`, applied to the golden test so the removed parity test's silence check survives.
- Task 7: the roadmap's status line also recorded Phases 2 and 3a as merged (PRs #11 and #12).

### Final review

Recorded after the whole-branch review (Fable, `ca0622c..8799fc8`): ready to merge with fixes. One Important finding,
from `main`: `inspect strudump` raised a traceback (`EOFError`) on a truncated table definition, where `export` reports
`undecodable_table` and goes on. Fixed in `5fcd991` the same way as `export`, sharing its message. Minor findings fixed:
the `Diagnostic` docstring now promises only that a message never holds CroBank record data (`79bff8f`); `crack
strucrack` prints each diagnostic once (`606e8d7`); `inspect destruct` requires `-t 1|2|3` and ends bad input with one
`Error:` line (`ed10bbe`); strudump and the API decide table keys with one `is_table_key` (`4cc6ec9`); tests for every
reachable reader diagnostic and for `inspect crodump` printing one (`da7dcaf`). A scoped re-review approved the fixes.

Left for Ben: `TableDefinition.decode`'s `Error '...' parsing Tabledefinition` branch cannot run (its try block raises
only `EOFError`, handled first), so it has no test; and `inspect destruct -t 3` prints nothing for a CroSys record of
type 3, because `destruct_sys3_def` is an empty stub on `main` too.
