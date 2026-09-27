# Phase 3e: the v4 header's KOD check — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Check a KOD exactly against a v4 file's header, refuse one the header rejects, never crack a KOD that
decodes garbage, read flag-`08` v4 records as extended, and record the research.

**Architecture:** `_format/header.py` reads 8 check bytes; `koddecoder.kod_fits_header` decides; `select_kod`,
`open()` (raising `WrongKod`, which replaces `OwnKodRequired`) and the crack paths use it; `_format/tad.py`'s v4 inline
rule becomes bit `0x04`.

**Tech Stack:** Python 3.12+, pytest, ruff, ty, uv.

**Spec:** `docs/superpowers/specs/2026-09-27-phase3e-v4-header-kod-design.md` (E1–E6, Evidence). Read it before any
task; where this plan and the spec disagree, the spec wins and the divergence is reported.

## Global Constraints

- Every code file keeps its two `ABOUTME: ` lines; update them when a file's job changes.
- `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check` and `uv run ty check` are clean before every
  commit. pytest runs with `filterwarnings = error`.
- Tests build databases with `tests/cronos_builder.py`; no mocks, no stubs returning fake data.
- Commit messages: imperative, subject ≤ 72 characters, ending with exactly one trailer line:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never `git checkout -- <file>` or `git stash`; copy a file aside and restore it by hand.
- Never open, quote or commit entries of `local/mash_datasets_with_CroIndex_dat.txt`; do not run `-m realdata` (the
  controller runs it).
- A golden file changes only by `uv run pytest --update-golden`; `git diff tests/golden` shows only the change the task
  names.
- Diagnostic and error messages never hold record content.

## Review Focus

1. A KOD-encoded v4 CroStru or CroBank with a wrong KOD, given or default, raises `WrongKod`; one the header accepts
   (including the default table) opens; `kod=None`, unencoded v4 files, v3 and `01.04`/`01.05` are never checked.
2. A v4 file shorter than 27 bytes: `kod_fits_header` is None, nothing is refused, nothing crashes.
3. The builder's v4 headers pass the check with the file's KOD, so no existing KOD-encoded v4 test database starts
   raising `WrongKod`.
4. The crack commands' output and exit codes when the derived KOD fails the check, with and without `--silent`,
   `--noninteractive` and `--sys`.
5. The inline rule for flags never seen (`01`, `03`, `05`, `09`) is extended, and realdata fails on an unseen flag.

---

### Task 1: The header check and the builder's v4 headers (E1)

**Files:** `src/cronos_extract/_format/header.py`, `src/cronos_extract/koddecoder.py`, `src/cronos_extract/Datafile.py`,
`tests/cronos_builder.py`; tests in `tests/test_header.py`, `tests/test_koddecoder.py`, `tests/test_cronos_builder.py`.

**Interfaces (produces):** `DatHeader.kod_check: bytes = b""`; `header.read_kod_check(file: BinaryIO) -> bytes` (up to
8 bytes at offset 19); `Datafile.header` carries them; `koddecoder.kod_fits_header(header: DatHeader, kod: KODcoding)
-> bool | None` (None unless `header.generation == "v4"` and 8 check bytes; else `kod.decode(0, header.kod_check) ==
bytes(8)`); builder `write_raw_datafile(..., kod: Sequence[int] | None = None)` writes `KODcoding(kod or
INITIAL_KOD).encode(0, bytes(8))` at offset 19 for v4 versions (v3 unchanged), and `write_datafile` passes its KOD.

- [ ] Failing tests: `read_kod_check` on a file with 27+ bytes and on a shorter one; `kod_fits_header` True with the
  file's KOD, False with another, None for v3 and for a short v4 file; a built `01.11` file (with `kod=random_kod(1)`,
  and unencoded) decodes bytes 19–26 to zeros with its KOD (Review Focus 3); `Datafile.header.kod_check` is set.
- [ ] Implement; run everything; `git diff tests/golden` empty (golden API files are text, built headers change no
  output); commit `Check a KOD against a v4 file's header`.

---

### Task 2: `WrongKod` replaces `OwnKodRequired` (E2)

**Files:** `koddecoder.py` (`select_kod`), `_api/errors.py`, `_api/bank.py` (`open()`, hints), `_cli/report.py`
(`error_message`), `__init__.py`; tests in `tests/test_koddecoder.py`, `tests/test_api_open.py`,
`tests/test_api_public.py`, `tests/test_cli_export.py`, `tests/test_cli_report.py`, `tests/test_cronos_builder.py`.

**Interfaces:** consumes Task 1's `kod_fits_header`. Produces `class WrongKod(CronosError)`; API hints
`STRU_KOD_HINT` (`cronos_extract.crack_kod(path, "strucrack") can recover the database's KOD.`) and `BANK_KOD_HINT`
(the same with `"dbcrack"`); command-line replacements naming `export --crack strucrack` / `--crack dbcrack` and
`cronos-extract crack strucrack` / `crack dbcrack`. Message: `Cro<Stru|Bank>.dat in {directory} has a header that
shows the KOD given is not the database's KOD. ` + hint. `select_kod`'s new message: `the file's header shows that the
KOD given is not its KOD`.

- [ ] Failing tests (Review Focus 1, 2): `select_kod` rows for a KOD-encoded v4 header that accepts / rejects the KOD
  and for `kod=None`, and a short-header v4 file falling back to 3c's rows; `open()` raises `WrongKod` for a wrong given
  KOD and for a wrong default, on CroStru and on CroBank, CroStru checked first; a `01.11` database encoded with the
  default table opens with the default KOD (refused under 3d); the mixed database (`database_with_own_kod_v4_bank`)
  opens with its own KOD and raises `WrongKod` with the default; `kod=None` opens the unencoded-CroStru variant with its
  warning; `crack_kod` and `inspect` never raise it; `WrongKod` in `__all__`; `export` subprocess tests pin the full
  stderr for each hint (the `mismatched_kod` warning, the summary, the `Error:` line).
- [ ] Implement. Remove `OwnKodRequired`, `OWN_KOD_HINT` and the 3d header-flag check; move their tests to the new rule;
  restore the `01.11` case of the builder test Task 2 of 3d dropped (a default-encoded v4 CroBank now opens).
- [ ] Run everything; commit `Refuse a KOD a v4 file's header rejects`.

---

### Task 3: Crack checks its result (E3)

**Files:** `_api/crack.py`, `_cli/crack.py`; tests in `tests/test_api_crack.py` (or wherever `crack_kod` is tested),
`tests/test_cli_crack.py`.

- [ ] Failing tests (Review Focus 4): `crack_kod` on a v4 database built so its statistics resolve to a permutation
  that is not its KOD returns None (build it by writing CroStru records that crack to a wrong but complete table, or,
  if that cannot be built, by a v4 database whose header was written with a different KOD than its records — say which
  in the report); `crack strucrack` prints `the recovered KOD does not fit CroStru.dat's header, so it is not the
  database's KOD` on stderr, exits 0 interactively and 1 with `--noninteractive`, prints only the KOD with `--silent`;
  the same for `--sys` naming `CroSys.dat`; `crack dbcrack` names `CroBank.dat` and exits 1. A database whose crack is
  right is unaffected (existing tests).
- [ ] Implement; run everything; commit `Reject a cracked KOD that a v4 header rejects`.

---

### Task 4: The v4 inline bit (E4)

**Files:** `src/cronos_extract/_format/tad.py`; tests in `tests/test_tad.py`, `tests/test_api_bank.py` or
`tests/test_datafile.py`; builder if it needs flag `08`.

- [ ] Failing tests (Review Focus 5): the layout test's inline column is `bool(flags & 0x04)` for `00, 01, 02, 03, 04,
  05, 06, 07, 08, 09, 0c` (literal expected booleans, not the expression); a built v4 database with a flag-`08` extended
  record (the builder's extended v4 flag byte made a parameter, or `write_raw_datafile`) reads back whole.
- [ ] Implement with the comment stating the evidence and its limits (spec Evidence, Flag bits); run everything;
  `git diff tests/golden` empty; commit `Read a v4 entry as inline only when bit 0x04 is set`.

---

### Task 5: Realdata and records (E5)

**Files:** `tests/test_realdata.py`, `docs/cronos-research.md`,
`docs/superpowers/specs/2026-09-15-modernisation-roadmap-design.md`,
`docs/superpowers/specs/2026-09-26-phase3d-v4-fixes-design.md` (a dated note under D2), `CLAUDE.md`.

- [ ] `tests/test_realdata.py`: E5's three assertions (a), (b), (c). For (b), use `_api/crack.py`'s
  `bank_and_index_xref` and `kod_from_xref` (and `kod_is_resolved`) on the Datafiles directly, before any header check.
  Verify with `uv run pytest -q` and `--collect-only` only.
- [ ] Records: `docs/cronos-research.md`'s v4 section gains the Evidence (header block and check, `Base000` constancy
  and the 78 entries alignment recovered, flag bits with evidence and limits, flag `03` unseen); the roadmap marks 3e
  done, adds the known-plaintext solver as a phase before 1.0 with the Evidence as its brief, and updates the status
  line (3d merged as PR #15; 3e on branch `phase3e-v4-header-kod`, pull request pending); `CLAUDE.md`'s KOD section
  describes the header check and `WrongKod` (replacing its `OwnKodRequired` text); the 3d spec's D2 gains
  "(2026-09-27) Replaced by Phase 3e's E2: `WrongKod` and the header check.".
- [ ] `uv run ruff format --check`; commits `Check the v4 header evidence on real databases` and `Record Phase 3e`.

The controller runs the realdata suite in the background afterwards and appends the Outcome.

## Outcome

Implemented on branch `phase3e-v4-header-kod` in 11 commits after the plan (`6978ed1`..`bacd62f`, plus this record),
subagent-driven: an implementer and a task review per task, then a whole-branch review by Fable and one fix.

- **Tests:** 946 passed on `main` (`359e94d`), 1,021 on the branch (14 realdata tests deselected); ruff, format and ty
  clean; `tests/golden/` unchanged.
- **Realdata (counts only):** the full run at `b45248f` took 9,278 s (2 h 35 min): 221 passed, 79 skipped, 5 xfailed,
  none failed. The three new evidence tests passed on every database they apply to: the default KOD fails the header
  check of every v4 file, encoded or not; every whole permutation dbcrack's statistics produce passes CroBank's header
  check; every v4 `.tad` flag byte is one of `00`, `02`, `04`, `06`, `07`, `08`, `0c`.

### Divergences from the plan and their rulings

- Task 1: the `Datafile` test lives in `tests/test_datafile.py`; `Datafile.readdathdr`'s "random bytes" docstring was
  corrected for v4 in Task 5.
- Task 2: both messages say "the KOD used", not "the KOD given", because the default is usually not given (fix round);
  a `kod=None` test on a KOD-encoded v4 CroStru was added; the builder test's `01.11` case, dropped in 3d, is restored,
  since a default-table v4 CroBank now opens with the default KOD.
- Task 3: the test database is a crackable v4 database whose check bytes were rewritten with another KOD (a new builder
  helper, `write_kod_check`), since a database whose statistics resolve to a wrong permutation could not be built. A
  KOD the header rejects is handled like an unresolved crack: its table on stderr, nothing on stdout, `--silent` prints
  nothing (fix round). The `export --crack` test pins a crack that returns None; a crack that succeeds and is then
  refused by `open()` needs two v4 files with different KODs, which no real database has.
- Task 5: the known-plaintext solver is named Phase 3f; the 3c spec gained a dated note, and one README sentence names
  the KOD among the reasons an export stops.

### Final review

Fable, `359e94d..b45248f`: ready to merge. Hostile probes (garbage check bytes, CroBank truncated to 19–28 bytes, an
unencoded v4 CroStru with an own-KOD CroBank, `--kod` of the default's hex, `--nokod`, flags `01`/`03`/`05`/`09`/`08`,
`inspect` on a refused database) all ended in `WrongKod`, a `DatabaseDefinitionError` with the crack hint, or a
`corrupt_record`; no crash and no silent garbage. One fix landed before merge: a test that the builder writes flag
`08` in a v4 entry (`bacd62f`), since the flag-`08` read test would also pass with flag `00`; a scoped re-review found
it addressed. Minors left: no subprocess test of a successful `export --crack dbcrack` on a v4 database; the name of
`open()`'s check helper reads as a sentence.
