# Phase 3e design: the v4 header's KOD check

**Date:** 2026-09-27
**Status:** design approved by Ben (2026-09-27), section by section; to be reviewed by Fable against the code, whose
findings E6 records
**Builds on:** `2026-09-26-phase3d-v4-fixes-design.md` (D1, D2), `2026-09-26-phase3c-bank-reading-design.md` (C2's
`select_kod` table) and the Phase 3e research spike of 2026-09-27 (Evidence below)

## Goal and scope

A KOD-encoded v4 file is never decoded with a KOD its own header rejects, whether the KOD was the default or given;
a default KOD the header accepts is used; a crack never returns a KOD that decodes garbage; v4 records flagged `08`
are read as the extended records they are; and the research is recorded.

**Not in 3e:** recovering the KOD of the five real v4 databases whose own-KOD CroStru is locked (a known-plaintext
solver, a phase of its own; the Evidence is its brief); the meaning of flag bit `0x01` and flag `03`.

## Evidence (the Phase 3e research spike, 2026-09-27, read-only, counts only)

- **The v4 header block is KOD-encoded with the database's own KOD.** After the 19-byte `.dat` header come 237 bytes
  that are the same in every Cro file of a v4 database. Decoded with the database's own KOD as
  `(KOD[h[19 + j]] - j) % 256`, the first 8 are zero, then 24 bytes look random, then zeros again, then long runs of a
  constant value that drifts slowly down (the inverse KOD read in order with a drifting offset). This holds in all 5
  v4 files whose own KOD is known (two databases); the default KOD gives at most 1 zero of 8 in every v4 file, including
  files whose records are not KOD-encoded. v3 headers do not follow this scheme at any shift.
- **So the header checks a KOD exactly.** A KOD is a v4 file's own exactly when those 8 bytes decode to zeros; a wrong
  KOD passes by chance about once in 256⁸. A locked database gives its first 8 KOD entries away.
- **Known plaintext recovers much of a locked KOD.** `Base000` (the Files table definition) is stored inline in CroStru
  record 1 and is 92 of 93 bytes identical in two unrelated databases. Sliding one database's `Base000` over the other's
  still-encoded record 1, with the header's 8 entries, leaves exactly one consistent offset (the true one) and 78
  correct KOD entries of 256. Record 1's keys are sorted and come from a small vocabulary (`Bank`, `BankId`,
  `BankName`, `Base000`, `Base001`, …, `NS1`, `USERINFO`, `Version`).
- **Flag bits.** All 838 flag-`08` CroBank entries of the one database that has them point at extended-record headers,
  and their third `.tad` field holds a Unix time; its few flag-`0c` entries mostly do not point at one. Flags `00` point
  at extended headers, `04` at inline data. So bit `0x04` looks like "inline" and bit `0x08` like "the third field is a
  time". That database cannot be opened yet, so this is not confirmed by reading its records.

## Decisions

Each decision below was made with Ben on 2026-09-27.

### E1. The header check

`_format/header.py`'s `read_dat_header` also reads up to 8 bytes after the 19-byte header into a new
`DatHeader.kod_check: bytes` (fewer when the file is shorter; the header's own size check is unchanged).
`koddecoder.kod_fits_header(header: DatHeader, kod: KODcoding) -> bool | None` is None for a v3 file or when fewer than
8 check bytes were read, and otherwise whether `(kod.kod[b] - j) % 256 == 0` for each `b` at position `j`. `survey`
reads `DatHeader` and does not use the new field.

### E2. KOD selection and `open()` use it for KOD-encoded v4 files

`select_kod`'s rows for a KOD-encoded v4 file become: with a KOD (default or not) that the header accepts, decode with
it and report nothing; with one it rejects, decode with it and report `mismatched_kod` with the message `the file's
header shows that the KOD given is not its KOD`; with none, 3c's row (`mismatched_kod`, read without KOD decoding).
When the check is None, 3c's rows apply. Files that are not KOD-encoded, v3 files and `01.04`/`01.05` keep 3c's table.

`open()` raises `WrongKod` (a new `CronosError`) when the KOD in use fails the header check of a KOD-encoded v4 CroStru
or CroBank: CroStru first, then CroBank, both before the database definition is decoded. So a wrong KOD, default or
given, is refused; a default KOD the header accepts is used; with `kod=None` nothing is checked and 3c's warning stays.
The message names the file and the directory, says its header shows the KOD is not the database's, and ends with a
hint naming `cronos_extract.crack_kod(path, "dbcrack")` for CroBank or `"strucrack"` for CroStru; the command line's
`error_message` replaces it with `--crack` and `cronos-extract crack`. `inspect` opens files through `Database` and
keeps the warning.

3d's `OwnKodRequired`, its hint and its header-flag rule are removed outright (it was never released): `WrongKod`
takes its place in `__all__`, in `open()`'s and the package's docstrings, and in the tests, which move to the new rule.

**Tests:** `kod_fits_header` on built v4 files (the right KOD, a wrong one, a short file, a v3 file); `select_kod`'s new
rows; `open()` refuses a wrong given KOD and a wrong default for CroStru and for CroBank, opens a v4 database encoded
with the default table with the default KOD (refused under 3d), and opens the mixed database with its own KOD; an
`export` subprocess test pins the `Error:` line. `tests/cronos_builder.py` writes v4 headers as real files have them:
8 zero bytes KOD-encoded with the file's KOD (the default table when the records are unencoded or default-encoded)
at offset 19; the rest of the block stays zero.

### E3. `crack_kod` and the crack commands check their result

`crack_kod` returns a recovered KOD only if it passes the header check of the file it cracked (CroStru for
strucrack, CroBank for dbcrack) whenever that check is not None, and None otherwise. `crack strucrack` and `crack
dbcrack` print one line on stderr when the KOD they derived fails the check (`the recovered KOD does not fit
Cro<name>.dat's header, so it is not the database's KOD`), and `--noninteractive` then exits 1.

### E4. A v4 entry is inline when bit `0x04` is set

`_format/tad.py`'s v4 `inline` is `bool(flags & 0x04)` in place of "any flag other than the deleted bit": `00`, `02`
and `08` are extended, `04`, `06`, `07` and `0c` inline. The comment states the evidence and its limits (E. Flag bits).
Tests: the layout test's inline column; a built v4 database with a flag-`08` extended record reads back whole.

### E5. Realdata and records

- `tests/test_realdata.py` gains a test: for every v4 file whose database opens, or whose KOD `crack_kod(path,
  "dbcrack")` recovers, the KOD in use passes the header check; for every KOD-encoded v4 file, the default KOD fails it
  unless the database opens with the default.
- `docs/cronos-research.md`'s v4 section records the Evidence: the header block and the check, `Base000`'s constancy and
  what alignment recovered, and the flag bits with their evidence and limits.
- The roadmap marks Phase 3e done and adds the known-plaintext solver as a phase before 1.0, with this spec's Evidence
  as its brief; `CLAUDE.md`'s KOD section describes the header check and `WrongKod`; the 3d spec's D2 gets a dated note
  that E2 replaced it.

### E6. Refinements from Fable's review of this spec

(To be filled after the review.)

## Delivery

One branch, `phase3e-v4-header-kod`, one pull request, in this order, each commit with its tests and green:

1. E1 and the builder's v4 headers.
2. E2: `select_kod`, `open()`, `WrongKod` replacing `OwnKodRequired`.
3. E3: crack.
4. E4: the inline bit.
5. E5: realdata (then a background realdata run), research notes and records.
