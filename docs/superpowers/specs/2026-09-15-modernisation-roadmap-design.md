# cronos-extract modernisation roadmap and 1.0 design

**Date:** 2026-09-15
**Status:** approved by Ben (2026-09-15)
**Covers:** the road from today's code (master `a10d51a`, after PR 2, PR 3 and PR 4) to a 1.0 release on PyPI, and the detailed design of Phase 0. Later phases get their own specs.

## Goal

cronos-extract reads CronosPro databases for two audiences that count equally: investigators and journalists who run the command line on databases they have been given, and developers whose pipelines import cronos-extract as a library. 1.0 makes both stable: one `cronos-extract` command, and a documented Python API that the command line is a thin layer over.

## Decisions

Every decision below was made with Ben on 2026-09-15.

1. **Audience:** command line and library API both matter; the CLI is a thin layer over the API, and both are stable at 1.0.
2. **Approach:** design and publish the API first, then restructure the internals behind it (the "API first" approach). Not a rewrite: the existing readers carry years of worked-out edge cases and the fixes from PR 2 and PR 3.
3. **CLI shape:** one `cronos-extract` command with subcommands. `crodump` and `croconvert` are removed outright, with no aliases: their names clash with the `cronodump` package.
4. **API shape:** a façade. `cronos_extract.open(...)` returns a `Bank`; today's `Datafile`, `Database` and `Datamodel` become internal, with one reader per format version behind the façade.
5. **Problem reporting:** structured `Diagnostic` objects collected on the bank, with an optional callback. The library never prints. Fatal problems raise named exceptions.
6. **Field values:** three views per field — `value` (typed), `text` (display string) and `raw` (bytes). Numeric fields stay `str` in 1.0 until real databases show how CronosPro formats numbers.
7. **Format support in 1.0:** tables with ids above 255 and CRC checking of compressed chunks. CronosPro v7 (`01.19`) comes after 1.0 (decision 13). Link fields (7, 8, 9, 17), dictionary fields (3), external files (29) and multi-valued fields come after 1.0.
8. **Exports in 1.0:** CSV, PostgreSQL and JSON Lines. The HTML export and its template are removed.
9. **Release:** nothing is published to PyPI before 1.0. 1.0 does not read v7 (decision 13). **Corrected 2026-09-27:** this decision also said that the repository stays private until 1.0, but the repository was already public, and it stays public.
10. **Specs and plans** are committed to the repository.
11. **v7 test files (decided 2026-09-16):** the Phase 0 survey of Ben's databases found no v7 — only `01.02` and `01.03` (v3) and `01.11` (v4). v7 samples will come from a file found online or one made with the CronosPro 7 trial software. No v7 file had been found by 2026-09-25, so v7 moved after 1.0 (decision 13).
12. **`compact=False` stays the default (decided 2026-09-17):** `cronos_extract.open()` keeps `compact=False`, even
    though it reads the whole CroBank `.tad` index into memory, 4.1 GB for one real database. `--compact` and
    `compact=True` are the documented way to read a very large database. See the Phase 2 design, decision D13.
13. **v7 after 1.0 (decided 2026-09-25):** the v7 reader (Phase 4) becomes a goal for after 1.0, because no real v7
    file has been found to design and test it against. The phases before 1.0 are 3 and 5, in that order.
14. **Phase 3 in four parts (decided 2026-09-25):** 3a the Datafile core (one record-decoding path, a `.tad`
    layout per version, CRC checking, a decompression limit), 3b definitions and diagnostics, 3c bank reading (the
    single-pass walk, KOD selection, file-reference context) and 3d research into v4 on real databases. Each has its
    own spec, plan and pull request; 3a is designed in `2026-09-25-phase3a-datafile-core-design.md`. **Phase 3e
    added (decided 2026-09-26):** research into the locked v4 CroStru files (the `.dat` header's 256 bytes, known
    plaintext from CroStru's known structure), the unexplained v4 `.tad` flags `04`, `08`, `0c` and `07`, and the
    third `.tad` field's timestamps, with `2026-09-26-phase3d-v4-fixes-design.md`'s Evidence as its brief. **Phase 3f
    added (decided 2026-09-27):** Phase 3e found that a v4 `.dat` header checks a KOD exactly and that CroStru record
    1 holds known plaintext (`2026-09-27-phase3e-v4-header-kod-design.md`'s Evidence), but left recovering the KOD of
    the locked v4 databases to a phase of its own: 3f, a known-plaintext KOD solver, before 1.0, with 3e's Evidence as
    its brief. **Phase 3f moved after 1.0 (decided 2026-09-27):** a research spike found that known plaintext recovers
    most of a KOD where the Files table definition matches (188 correct entries from a parse of CroStru record 1; 153
    correct and 9 wrong from crib-dragging with key names from another database), but that the five locked databases'
    CroStru records hold no copy of that definition at any offset or shift, so a solver would start from the header's
    8 entries alone. It waits for a plaintext template from the same program generation (a small v4 database made with
    CronosPro whose KOD is known).

## Roadmap

Each phase is a separate spec, plan and pull request, in this order. Phase 4 (v7) comes after 1.0 (decision 13).

**Status (2026-09-27):** Phase 0 is complete — `cronos-extract survey` merged as PR #6 — and the survey of Ben's databases found no v7 (decision 11). Phase 1 is complete: it is designed in `2026-09-16-phase1-public-api-design.md`, which refines the API contract below, and was merged as PR #9. Phase 2 is designed in `2026-09-17-phase2-command-line-design.md` and was merged as PR #11. Phase 3a is designed in `2026-09-25-phase3a-datafile-core-design.md` and was merged as PR #12. Phase 3b is designed in `2026-09-26-phase3b-definitions-diagnostics-design.md` and was merged as PR #13. Phase 3c is designed in `2026-09-26-phase3c-bank-reading-design.md` and was merged as PR #14. Phase 3d is designed in `2026-09-26-phase3d-v4-fixes-design.md` and was merged as PR #15. Phase 3e is designed in `2026-09-27-phase3e-v4-header-kod-design.md` and was merged as PR #16. Phase 3f's research spike moved the known-plaintext KOD solver after 1.0 (decision 14). Phase 5, the 1.0 release, is designed in `2026-09-27-phase5-release-design.md`, was merged as PR #17 and released on 2026-09-27: tag `v1.0.0` (the 2021 cronodump tag renamed `cronodump-v1.0.0`), `cronos-extract 1.0.0` on PyPI through trusted publishing, and a GitHub Release. The fork is detached from alephdata's network and the duplicate CodeQL default setup is off. Ben posts the courtesy issue on alephdata/cronodump.

### Phase 0 — version survey

A `cronos-extract survey` command that reports the CronosPro version of every database under a directory, reading only file headers. Ben runs it on his own databases; the result tells us whether v7 support can be confirmed against real files. Designed in full below.

### Phase 1 — public API over today's internals

`cronos_extract.open()` and the `Bank`, `Table`, `Record`, `Field`, `FileReference`, `EmbeddedFile`, `Kod`, `Diagnostic` and exception types, implemented over the existing `Database`, `Datafile` and `Datamodel` classes, which become internal. Tests are written against the public API using databases from `tests/cronos_builder.py`.

### Phase 2 — new command line on the API

The `cronos-extract` subcommands (`survey`, `export`, `inspect`, `crack`), global KOD options, exit statuses and `--strict`. Removes the `crodump` and `croconvert` commands, the HTML export and `dumpdbfields`. Golden output tests move to the new commands; the README is rewritten.

### Phase 3 — restructure behind the façade

Type annotations throughout; one record-decoding path in place of the copies in `Datafile.readrec` and `Datafile.dump`; a reader interface per format version; one CP-1251 decoding policy; one KOD-selection function; diagnostics in place of `print`. Fixes: tables with ids above 255, CRC checking, a diagnostic when a supplied KOD is not used, warnings printed once per problem instead of once per table pass, and the Files table header. The Phase 1 and Phase 2 tests guard every step. Delivered as 3a–3e (decision 14): 3e researched what 3d could not settle, and checks a KOD against a v4 file's header. Phase 3f, a known-plaintext KOD solver for the v4 databases whose own-KOD CroStru is locked, with `2026-09-27-phase3e-v4-header-kod-design.md`'s Evidence as its brief, moved after 1.0 (decision 14).

### Phase 4 — v7 reader (after 1.0)

A goal for after 1.0 (decision 13). A `01.19` reader behind the façade, from the research in alephdata/cronodump#24 (record envelope, plaintext CroBank, per-bank KOD, known-plaintext recovery) and a real v7 file (decision 11), with v7 support in `tests/cronos_builder.py` for crafted databases.

### Phase 5 — 1.0 release

**(done, 2026-09-27)** Version 1.0, API documentation, PyPI publishing, detaching the fork from alephdata's network, and removing the duplicate CodeQL "Code Quality" analysis. (Corrected 2026-09-27: this text also named making the repository public, but the repository was already public.) Ben posts the courtesy issue on alephdata/cronodump afterwards.

### After 1.0

KOD recovery that chooses the best whole permutation (an assignment problem, e.g. the Hungarian algorithm) instead of deciding each entry independently; link, dictionary, external-file and multi-valued fields; numeric value types; `inspect destruct` error handling; interactive crack exit statuses; the v7 reader of Phase 4; CroSys record type 3, given a real CroSys file; the known-plaintext KOD solver for the locked v4 databases (Phase 3f), given a plaintext template from the same program generation.

### Open items carried forward

Found during Phase 0 and its reviews and not fixed there, each with the phase that owns it. The older backlog in Appendix A of `docs/superpowers/plans/2026-09-15-pr2-bug-fixes.md` is still the input for Phases 2 to 5.

- **Phase 1 (done):** `survey.survey_roots` streams its results (Phase 1 plan, Task 6).
- **Phase 2 (done, D14):** `cli.main` now dispatches `survey`, `export`, `inspect` and `crack` through the `run_*(args, parser) -> int` signature; `dumpdbfields.py` is deleted.
- **Phase 3 (done, Phase 3a):** `Datafile.isv3`, `isv4`, `isv7` and `isencrypted` are removed; `Datafile` reads version lists from `_format/header.py` directly. (The survey's stat-then-open window is closed: every Cro file is opened by `_format/files.open_regular_file`, which checks `fstat` on the open descriptor.)
- **Phase 3 (closed without code, Phase 3b, B6):** decision 7's "tables with ids above 255" stays unfixed: no real
  table has one, and CroBank records hold the table id in one byte, so there is no known layout to read; the API's
  `unsupported_table` diagnostic already covers it. The Files table header was a `croconvert` CSV defect and went
  with `croconvert` in Phase 2.
- **Phase 3, from Phase 1:**
  - **(done, Phase 3a)** `Datafile.decompress` does not limit the decompressed size, so a crafted record can exhaust memory; do it with CRC checking. `_format/record.py`'s `decompress` now checks each chunk's CRC-32 and refuses past `MAX_DECOMPRESSED_BYTES` (256 MiB).
  - **(done, Phase 3d)** v4 deleted records: no real `01.11` `.tad` entry uses the `0xFFFFFFFF` length `readrec`
    treats as deleted, but every one with a nonzero header deleted count carries flag `02`, which
    `docs/cronos-research.md` calls deleted. `_format/tad.py`'s v4 layout now marks an entry deleted when its flag
    byte has bit `0x02` set and bit `0x01` clear (the header counts flags `02` and `06`, not `07`), so it is no
    longer read as live; flags `04`, `08`, `0c` and `07`, and the third field's
    2023–2024 Unix timestamps seen in one real database, are unexplained and become Phase 3e's research. One real
    database is a mixed-generation database (v3 CroStru, v4 own-KOD KOD-encoded CroBank and CroIndex) with
    22,870,296 genuine live records: read with the wrong, default KOD before 3d its export was garbage; `open()`
    now refuses it with `WrongKod` (Phase 3e) unless its own KOD is given, and `crack_kod(path, "dbcrack")` recovers
    that KOD in 2 s. Its slowness is the record count and per-byte KOD decoding (about 120 µs a record), not flag-`02`
    entries read as live.
  - **(done, Phase 3e)** the v4 `.dat` header's KOD check and the v4 `.tad` flags: the header block after the 19-byte
    header starts with 8 zero bytes KOD-encoded with the database's own KOD, so `koddecoder.kod_fits_header` checks a
    KOD exactly. `select_kod` reports a KOD a KOD-encoded v4 file's header rejects, the default included, `open()`
    refuses one for CroStru or CroBank with `WrongKod` (in place of 3d's `OwnKodRequired`), and `crack_kod` does not
    return one for the file it read. A v4 entry is inline when flag bit `0x04` is set, so flag-`08` records are read
    as the extended records they are; bit `0x08` looks like "the third field is a time", and bit `0x01` and flag `03`
    stay unexplained. `docs/cronos-research.md` records the evidence and its limits, and `tests/test_realdata.py`
    asserts it.
  - **(researched, Phases 3e and 3f; after 1.0)** KOD recovery fails on the real v4 databases whose CroBank and
    CroIndex headers are not KOD-encoded (both crack methods return `None`): their CroStru is encoded with their own
    KOD and holds too few records for strucrack (3d). Phase 3e found that its header gives away 8 KOD entries and that
    known plaintext in its record 1 (`Base000`) recovered 78 correct entries of 256 in one database; Phase 3f's spike
    found no such plaintext in the five locked databases, so the solver waits until after 1.0 (decision 14). `tests/test_realdata.py` marks this as a strict xfail.
  - **(done, Phase 5 R2)** Decoding KOD faster: `koddecoder.KODcoding.decode` decoded one byte at a time in Python,
    about 120 µs a record, so about 45 minutes for the 22.87 million records of the slowest real database. It now
    translates through the KOD and subtracts the position ramp in byte lanes (strided slices from 16 KiB), about 13x
    faster at 1 KiB; a built database of 100,000 KOD-encoded records of about 1 KiB reads 1.85x faster.
  - **(done, Phase 3c)** KOD selection: `koddecoder.select_kod` chooses and reports the KOD for every reader, so an
    own-KOD file read with `Kod.default()` and a KOD-encoded file read with `kod=None` are now each reported as
    `mismatched_kod`.
  - **(done, Phase 3b)** `Database.enumerate_tables`, `enumerate_records`, `enumerate_files`, `incomplete_records`,
    `files_tableid`, `get_record`, `readbankrec` and `readbankrec_or_raise` are removed. `tests/golden/api/*.jsonl`
    and `local/realdata-fingerprints.json` replaced `enumerate_records` as the API's output oracle first; the tests
    that used the removed methods moved to the public API.
  - **(done, Phase 3a)** v3 `.tad` lengths are masked with `0x0FFFFFFF` while the flags are read as `ln >> 24`, so bits 24–27 count as both flag and length; `docs/cronos-research.md` says only the top bit is a flag. `_format/tad.py`'s v3 layout now reads the inline flag from bit 31 only and keeps bits 0-30 as the length; no real database sets bits 24-30 (`docs/cronos-research.md`'s evidence over 70 files).
  - **(done, Phase 3a)** Add a committed, seeded random-damage test of the reading path, and the builder gaps the Phase 1 reviews noted (32-bit v3 flag placement, `01.02`/`01.03` written KOD-encoded). `tests/test_damage.py` flips, truncates and overwrites random bytes of built `.dat`/`.tad` files, inline and extended, unencoded and KOD-encoded (default and own tables); `tests/cronos_builder.py` gained the `extended=` and `encoded=` options it needed.
- **Phase 2, from Phase 1 (done, D5/D8/D10/D12):** diagnostic and exception text is now escaped before printing
  (`_cli/report.py`'s `EscapingStream`, D10). A date or time field holding only NUL bytes keeps `""` plus
  `invalid_value` (D5; unchanged, since a realdata count found no such field in any of the 30 listed databases).
  `crack strucrack` now reads through `readable_records` rather than `enumrecords`, so it no longer stops on a
  record `--noninteractive` skips (D12). `export --csv` writes each referenced file while the records are read,
  instead of holding them in memory until the end (D8).
- **Phase 3, from Phase 2:**
  - **(done, Phase 3c)** `Table.records()` no longer reads all of CroBank on every call; `Bank` indexes CroBank once,
    as it is read, so a table read after another reads only its own records. The slowest real database was not
    slow for this reason: it has one data table with 22.87 million genuine live records, and KOD-decoding them
    still takes about 45 minutes (see the v4 item).
  - **(done, Phase 3c)** an `unresolved_file_reference` diagnostic now names the table, record and field of the
    reference itself, alongside the target record and the reason.
  - **(done, Phase 3b)** the `inspect` subcommands now pass a `_cli/report.py` `Report` to the readers they
    construct, so a reader problem is one escaped `warning: kind: location: message` line, in the same format
    `export` uses.
  - `report.py` counts `replaced_nul` itself, because writing a NUL to a PostgreSQL `TEXT` column is a problem of
    the SQL writer, not of reading; if Phase 3 gives the API a diagnostic kind for output problems, this moves
    there.
- **Phase 3b, from Phase 3a (done):** a CroStru checksum mismatch (the database definition or a table definition) is
  now reported as its own kind, `checksum_mismatch`, instead of `unexpected_structure` through the `warn` hook.
- **Before 1.0, from Phase 1 (settled, Phase 5 R1):** `FileInfo` does not enforce that either `problem` or the header fields are set; `Generation` is a PEP 695 alias, so `typing.get_args(Generation)` is empty; `bank.diagnostic_counts[kind]` reads 0 for a kind that never occurred (documented). Phase 5 R1 settled all three: `FileInfo.__post_init__` enforces the invariant, `Generation` is a public `Literal` alias, and `docs/api.md` documents the zero count.
- **Cosmetic, no phase:** an unreadable directory reachable from two overlapping roots is warned about twice. A directory named `Cro*.dat` that itself holds databases is reported as a problem under its parent and as its own database, so `--counts` also scores it as one unreadable file. `--jsonl` writes undecodable path bytes as `\udcXX` escapes, which strict JSON parsers may reject. The README's sentence about unreadable directories sits in the `--list` paragraph, though the warning applies to any root.
- **Decided, not open:** `survey_file` follows symlinks (`stat`, not `lstat`) on purpose, and each plan keeps its pre-implementation wording as the record of what was planned.

## Public API contract (Phases 1 and 2 build to this)

As refined by the Phase 1 design (`2026-09-16-phase1-public-api-design.md`, decisions P1–P11), which gives the full detail.

```python
import cronos_extract

with cronos_extract.open(path, kod=..., compact=False, on_diagnostic=None) as bank:
    for table in bank.tables:
        for record in table.records():
            record["Entry #4"].value
```

- **`open(path, *, kod=Kod.default(), compact=False, on_diagnostic=None) -> Bank`** — `kod=None` reads without KOD decoding. `Bank` is a context manager that closes its files.
- **`Kod`** — `Kod.default()`, `Kod.from_hex(str)`, `Kod.from_table(Sequence[int])`. A valid table is a permutation of 0–255.
- **`crack_kod(path, method="strucrack" | "dbcrack") -> Kod | None`** — returns `None` when it cannot recover a permutation.
- **`Bank`** — `tables: Sequence[Table]` (the Files table excluded), `read_file(FileReference) -> EmbeddedFile | None`, `files() -> Iterator[EmbeddedFile]`, `info: Sequence[FileInfo]` (per-file versions and flags, as the survey reports them), `diagnostics: Sequence[Diagnostic]` (the first 1,000), `diagnostic_counts: Mapping[DiagnosticKind, int]`, `close()`.
- **`Table`** — `id: int`, `name: str`, `abbreviation: str`, `fields: Sequence[FieldDefinition]`, `records() -> Iterator[Record]` (lazy).
- **`Record`** — `number: int`, `fields: Sequence[Field]`, `__getitem__(name)`, `diagnostics`.
- **`Field`** — `definition`, `value`, `text: str`, `raw: bytes`. `value` is `str`, `datetime.date`, `datetime.time`, `FileReference` or `None`; a value that does not parse as its type falls back to the text and records a diagnostic.
- **`FileReference`** — `name`, `extension`, `record`. **`EmbeddedFile`** — `record: int`, `data: bytes`, `name: str | None` (`None` from `files()`, where the Files table stores no name).
- **`Diagnostic`** — frozen: `kind` (`DiagnosticKind`: `corrupt_record`, `checksum_mismatch`, `undecodable_field`, `invalid_value`, `undecodable_table`, `unsupported_table`, `unexpected_structure`, `unresolved_file_reference`, `unreadable_file`, `unused_kod`), `message`, `file`, `table`, `record`, `field`.
- **Exceptions** — `CronosError` base; `NotACronosFile`, `UnsupportedVersion`, `DatabaseDefinitionError`. Anything survivable (one record, field or file reference) is a diagnostic, not an exception.

**Documented promises:** iteration is lazy, and `bank.diagnostics` grows while reading, up to its first 1,000 entries; a `Bank` is not thread-safe; the set of `Field.value` types may grow in later versions.

## Command line

As refined by the Phase 2 design (`2026-09-17-phase2-command-line-design.md`), whose decision D1 moves the KOD
options onto the subcommands that read with one.

```
cronos-extract <subcommand>
```

- `survey [--list FILE] [--counts|--jsonl] [DIR...]`
- `export --csv|--postgres|--jsonl [-o PATH] [--delimiter ,] [--no-files] [--strict] KODOPTS DB`
- `inspect strudump|recdump|crodump|destruct|kodump [options] KODOPTS DB`
- `crack strucrack|dbcrack [--noninteractive] [--silent] [--sys] [--fix F] [--text T] [--width N] [--color] DB`

where `KODOPTS` is `[--kod HEX | --nokod | --crack strucrack|dbcrack] [--compact]`, and `inspect destruct` and
`inspect kodump`, which read stdin or one file, take only `--kod` and `--nokod`.

Data goes to stdout, diagnostics to stderr followed by a summary count. Exit statuses: 0 on success (skipped records included), 1 when the database cannot be read at all (one message, no traceback), 2 for a usage error. `--strict` turns any diagnostic into exit status 1.

## Phase 0 design: `cronos-extract survey`

### What it reads

A `.dat` file starts with a 19-byte header, `struct.unpack("<8sH5sHH", ...)`: magic `CroFile\0`, an unknown uint16, a 5-byte version, uint16 encoding flags (bit 0 KOD-encoded, bit 1 compressed) and a uint16 block size. Versions `01.02`–`01.05` are v3, `01.11`/`01.13`/`01.14` are v4, `01.19` is v7; `01.03`, `01.05` and `01.11` use 64-bit offsets; `01.04`, `01.05` and v4 are encrypted with the database's own KOD table. The survey reads those 19 bytes and nothing else: no `.tad` file, no record, no file content.

### Behaviour

- `cronos-extract survey [--list FILE] [--counts | --jsonl] [DIR...]` walks each directory recursively without following symlinks, and treats every directory containing `Cro*.dat` files as one database. File names are matched case-insensitively.
- **`--list FILE`:** survey the directories named in a text file, one per line, as one group, alone or alongside directories given as arguments. Blank lines and lines starting with `#` are ignored, and a relative path is taken from the current directory. A database found under more than one root is reported once, so `--counts` totals count it once.
- **Default output:** a block per database — its path, then one line per file with the name (`Stru`, `Bank`, `Index`, `Sys` or another), version, generation (`v3`, `v4`, `v7`, or `unknown`), 32- or 64-bit, and whether it is KOD-encoded, compressed and encrypted with its own KOD.
- **`--counts`:** totals per version and generation only, with no paths, for sensitive directory names.
- **`--jsonl`:** one JSON object per database, for scripts and agents.
- **Problems** (a file shorter than 19 bytes, an unknown magic, an unreadable file, an unknown version) are reported as a problem line for that file, and the walk continues. No tracebacks. Exit status 0 when the walk completes, 2 for a missing directory or a usage error.
- **A list entry that is not a directory** is a warning on stderr and the run continues with exit status 0: the file is data, and a database may have moved since it was written. A directory given as an argument, a `--list` file that cannot be read, and giving neither a directory nor a list are usage errors with exit status 2.

### Files

- `src/cronos_extract/cli.py` — the `cronos-extract` entry point: an argparse parser dispatching all four subcommands, `survey`, `export`, `inspect` and `crack`.
- `src/cronos_extract/survey.py` — finding databases, reading a `--list` file, surveying several roots as one group without reporting a database twice, and the three output formats.
- `src/cronos_extract/_format/header.py` — a frozen, annotated `DatHeader` and `read_dat_header(file) -> DatHeader`, raising `ValueError` for a short file or an unknown magic. `Datafile.readdathdr` is changed to use it, so the header is parsed in one place. This creates the internal `_format` package that Phase 3 fills.
- `pyproject.toml` — adds the console script `cronos-extract = "cronos_extract.cli:main"`. The `crodump` and `croconvert` scripts are gone.
- New modules are fully annotated and ty-clean.

### Tests

Real files only, no mocks: v3 databases from `tests/cronos_builder.py`; v4 and v7 headers written as raw bytes; a nested tree and mixed-case names; problem files (short, bad magic, unknown version); `--counts` output containing no paths; the `--jsonl` structure; and `Datafile` still reading `test_data` unchanged, so the existing golden files do not move.

### Exit criterion

Ben runs the survey on his own databases and reports which versions appear. That decides whether Phase 4 can confirm v7 against real files or must label it experimental.

**Result (2026-09-16):** no v7 among Ben's databases. The survey counted 62 `01.02` files, 8 `01.03` files and 20 `01.11` files; see decision 11.
