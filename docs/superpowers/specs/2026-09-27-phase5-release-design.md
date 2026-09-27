# Phase 5 design: the 1.0 release

**Date:** 2026-09-27
**Status:** design approved by Ben (2026-09-27), section by section; to be reviewed by Fable against the code, whose
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
  the four names; ty stays clean.
- `bank.diagnostic_counts[kind]` keeps reading 0 for a kind that never occurred; `docs/api.md` says so.

Tests: both valid `FileInfo` shapes and both invalid ones; every `FileInfo` the API and `survey` build passes;
`typing.get_args(cronos_extract.Generation)` if public, else through `FileInfo`'s annotation.

### R2. KOD decoding in C, not per byte

`KODcoding.decode(o, data)` and `KODcoding.encode(o, data)` stop looping over bytes in Python. They use translation
tables precomputed per position shift (for decode, table `k` maps `c` to `(KOD[c] - k) % 256`) applied with
`bytes.translate`, so the work is done in C; the arrangement that is fastest for real record sizes (about 100 bytes to
12 KB) is chosen by measurement. `try_decode` (used by crack) keeps its behaviour. No new dependency.

Tests: `decode` and `encode` equal the per-byte formula on random data for many shifts (including 0 and 255) and
lengths (0, 1, 255, 256, 257, 4096); the whole suite and the golden files unchanged. The plan's Outcome records the
time to read a built database of 100,000 records before and after; the target is at least five times faster.

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
  the licence. Every command example in it still works (the plan names how this is checked).
- `CHANGELOG.md` has a 1.0.0 entry: what cronos-extract 1.0 is compared with cronodump, and each breaking change
  (`crodump` and `croconvert` removed; the HTML export removed; the one `cronos-extract` command; the Python API).

### R4. The release mechanics

- `pyproject.toml`: version `1.0.0`; classifier `Development Status :: 5 - Production/Stable`; URLs gain
  `Documentation` (`docs/api.md`) and `Changelog`.
- `.github/workflows/ci.yml` runs on pushes to `main` in place of `master`.
- `.github/workflows/release.yml` (new): on a pushed tag `v*`, build with `uv build`, fail unless the tag without its
  `v` equals the version in `pyproject.toml`, run the tests, publish to PyPI with trusted publishing (OIDC, no token)
  in the `pypi` environment, and create a GitHub Release whose notes are that version's `CHANGELOG.md` entry. Action
  versions are looked up when written and pinned as `ci.yml` pins them; permissions are the least each job needs.
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

Decision 9's "the repository stays private until then" is corrected: the repository was already public. The roadmap
marks Phase 5 done after the release, with the release's tag and PyPI version; `CLAUDE.md` gains the release command
(`git tag v1.x.y && git push origin v1.x.y`) and names `docs/api.md` and `CHANGELOG.md`.

### R7. Refinements from Fable's review of this spec

(To be filled after the review.)

## Delivery

One branch, `phase5-release` (which already holds the Phase 3f spike's record), one pull request:

1. R1: the API items.
2. R2: fast KOD decoding, with its measurement.
3. R3: `docs/api.md`, then the README, then `CHANGELOG.md`.
4. R4: version, CI trigger, release workflow.
5. R6: records.

Then R5's steps with Ben, in order.
