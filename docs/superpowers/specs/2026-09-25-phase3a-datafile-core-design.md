# Phase 3a design: the Datafile core

**Date:** 2026-09-25
**Status:** design approved by Ben (2026-09-25), section by section; this written spec awaits his review
**Builds on:** `2026-09-15-modernisation-roadmap-design.md` ("Phase 3" and "Open items carried forward"; decision 14
splits Phase 3 into 3a–3d), `2026-09-16-phase1-public-api-design.md` and `2026-09-17-phase2-command-line-design.md`

## Goal and scope

Phase 3 restructures the internal readers behind the public API. Decision 14 splits it into four sub-projects, each
with its own spec, plan and pull request: **3a** the Datafile core (bytes to records), **3b** definitions and
diagnostics, **3c** bank reading, and **3d** research into v4 on real databases. This spec is 3a.

3a gives `Datafile` one record-decoding path and a `.tad` layout per format version, checks the CRC of every
compressed chunk, bounds the memory a record can decompress to, and fully annotates the code it touches. The public
API and the command line keep their behaviour, apart from the new `checksum_mismatch` diagnostic (A3), a record over
256 MiB becoming `corrupt_record` (A4), and `inspect crodump`'s mismatch marker (A6).

**Not in 3a:** the meaning of the v4 `.tad` flags `02` and `03`, which are still read as live records (3d); the
uncrackable v4 databases (3d); diagnostics in place of `warn` and `print`, one CP-1251 policy, table ids above 255,
the Files table header and the dead `Database` methods (3b); the single-pass CroBank walk, KOD selection and file
reference context (3c).

## Evidence gathered for this design (2026-09-25, read-only, counts only)

- **CRC:** across 8 small real databases, 11,885 compressed chunks in 11,772 records all store the CRC-32 of their
  decompressed data (`zlib.crc32`); none mismatched.
- **Record sizes:** across 130,254 compressed CroBank records of the real databases under the test suite's size
  limit, the largest compressed record is 75,331 bytes, the largest decompressed one 79,968 bytes, and the highest
  ratio 1.9.
- **v3 `.tad` flags:** in 70 real v3 `.tad` files, the top byte of a live entry's length field is always `0x00`
  (1,417,422 entries) or `0x80` (10,690,012 entries); 787,562 entries are deleted (`0xFFFFFFFF`). No entry sets any of
  bits 24–30.

## Decisions

Each decision below was made with Ben on 2026-09-25.

### A1. Restructure `Datafile` in place, around two new typed modules

`Datafile` keeps its name, its callers and its methods' contracts; it is not rewritten. Two new modules hold what
it does today in two copies:

- **`_format/tad.py`** — `TadEntry(offset, length, inline, deleted, checksum)` and a `TadLayout` per generation
  that turns a raw `.tad` entry into a `TadEntry`, and knows its header size (8 bytes for v3, 16 for v4) and entry
  size (12 or 16 bytes). `_api/datafiles.py`'s `TAD_HEADER_SIZES` and `Datafile.readtad`'s own copy use it.
- **`_format/record.py`** — `decode_record(...) -> RecordParts`, the one pipeline: read the entry's bytes, reassemble
  extension blocks, KOD-decode, then check and decompress every chunk. `RecordParts` holds the decoded `data` and
  what `inspect crodump` prints: the entry's flags, the extension block chain, the bytes read past the record's end
  (`tail`), whether the record was compressed, and the chunks whose CRC did not match.

`Datafile.readrec(idx)` returns `decode_record(...).data`, as today. A new `Datafile.read_record(idx)` returns the
`RecordParts`. `Datafile.dump` prints from `RecordParts`. `Datafile.isv3`, `isv4`, `isv7` and `isencrypted` are
removed; their version lists come from `_format/header.py`, which already holds them (the roadmap's Phase 3 item).
`Datafile`, `tad.py` and `record.py` are fully annotated and ty-clean; `KODcoding` gains annotations only where
`record.py` calls it.

**Why:** the edge cases the reader handles were worked out over PR 2, PR 3 and Phase 1; moving the code in small
steps under the existing tests keeps them. A layout per generation is the seam Phase 4 (v7, after 1.0) needs.

**Rejected:** a new reader written beside `Datafile`, then swapped in (a rewrite that must re-prove every edge case,
and makes `inspect`'s byte-identical output harder to keep); extracting one private method and keeping the v3/v4
branches inside `Datafile` (no seam for another version).

### A2. The v3 inline flag is bit 31 of the length

A v3 `.tad` entry is deleted when its length field is `0xFFFFFFFF`. Otherwise bit 31 is the inline flag and bits
0–30 are the length. Today the flags are read as `length >> 24` and the length masked with `0x0FFFFFFF`, so bits
24–27 count as both flag and length. `docs/cronos-research.md` says only the top bit is a flag, and every real v3
entry agrees (see Evidence). The v4 layout is unchanged: the flags are the top byte of the offset, and `0xFFFFFFFF`
in the length marks a deleted entry.

### A3. A CRC mismatch keeps the data and is reported

Each compressed chunk's stored CRC-32 is compared with `zlib.crc32` of its decompressed bytes. On a mismatch the
record is still decoded and returned; `RecordParts` lists the mismatched chunks. The API records a new
`DiagnosticKind.CHECKSUM_MISMATCH` (`"checksum_mismatch"`) naming the file and record, once per record, as it does
`corrupt_record`. It reaches `bank.diagnostics`, `bank.diagnostic_counts`, `on_diagnostic`, the export's stderr, the
JSON Lines stream and `--strict`.

**Why:** an investigator keeps the text of a damaged record and knows it is suspect; one flipped bit does not cost
a whole record. The API's documented promise that later versions may add `DiagnosticKind` members covers the new
kind.

**Rejected:** treating a mismatch as a corrupt record and skipping it; keeping the data without a diagnostic.

### A4. A record may decompress to at most 256 MiB

Decompression stops once a record's output would pass 256 MiB (`MAX_DECOMPRESSED_BYTES = 256 * 1024 * 1024`),
using `zlib`'s `max_length` so that no more than that is ever held, and the record raises `ValueError` naming the
record, the file and the limit. The API reports it as `corrupt_record` and skips it, as it does any record it cannot
decode. There is no option to change the limit.

**Why:** a crafted record can inflate each chunk about a thousandfold and hold any number of chunks, so memory is
unbounded today. 256 MiB is more than 3,000 times the largest real record seen and leaves room for large stored
files.

**Rejected:** a 64 MiB limit (could refuse a large stored file); a command-line option and `open()` parameter (public
surface for a case no real database has shown).

### A5. Error contracts stay as they are

| Condition | Result |
|---|---|
| a record shorter than its `.tad` length, a short extended-record header, a length past the end of the file, looping extension blocks, a block past the end of the file, corrupt deflate data | `ValueError` naming the record and the file, as today; the API reports `corrupt_record` and skips the record |
| decompressed output over 256 MiB | the same `ValueError` path (A4) |
| a chunk whose CRC does not match | data kept; `checksum_mismatch` (A3) |
| a `.tad` entry whose length is `0xFFFFFFFF` | a deleted record: `readrec` returns `None`, as today |
| a v4 entry with flag `02` or `03` | read as a live record, as today (3d) |
| bytes that look compressed by chance | unchanged detection (`iscompressed`); a wrong guess now surfaces as `checksum_mismatch` or `corrupt_record` rather than passing as garbage |
| record number 0 | `ValueError` naming the file, in place of today's bare `Exception` |

### A6. `inspect crodump` marks a mismatched record

A record with a CRC mismatch is dumped as today, followed by ` <checksum mismatch>` at the end of its line. Every
other line of `inspect crodump`, `recdump` and `strudump` stays byte for byte the same; the golden files do not
change, because none of their records mismatches.

## Testing

Tests are written first, against real files from `tests/cronos_builder.py`; nothing is mocked.

- **`tests/test_tad.py`:** each `TadLayout` on entries built as bytes — inline and extended, deleted, v3 with bit 31
  set and clear, lengths using bits 24–30, v4 flags in the offset's top byte, 32- and 64-bit entries.
- **`tests/test_record.py`:** `decode_record` on inline, extended, KOD-encoded and compressed records; a multi-chunk
  record; a CRC mismatch in one chunk of several; a crafted chunk that inflates past 256 MiB, refused without
  holding more than the limit; each `ValueError` of A5.
- **Builder:** `tests/cronos_builder.py` gains the 32-bit v3 layout with the flag in bit 31, `01.02` and `01.03`
  written KOD-encoded, and compressed records with a deliberately wrong CRC; each is tested in
  `tests/test_cronos_builder.py`.
- **API and command line:** `checksum_mismatch` in `bank.diagnostics` and `bank.diagnostic_counts`, on the export's
  stderr and in its summary, as a JSON Lines diagnostic line, and making `--strict` exit 1; a record over the limit
  reported as `corrupt_record`; `inspect crodump`'s marker.
- **`tests/test_damage.py`:** a seeded random-damage test. From a fixed seed it builds databases of each version the
  builder writes, flips and truncates random bytes of their `.dat` and `.tad` files, then opens each with
  `cronos_extract.open()` and reads every table, record and file. It asserts that the only exception is a
  `CronosError`, that nothing is printed, and that each database is read within a time limit. About 200 cases and a
  few seconds, deterministic from the seed; a failing case names its seed and index so it can be replayed.
- **Guards:** the golden files, `inspect` byte for byte in particular, and every Phase 1 and Phase 2 test pass
  unchanged. The realdata tests gain a check that no real database reports `checksum_mismatch`.

## Documentation

The API module docstring lists `checksum_mismatch` among the kinds; the README's diagnostics paragraph and
`CLAUDE.md`'s `Datafile` description (the v3 flag rule, the new modules, CRC checking and the limit) are updated.
`docs/cronos-research.md` gains the CRC evidence and the v3 flag counts.

## Delivery

One pull request on the branch `phase3a-datafile-core`, one logical change per commit, in this order: this spec and
the roadmap's decision 14; the builder gaps; `_format/tad.py`; `_format/record.py` with CRC checking and the limit;
`Datafile` moved onto them, with the version methods removed; the API's `checksum_mismatch`; `inspect crodump`'s
marker; the damage test; the realdata check; the documentation; and an outcome section in the plan with the
roadmap's open items updated.

## Open items this phase records

- **3d:** whether v4 flags `02` and `03` mark deleted records, and what the third `.tad` field of some v4 databases
  holds.
- **3b:** `Datafile`'s `warn` hook still carries strings; 3b turns them into diagnostics.
