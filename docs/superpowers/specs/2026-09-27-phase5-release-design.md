# Phase 5 design: the 1.0 release

**Date:** 2026-09-27
**Status:** design approved by Ben (2026-09-27), section by section; reviewed by Fable against the code, whose
findings R7 records
**Builds on:** `2026-09-15-modernisation-roadmap-design.md` (Phase 5; decisions 9 and 14; "Before 1.0" items) and
`2026-09-16-phase1-public-api-design.md` (the API contract)

## Goal and scope

cronos-extract 1.0 is on PyPI, installable with `pip install cronos-extract` or `uv tool install cronos-extract`, with
an API reference, a README and a changelog written in simple technical English; the API quirks that 1.0 would freeze
are settled; KOD decoding is fast enough for a database of millions of records; and every later release is one tag.

**Not in 1.0 (Ben, 2026-09-27):** the known-plaintext KOD solver (after 1.0, decision 14), v7 (decision 13), and the
rest of "After 1.0".

## Evidence (2026-09-27)

- `pyproject.toml` says version `0.1.0.dev0`; the name `cronos-extract` is free on PyPI (its JSON API answers 404).
- The repository is public and is still a GitHub fork. It holds upstream cronodump's tag `v1.0.0` (itsme, 2021).
- `.github/workflows/ci.yml` runs on `pull_request` and on pushes to `master`; the default branch has been `main`
  since PR #11, so a push or merge to `main` runs no CI.
- `koddecoder.KODcoding.decode` decodes one byte at a time in Python: about 120 µs for a record, about 45 minutes for
  the 22.87 million records of the largest real database that opens with its KOD.
- The roadmap's "Before 1.0" items: `FileInfo` does not enforce its invariant; `Generation` is a PEP 695 alias, so
  `typing.get_args(Generation)` is empty; `bank.diagnostic_counts[kind]` reads 0 for a kind that never occurred.

## Decisions

Each decision below was made with Ben on 2026-09-27.

### R1. What 1.0 freezes

- `FileInfo.__post_init__` raises `ValueError` unless either `problem` is set and `version`, `generation`,
  `use64bit`, `kod_encoded`, `compressed` and `own_kod` are all None, or `problem` is None and all of them are set.
- `Generation` becomes `Generation = Literal["v3", "v4", "v7", "unknown"]` (a plain alias), so `typing.get_args` lists
  the four names; ty stays clean. It becomes public: `FileInfo.generation` exposes it, so `cronos_extract` re-exports it
  and lists it in `__all__`.
- `bank.diagnostic_counts[kind]` keeps reading 0 for a kind that never occurred; `docs/api.md` says so.

Tests: both valid `FileInfo` shapes and both invalid ones; every `FileInfo` the API and `survey` build passes,
including a file of an unknown or v7 version, whose `generation` is the value `"unknown"` or `"v7"` with `problem`
None; `typing.get_args(cronos_extract.Generation)` lists the four names. `diagnostic_counts` needs no change
(`_api/diagnostics.py` already exposes a read-only view of a `Counter`).

### R2. KOD decoding in C, not per byte

`KODcoding.decode(o, data)` and `KODcoding.encode(o, data)` stop looping over bytes in Python; `bytes` in and out, as
every caller expects. Because the shift `(i + o) % 256` changes at every position, one `bytes.translate` cannot do it.
The candidates are measured against the per-byte formula and the fastest for each record length is used: 256 tables
applied to the strided slices `data[j::256]` and interleaved again (15x at 12 KB, slower at 100 bytes in Fable's
measurement), and one `translate` through the KOD followed by subtracting the position ramp on `int.from_bytes` values
in even and odd byte lanes (7 µs against 9 µs at 100 bytes, 8x at 1 KB, 19x at 12 KB). Encode uses the inverse
(`inv[(c + k) % 256]`). `try_decode` (used only by crack) keeps its behaviour. No new dependency: a C extension or
`numpy` would be faster at 100 bytes, but is not worth a dependency.

Tests: `decode` and `encode` equal the per-byte formula on random data for many shifts (including 0 and 255) and
lengths (0, 1, 7, 8, 9, 255, 256, 257, 4096, 12288); the whole suite and the golden files unchanged. The plan's
Outcome records the time to read a built database of 100,000 KOD-encoded records of about 1 KB, the size behind the
real database's 120 µs a record, before and after, and the time per record at 100 bytes, 1 KB and 12 KB.

### R3. The documentation, in simple technical English

`docs/api.md` (new), the README (rewritten) and `CHANGELOG.md` (new) are written to the rules of the `simple-english`
skill (`/home/ben/.claude/skills/simple-english/SKILL.md`, pragmatic mode): procedural text in the imperative, at most
20 words a sentence, conditions before commands; descriptive text at most 25 words a sentence, one new fact a
sentence, at most six sentences a paragraph; no "should", "may", "might", "could", "would" or semicolons; one term
for each concept (the check family is "make sure that"); code, identifiers, commands and quoted messages untouched.
Each writer runs the skill's self-check and `references/checklist.md` before committing, and the reviewer checks the
same way.

- `docs/api.md` documents every name in `__all__`: `open()` and its parameters, `Bank`, `Table`, `Record`, `Field`,
  `FieldDefinition`, `FileReference`, `EmbeddedFile`, `Kod`, `crack_kod`, `FileInfo`, `Generation`, `Diagnostic`, each
  `DiagnosticKind` with what it means and when it occurs, each exception and when it is raised, and the documented
  promises (laziness, diagnostics kept and counted, thread safety, the value types, `compact`, the index's memory).
  A test fails when a name in `__all__` or a `DiagnosticKind` member does not appear in it.
- The README is rewritten: what cronos-extract is and its origin (cronodump, OCCRP, the authors), installing from
  PyPI, the commands with examples, recovering a KOD, the library (short, linking to `docs/api.md`), development, and
  the licence. Every command example in it still works: a test runs each one from a checkout, against `test_data`,
  skipping the install lines. Links to repository files (`LICENSE`, `docs/api.md`, `CHANGELOG.md`,
  `docs/cronos-research.md`) are absolute `https://github.com/hammersleyfutures/cronos-extract/blob/main/...` URLs,
  because PyPI renders the README and relative links are dead there.
- `CHANGELOG.md` has a 1.0.0 entry: what cronos-extract 1.0 is compared with cronodump, and each breaking change
  (`crodump` and `croconvert` removed; the HTML export removed; the one `cronos-extract` command; the Python API).

### R4. The release mechanics

- `pyproject.toml`: version `1.0.0`; classifier `Development Status :: 5 - Production/Stable`; URLs gain
  `Documentation` (`docs/api.md`) and `Changelog`.
- `.github/workflows/ci.yml` and `.github/workflows/codeql.yml` run on pushes to `main` in place of `master`.
- `cronos-extract --version` prints `cronos-extract <version>` from `importlib.metadata.version("cronos-extract")` and
  exits 0, with a test.
- `.github/workflows/release.yml` (new), on a pushed tag `v*`: top-level `permissions: contents: read`. A build job
  sets up uv with `astral-sh/setup-uv`, fails unless `uv version --short` equals `${GITHUB_REF_NAME#v}` (before
  building), runs `uv sync --locked` and the tests from the checkout (the sdist holds no tests), builds with
  `uv build`, and uploads `dist/` as an artifact. A publish job in `environment: pypi` with only `id-token: write`
  downloads it and runs `uv publish --trusted-publishing always`. A release job with `contents: write` creates the
  GitHub Release for the tag with that version's `CHANGELOG.md` entry as notes and the built files attached. Action
  versions are looked up when written and pinned as `ci.yml` pins them.
- The README's install instructions name PyPI.

### R5. Ben's one-off steps, and release day

The plan lists these and waits for each; none is done for Ben.

1. Register the pending trusted publisher on PyPI: project `cronos-extract`, owner `hammersleyfutures`, repository
   `cronos-extract`, workflow `release.yml`, environment `pypi`.
2. Create the `pypi` environment in the repository, with Ben as required reviewer.
3. Detach the fork from alephdata's network (Settings, or a GitHub Support request).
4. Turn off the duplicate CodeQL "Code Quality" default setup, keeping `codeql.yml`.
5. After the release, post the courtesy issue drafted in Appendix B of `2026-09-15-pr2-bug-fixes.md`.

Release day, each step with Ben's go-ahead at the time: re-tag the 2021 commit as `cronodump-v1.0.0` and delete
`v1.0.0` locally and on origin; once the pull request is merged, tag `v1.0.0` on `main` and push it; Ben approves the
`pypi` environment's run; then `uv tool install cronos-extract` (or `pip install` in a new venv) runs
`cronos-extract --version` or `--help` from PyPI.

### R6. Records

Decision 9's "the repository stays private until then" and the Phase 5 roadmap text "making the repository public"
are corrected, and `2026-09-15-pr2-bug-fixes.md`'s "making the repository public again" gets a dated note: the
repository was already public. The roadmap
marks Phase 5 done after the release, with the release's tag and PyPI version; `CLAUDE.md` gains the release command
(`git tag v1.x.y && git push origin v1.x.y`) and names `docs/api.md` and `CHANGELOG.md`.

### R7. Refinements from Fable's review of this spec (2026-09-27)

Fable reviewed this spec against the repository, built the package and measured KOD decoding. Each finding was
checked and adopted; the decisions above include them.

- **Translate-per-shift misses the target at small records** (slower at 100 bytes); R2 now measures named candidates
  per length and states the target on a realistic database instead of a flat 5x.
- **`--version` did not exist**; R4 adds it.
- **`codeql.yml` has the same stale `master` trigger**; R4 fixes both workflows.
- **`Generation` was not public**; R1 makes it public.
- **PyPI renders the README**, so repository links are absolute, and the command check runs from a checkout (R3).
- **The release workflow's permissions, environment, version check order and test location** are spelled out (R4);
  the sdist holds `src/`, `LICENSE`, `README.md` and `pyproject.toml` only, and the wheel holds `py.typed` and the
  licence.
- **Two more "make public" lines** are corrected (R6). Deleting the old `v1.0.0` tag is safe: nothing references it and
  it has no GitHub Release.

## Delivery

One branch, `phase5-release` (which already holds the Phase 3f spike's record), one pull request:

1. R1: the API items.
2. R2: fast KOD decoding, with its measurement.
3. R3: `docs/api.md`, then the README, then `CHANGELOG.md`.
4. R4: version, CI trigger, release workflow.
5. R6: records.

Then R5's steps with Ben, in order.
