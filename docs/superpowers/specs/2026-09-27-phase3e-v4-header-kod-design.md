# Phase 3e design: the v4 header's KOD check

**Date:** 2026-09-27
**Status:** design approved by Ben (2026-09-27), section by section; reviewed by Fable against the code, whose
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

- **The v4 header block is KOD-encoded with the database's own KOD.** After the 19-byte `.dat` header, bytes 19 to 255
  (237 bytes) are the same in every Cro file of a v4 database. (The builder and `Datafile`'s comment use 0xE9 bytes of
  padding; the research notes say "0x101 or 0x100 minus 19"; only the first 8 matter here.) Decoded with the database's own KOD as
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

`DatHeader` gains `kod_check: bytes = b""`. `read_dat_header` is unchanged (it reads the 19-byte header, which
`survey` and `FileInfo` rely on); a new `_format/header.py` function, `read_kod_check(file: BinaryIO) -> bytes`,
reads up to 8 bytes at offset 19 (fewer when the file is shorter), and `Datafile` stores them on its header
(`dataclasses.replace`). `koddecoder.kod_fits_header(header: DatHeader, kod: KODcoding) -> bool | None` is None for any
generation other than v4 or when fewer than 8 check bytes were read, and otherwise
`kod.decode(0, header.kod_check) == bytes(8)`: the block is encoded like record 0 of the same cipher, so nothing is
reimplemented.

### E2. KOD selection and `open()` use it for KOD-encoded v4 files

`select_kod`'s rows for a KOD-encoded v4 file become: with a KOD (default or not) that the header accepts, decode with
it and report nothing; with one it rejects, decode with it and report `mismatched_kod` with the message `the file's
header shows that the KOD given is not its KOD`; with none, 3c's row (`mismatched_kod`, read without KOD decoding).
When the check is None, 3c's rows apply. Files that are not KOD-encoded, v3 files and `01.04`/`01.05` keep 3c's table.

`open()` raises `WrongKod` (a new `CronosError`) when the KOD in use fails the header check of a KOD-encoded v4 CroStru
or CroBank: CroStru first, then CroBank, both before the database definition is decoded. So a wrong KOD, default or
given, is refused; a default KOD the header accepts is used; with `kod=None` nothing is checked and 3c's warning stays.
The message names the file and the directory, says its header shows the KOD is not the database's, and ends with a
hint: one constant naming `cronos_extract.crack_kod(path, "dbcrack")` for CroBank, another naming `"strucrack"` for
CroStru; the command line's `error_message` replaces each with its own hint naming `--crack dbcrack` or `--crack
strucrack` and the matching `cronos-extract crack` command, each pinned by a subprocess test. `open()` learns the
verdict by calling `kod_fits_header(datafile.header, datafile.kod)` after each `open_datafile` (`datafile.kod` is None
with `kod=None`, so nothing is checked). The `mismatched_kod` diagnostic is reported while the file is opened, so it
still precedes `WrongKod`'s `Error:` line. `inspect` opens files through `Database` and
keeps the warning.

3d's `OwnKodRequired`, its hint and its header-flag rule are removed outright (it was never released): `WrongKod`
takes its place in `__all__`, in `open()`'s and the package's docstrings, and in the tests, which move to the new rule.

**Tests:** `kod_fits_header` on built v4 files (the right KOD, a wrong one, a short file, a v3 file); `select_kod`'s new
rows; `open()` refuses a wrong given KOD and a wrong default for CroStru and for CroBank, opens a v4 database encoded
with the default table with the default KOD (refused under 3d), and opens the mixed database with its own KOD; an
`export` subprocess test pins the `Error:` line. `tests/cronos_builder.py` writes a v4 header block whose first 8 bytes
are zeros encoded with the file's KOD (as `KODcoding.encode(0, bytes(8))`) at offset 19, the rest staying zero:
`write_raw_datafile` gains a `kod` parameter (the table to encode the check bytes with; the default table when None),
and `write_datafile` passes the KOD it encodes records with. This lands in the same commit as E1, before E2, since raw
zero padding fails the check for every KOD; a builder test asserts that bytes 19–26 of a built v4 file decode to zeros
with the file's KOD. (Real unencoded v4 files carry their database's own KOD in the header; the builder uses the
default for them, which the check never looks at.)

### E3. `crack_kod` and the crack commands check their result

`crack_kod` returns a recovered KOD only if it passes the header check of the file it read (CroStru for strucrack,
CroBank for dbcrack; each `Datafile` keeps its header) whenever that check is not None, and None otherwise. The
command-line `crack strucrack` (CroStru, or CroSys with `--sys`) and `crack dbcrack` (CroBank) print one line on stderr
when the KOD they derived fails the check of the file they read: `the recovered KOD does not fit Cro<name>.dat's
header, so it is not the database's KOD`, unless `--silent`, which prints only the KOD. `strucrack --noninteractive`
then exits 1, as for an unresolved KOD; an interactive strucrack still prints its dump and KOD and exits 0; `dbcrack`
exits 1, as it does when it recovers nothing.

### E4. A v4 entry is inline when bit `0x04` is set

`_format/tad.py`'s v4 `inline` is `bool(flags & 0x04)` in place of "any flag other than the deleted bit": every flag
with bit `0x04` clear is extended, including `01`, `03`, `05` and `09`, which have not been seen; of those seen, `00`,
`02` and `08` are extended and `04`, `06`, `07` and `0c` inline. The comment states the evidence and its limits (E. Flag bits).
Tests: the layout test's inline column; a built v4 database with a flag-`08` extended record reads back whole.

### E5. Realdata and records

- `tests/test_realdata.py` tests the Evidence itself rather than the gate E2 and E3 build on it: (a) the default KOD
  fails the header check of every v4 file, encoded or not; (b) for every v4 database whose CroBank and CroIndex give
  dbcrack's statistics a whole permutation (computed with `_api/crack.py`'s internals, before any header check), that
  permutation passes CroBank's header check; (c) every v4 `.tad` entry's flag byte is one of `00`, `02`, `04`, `06`,
  `07`, `08`, `0c`, so an unseen flag fails loudly instead of being read by a guessed rule.
- `docs/cronos-research.md`'s v4 section records the Evidence: the header block and the check, `Base000`'s constancy and
  what alignment recovered, and the flag bits with their evidence and limits.
- The roadmap marks Phase 3e done and adds the known-plaintext solver as a phase before 1.0, with this spec's Evidence
  as its brief; `CLAUDE.md`'s KOD section describes the header check and `WrongKod`; the 3d spec's D2 gets a dated note
  that E2 replaced it.

### E6. Refinements from Fable's review of this spec (2026-09-27)

Fable reviewed this spec against the code; each finding was checked and adopted, and the decisions above include them.

- **The builder's zero padding fails the check for every KOD**, so E2 alone would make every KOD-encoded v4 test
  database raise `WrongKod`; the builder writes encoded check bytes, through a `kod` parameter on `write_raw_datafile`,
  in E1's commit (E2).
- **The check reuses the cipher**: `kod.decode(0, check) == bytes(8)` (E1).
- **`read_dat_header` stays at 19 bytes**, which `survey` and `FileInfo` rely on; the check bytes are read separately
  (E1).
- **E4 flips unseen flags** `01`, `03`, `05`, `09`: the rule is stated in full, and realdata fails on an unseen flag
  (E4, E5).
- **The realdata test tested the gate**, not the Evidence; it now asserts the Evidence (E5).
- **Crack reads CroSys with `--sys`**, `dbcrack` has no `--noninteractive`, and `--silent` prints only the KOD (E3).
- **Two hints need two command-line replacements**, and the diagnostic still precedes the error (E2).
- **The header block's size** is stated as the bytes from 19 to 255 (Evidence).

## Delivery

One branch, `phase3e-v4-header-kod`, one pull request, in this order, each commit with its tests and green:

1. E1 and the builder's v4 headers.
2. E2: `select_kod`, `open()`, `WrongKod` replacing `OwnKodRequired`.
3. E3: crack.
4. E4: the inline bit.
5. E5: realdata (then a background realdata run), research notes and records.
