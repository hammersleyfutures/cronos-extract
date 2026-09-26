# Phase 3d design: what the v4 evidence settles

**Date:** 2026-09-26
**Status:** design approved by Ben (2026-09-26), section by section; to be reviewed by Fable against the code, whose
findings D7 records
**Builds on:** `2026-09-15-modernisation-roadmap-design.md` (decision 14; "Open items carried forward"),
`2026-09-25-phase3a-datafile-core-design.md` (the `.tad` layouts) and `2026-09-26-phase3c-bank-reading-design.md`
(`select_kod`, `mismatched_kod`, the CroBank index)

## Goal and scope

A v4 record marked deleted is not read as a live one; a database whose CroBank uses its own KOD is never exported as
garbage decoded with the default one; an investigator learns how many deleted records CroBank holds; the realdata
checks classify databases per file and would catch garbage; and the records written in 3c about the slowest real
database are corrected.

**Not in 3d (Ben, 2026-09-26):** unlocking the five real v4 databases whose own-KOD CroStru no crack method recovers,
the meaning of v4 flags `04`, `08`, `0c` and `07`, and the timestamps in the third `.tad` field — all Phase 3e, a
separate, time-boxed research phase; decoding KOD faster (an open item).

## Evidence gathered for this design (2026-09-26, read-only, counts only)

Over the 30 listed real databases:

- **v4 `.tad` bit `0x02` is "deleted".** In every v4 `.tad` holding such entries, the header's deleted count equals the
  number of entries whose flag byte has bit `0x02` set: 47 = 47 flag `02` (one CroBank), 4 = 4 (another CroBank),
  1 = 1 (a CroIndex), and 199,273 = 117,767 flag `02` + 81,506 flag `06` (a CroIndex). Other flag bytes seen: `00`,
  `04` (the great majority of live entries), `08` and `0c` (one database, whose third field holds 2023–2024 Unix
  times), and `07` (2 entries).
- **The deleted count in the header is exact for v3 too.** 10 of 30 CroBank files have a nonzero header deleted count;
  in all 10 it equals the entries marked deleted (v3 length `0xFFFFFFFF`, v4 bit `0x02`).
  `test_data/all_field_types`' CroBank lists 85 deleted records among its 86 entries.
- **Mixed generations exist.** One database has a v3 (`01.02`) CroStru and a v4 (`01.11`) CroBank and CroIndex, both
  KOD-encoded, marked own-KOD. The realdata harness classifies a database by its CroStru, so its v4 checks never ran on
  it.
- **That database has been exported as garbage.** Its CroBank holds 22,870,296 live records. Read with the default
  KOD, their table-id bytes are near random: the export found 28,191 records and 61,133 files, 89,324 in all, against
  22,870,296 / 256 ≈ 89,337 expected by chance. `crack_kod(path, "dbcrack")` recovers its KOD in 2 s; with it,
  199,996 of the first 200,000 records carry table id 1. Before 3c nothing was reported; 3c added one
  `mismatched_kod` line.
- **Five of the six pure v4 databases do not open** with the default KOD, with no KOD, or with strucrack's KOD: their
  CroStru is KOD-encoded with its own table and holds 3–7 records. Most of their CroBanks are not KOD-encoded. (3e.)
- **3c's records are wrong about that database.** The roadmap, `CLAUDE.md` and the 3c plan's Outcome say its reading
  time comes from v4 flag-`02` entries read as live; it comes from 22.87 million genuine records.

## Decisions

Each decision below was made with Ben on 2026-09-26.

### D1. A v4 entry with bit `0x02` set is deleted

`_format/tad.py`'s v4 layout marks an entry deleted when its flag byte has bit `0x02` set (`V4_DELETED_FLAG = 0x02`),
in addition to the `0xFFFFFFFF` length both generations already treat as deleted. The entry keeps its offset, length
and flags: in v4 only the flag bit marks it, so its data is still in the `.dat` file. The comment above the v4 flags
records the evidence and says that `04`, `08`, `0c` and `07` are unexplained (3e).

`Datafile.read_record` returns None for it, as for a v3 deleted record, so `Table.records()`, `Bank.files()`,
`Bank.read_file` and every export leave it out. `inspect crodump` (`Datafile.dump`) dumps a v4 deleted entry's data as
it dumps a live one's, marked deleted; a v3 deleted entry prints as today, since its length is gone.

`tests/cronos_builder.py` writes a deleted v4 record as flag `02` with its data kept (it refuses today), and writes
every `.tad` header's deleted count as the number of deleted entries, as real files have it (both generations).

**Tests:** a v4 record with flag `02`, and one with `06`, is skipped by the API and by an export; a flag `04` record
is read; `crodump` shows a v4 deleted record's data with its marker; the layout test pins bit `0x02`.

**Why:** the header counts match the flagged entries in every real file.

### D2. `open()` refuses an own-KOD CroBank with the default KOD

`open()` raises `OwnKodRequired`, a new public `CronosError` in `__all__`, when CroBank's header is KOD-encoded and
marked own-KOD and the KOD in use equals the default one, whether it was given or left as the default. The check runs
right after CroBank is opened and before the database definition is decoded, so a database whose CroStru also uses its
own KOD gets this error instead of `DatabaseDefinitionError`. The message names `CroBank.dat` and the directory, says
the default KOD would decode its records as garbage, and ends with a hint naming `cronos_extract.crack_kod(path,
"dbcrack")`; the command line replaces that hint with one naming `--crack dbcrack` and `cronos-extract crack dbcrack`,
as `_cli/report.py`'s `error_message` already does for the definition error. The command exits 1 with one `Error:`
line.

Unchanged: `kod=None` (`--nokod`) keeps 3c's `mismatched_kod` warning, since it asks for no decoding; `inspect` opens
files through `Database` and keeps the warning; a KOD other than the default is never refused. CroBank's
`mismatched_kod` warning is reported while CroBank is opened, so it still precedes the error.

**Tests:** a built database with a v3 `01.02` CroStru and a v4 `01.11` CroBank encoded with `random_kod(seed=1)`
raises `OwnKodRequired` with the default KOD, opens and reads its records with its own KOD, and opens with a warning
with `kod=None`; an `export` subprocess test pins the `Error:` line and exit status 1. The builder writes a database
whose files have different versions (`write_database` gains per-file versions, or the test composes `write_datafile`
calls).

**Why:** a wrong KOD on CroBank alone decodes about one record in 256 into each table, with no error: silent data
corruption of untrusted input.

**Rejected:** cracking automatically inside `open()` (hidden, possibly long work, and a second way to choose the KOD);
warning only (3c's behaviour, which let garbage through); a statistical check of decoded table ids (a header rule is
deterministic, and every own-KOD CroBank seen uses a table other than the default).

### D3. `Bank.deleted_records` and a note from `export`

`Bank.deleted_records: int` is the number of deleted records CroBank's `.tad` header states, read at open for v3 and
v4 alike (`Datafile.nrdeleted`); those records are not read. When the header states more than the `.tad` has entries,
`open()` reports `unexpected_structure` (file `CroBank.dat`) and `deleted_records` is the number of entries.

`export`, when it is nonzero, prints one line on stderr after opening, through the same escaping stream as
diagnostics: `note: CroBank.tad lists 85 deleted records, which are not exported; inspect crodump shows what remains of
them`. It is not a diagnostic: the summary does not count it and `--strict` ignores it. JSON Lines gets one line before
the first table: `{"type": "deleted_records", "count": 85}`. CSV and PostgreSQL output do not change.

**Output changes:** `test_data/all_field_types` lists 85 deleted records, so every `export` golden stderr gains the
note and `export-jsonl.stdout` gains the line; the plan names each file.

**Tests:** `deleted_records` for built v3 and v4 databases with and without deleted records; a crafted header count
above the entry count gives the diagnostic and the cap; an export subprocess test pins the note and the JSON Lines line,
and `--strict` exits 0 on a database with deleted records and no diagnostics.

**Why:** 10 of 30 real CroBanks hold deleted records; a diagnostic would make `--strict` fail on a third of real
databases for something that is not a problem reading.

### D4. The realdata checks classify per file and catch garbage

- `tests/test_realdata.py`'s `is_v4` asks whether CroBank is v4. The `.tad` check runs on every Cro file whose own
  header is v4 and gains the assertion that the header's deleted count equals the entries with bit `0x02`; the dbcrack
  test runs on every database whose CroBank is v4.
- A new test: for every database that opens with the default KOD, at least 90% of its first 10,000 live CroBank
  records carry the table id of a table in `bank.tables` or of the Files table. A real database that fails it is
  reported, not the threshold loosened.
- The mixed database now raises `OwnKodRequired`: its fingerprint is removed from `local/realdata-fingerprints.json`,
  and `V4_CRACK_XFAIL`'s reason says those databases fail because their own-KOD CroStru cannot be cracked.

### D5. 3c's records are corrected

The roadmap's v4 open item and its 3c done item, `CLAUDE.md`'s realdata note, and the 3c plan's Outcome are corrected:
the slowest real database is a mixed-generation database with 22.87 million genuine records, which was read with the
wrong KOD. The 3c Outcome gains a dated correction paragraph rather than a rewrite. The realdata run's length is
measured again after 3d and recorded.

### D6. The roadmap

Decision 14 gains Phase 3e: research into the locked v4 CroStru files (the `.dat` header's 256 bytes, known plaintext
from CroStru's known structure), the unexplained flags `04`, `08`, `0c` and `07`, and the third field's timestamps,
with this spec's Evidence as its brief. "Open items carried forward" gains decoding KOD faster (`bytes.translate` for
the table lookup, then a position ramp): about 120 µs a record, so about 45 minutes for 22.87 million records. The
status line names 3d. The v4 deleted-records item is marked done (D1).

### D7. Refinements from Fable's review of this spec

(To be filled after the review.)

## Delivery

One branch, `phase3d-v4-fixes`, one pull request, commits in this order, each with its tests and green:

1. D1: the v4 deleted flag, the builder, `crodump`.
2. D2: `OwnKodRequired`.
3. D3: `Bank.deleted_records`, the note, the JSON Lines line, golden files.
4. D4: the realdata checks, then a realdata run (in the background; it takes hours), fingerprints.
5. D5 and D6: the records, and the plan's Outcome.
