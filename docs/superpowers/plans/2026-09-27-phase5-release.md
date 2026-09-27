# Phase 5: the 1.0 release — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make cronos-extract 1.0 ready to publish: settle the API items 1.0 freezes, decode KOD fast, add
`--version` and the release workflow, and write the API reference, README and changelog in simple technical English.

**Architecture:** Small changes to `_api/info.py`, `_format/header.py`, `koddecoder.py` and `cli.py`; a new
`.github/workflows/release.yml`; new `docs/api.md` and `CHANGELOG.md`; a rewritten `README.md`. Publishing itself
happens after the pull request, on a tag, with Ben.

**Tech Stack:** Python 3.12+, uv, pytest, ruff, ty, GitHub Actions, PyPI trusted publishing.

**Spec:** `docs/superpowers/specs/2026-09-27-phase5-release-design.md` (R1–R7). Read it before any task; where this plan
and the spec disagree, the spec wins and the divergence is reported.

## Global Constraints

- Every code file keeps its two `ABOUTME: ` lines; update them when a file's job changes.
- `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check` and `uv run ty check` are clean before every
  commit. pytest runs with `filterwarnings = error`.
- Tests build databases with `tests/cronos_builder.py`; no mocks.
- Commit messages: imperative, subject ≤ 72 characters, ending with exactly these two trailer lines:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_01W3bjSjqEbhhfZJuXQPrE5U`.
- Never `git checkout -- <file>` or `git stash`. Never push, tag, or change anything on GitHub or PyPI.
- Never open, quote or commit entries of `local/mash_datasets_with_CroIndex_dat.txt`; do not run `-m realdata`.
- A golden file changes only by `uv run pytest --update-golden`; `git diff tests/golden` shows only the change the task
  names.
- **Documentation tasks (4, 5, 6):** follow `/home/ben/.claude/skills/simple-english/SKILL.md` in pragmatic mode, and
  run its self-check and `/home/ben/.claude/skills/simple-english/references/checklist.md` before committing. One term
  per concept across all three documents: "make sure that" for the check family; "database" for a CronosPro database
  (not "bank", except the API's `Bank` class); "table", "record", "field", "KOD", "diagnostic" as the API names them.
  No "should", "may", "might", "could", "would" or semicolons. Code, identifiers, commands and quoted messages
  unchanged.

## Review Focus

1. A `FileInfo` for a file of an unknown or v7 version (generation set, `problem` None) is valid.
2. Fast `decode` equals the per-byte formula at every shift, including shifts above 255 and empty data.
3. The release workflow fails before building when the tag and the package version differ, and only the publish job
   can request an OIDC token.
4. Every README command example runs from a checkout; no README link is relative.
5. `docs/api.md` names every `__all__` entry and every `DiagnosticKind`.

---

### Task 1: What 1.0 freezes (R1)

**Files:** `src/cronos_extract/_api/info.py`, `src/cronos_extract/_format/header.py`, `src/cronos_extract/__init__.py`;
tests in `tests/test_api_info.py`, `tests/test_api_public.py`.

- [ ] Failing tests: `FileInfo` with `problem` and all header fields None is valid; with `problem` None and all set is
  valid (including `generation="unknown"` and `"v7"`); a mix in either direction raises `ValueError`;
  `typing.get_args(cronos_extract.Generation) == ("v3", "v4", "v7", "unknown")`; `Generation` in `__all__`.
- [ ] Implement `FileInfo.__post_init__` and the plain alias; re-export `Generation`; update the package docstring if
  it lists public names. Run everything; commit `Settle FileInfo's invariant and make Generation public`.

---

### Task 2: Fast KOD decoding (R2)

**Files:** `src/cronos_extract/koddecoder.py`; tests in `tests/test_koddecoder.py`.

- [ ] Failing tests (Review Focus 2): for random data at lengths 0, 1, 7, 8, 9, 255, 256, 257, 4096, 12288 and shifts
  0, 1, 255, 256, 1000, `decode` and `encode` equal the per-byte formulas (write the reference formulas in the test)
  and `decode(o, encode(o, d)) == d`. They pass today; keep them as the guard.
- [ ] Measure, in a throwaway script, the per-byte code, the slice-translate method and the big-int lane method at 100
  bytes, 1 KB and 12 KB, and pick the fastest per length (a length threshold if the winner changes). Implement it with
  precomputed tables built once per `KODcoding`. `try_decode` unchanged.
- [ ] Measure the time to read all tables of a built database of 100,000 KOD-encoded records of about 1 KB (`01.04`
  with `random_kod(seed=1)`, or `01.11` with its KOD) before and after, and the per-record times; put the numbers in
  the report. Run everything; commit `Decode KOD without a Python loop over bytes`.

---

### Task 3: Release mechanics (R4)

**Files:** `pyproject.toml`, `src/cronos_extract/cli.py`, `.github/workflows/ci.yml`, `.github/workflows/codeql.yml`,
`.github/workflows/release.yml` (new); tests in `tests/test_cli.py` (or where `main` is tested).

- [ ] Failing test: `cronos-extract --version` prints `cronos-extract 1.0.0` and exits 0 (subprocess, `run_command`).
- [ ] `pyproject.toml`: version `1.0.0`; classifier `Development Status :: 5 - Production/Stable`; URLs `Documentation`
  (`https://github.com/hammersleyfutures/cronos-extract/blob/main/docs/api.md`) and `Changelog` (`…/CHANGELOG.md`).
  Update `uv.lock` with `uv lock`.
- [ ] `--version` via `importlib.metadata.version("cronos-extract")`.
- [ ] `ci.yml` and `codeql.yml`: `push: branches: [main]`.
- [ ] `release.yml` exactly as R4 describes (three jobs; permissions per job; version check before build; tests from
  the checkout; `uv publish --trusted-publishing always`; GitHub Release with the CHANGELOG entry and `dist/` files).
  Look up the current stable versions of each action (`actions/checkout`, `astral-sh/setup-uv`,
  `actions/upload-artifact`, `actions/download-artifact`, and the release step you choose, preferably `gh release
  create` with `GH_TOKEN` so no extra action is needed) and pin them as `ci.yml` does. Extract the CHANGELOG section
  with a small shell or Python step; check the workflow with `actionlint` if available (`uvx` or the binary), else say
  so. Run everything; commit `Add the 1.0 version, --version and the release workflow`.

---

### Task 4: `docs/api.md` (R3)

**Files:** `docs/api.md` (new); test in `tests/test_api_public.py`.

- [ ] Failing test (Review Focus 5): every name in `cronos_extract.__all__` and every `DiagnosticKind` value appears in
  `docs/api.md` as inline code.
- [ ] Write it from the code (docstrings, `__init__.py`'s promises, `_api/*`), per R3's list, in simple technical
  English (Global Constraints). Descriptive sections per object; one short procedural example at the top (open a
  database, read records, handle diagnostics) that the test also runs, or that matches an existing test. Run the
  skill's self-check and checklist; list its results in the report. Commit `Document the 1.0 API`.

---

### Task 5: The README (R3)

**Files:** `README.md` (rewritten); a test, e.g. `tests/test_readme.py`.

- [ ] Failing test (Review Focus 4): each shell command in the README's fenced `bash` blocks that starts with
  `cronos-extract` runs (subprocess, from the repository root, against `test_data`, into `tmp_path` where it writes)
  and exits as the README says; install lines are skipped; no Markdown link target is relative.
- [ ] Rewrite per R3's list in simple technical English, keeping every fact the current README gives that is still
  true (read it first), with absolute GitHub URLs for repository files, installs from PyPI (`uv tool install
  cronos-extract`, `pipx install cronos-extract`, `pip install cronos-extract`). Run the self-check and checklist.
  Commit `Rewrite the README for 1.0`.

---

### Task 6: `CHANGELOG.md` and records (R3, R6)

**Files:** `CHANGELOG.md` (new), `docs/superpowers/specs/2026-09-15-modernisation-roadmap-design.md`,
`docs/superpowers/plans/2026-09-15-pr2-bug-fixes.md` (a dated note), `CLAUDE.md`.

- [ ] `CHANGELOG.md`: a `## 1.0.0` section (the release workflow extracts it by this heading) per R3, in simple
  technical English, self-checked.
- [ ] R6's record changes: decision 9 and the Phase 5 text corrected; the pr2 plan's line noted; the roadmap status line
  (3e merged as PR #16; Phase 5 on branch `phase5-release`, pull request pending); `CLAUDE.md` gains the release
  command and names `docs/api.md` and `CHANGELOG.md`.
- [ ] `uv run ruff format --check`; commit `Add the changelog and record Phase 5`.

The controller appends the Outcome; the release steps (R5) follow the pull request, with Ben.
