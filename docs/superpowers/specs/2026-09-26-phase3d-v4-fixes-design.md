# Phase 3d design: what the v4 evidence settles

**Date:** 2026-09-26
**Status:** design approved by Ben (2026-09-26), section by section; reviewed by Fable against the code, whose
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

- **v4 `.tad` bit `0x02` with bit `0x01` clear is "deleted".** In every v4 `.tad` holding such entries, the header's
  deleted count equals the number of entries whose flag byte is `02` or `06`: 47 = 47 flag `02` (one CroBank),
  4 = 4 (another CroBank), 1 = 1 (a CroIndex), and 199,273 = 117,767 flag `02` + 81,506 flag `06` (a CroIndex). That
  CroIndex also has 2 entries with flag `07`, which has bit `0x02` set as well as bit `0x01`; the header does not
  count them, so 199,275 of its entries have bit `0x02` set. Other flag bytes seen: `00`, `04` (the great majority of
  live entries), and `08` and `0c` (one database, whose third field holds 2023–2024 Unix times).
- **The deleted count in the header is exact for v3 too.** 10 of 30 CroBank files have a nonzero header deleted count;
  in all 10 it equals the entries marked deleted (v3 length `0xFFFFFFFF`, v4 bit `0x02` with bit `0x01` clear).
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

### D1. A v4 entry with bit `0x02` set and bit `0x01` clear is deleted

`_format/tad.py`'s v4 layout marks an entry deleted when its flag byte has bit `0x02` set and bit `0x01` clear
(`flags & 0x03 == 0x02`, with `V4_DELETED_FLAG = 0x02`), in addition to the `0xFFFFFFFF` length both generations
already treat as deleted. So flags `02` and `06` are deleted, and `07` is live. The entry keeps its offset, length
and flags: in v4 only the flag bit marks it, so its data is still in the `.dat` file. Whether a v4 entry is inline
ignores the deleted bit (`inline = bool(flags & ~0x02)`), so a deleted entry that was extended (flag `02`) is read
back through its extension blocks and one that was inline (flag `06`) is not; a live flag-`07` entry is read as
inline, as its bit `0x04` suggests. The comment above the v4 flags
records the evidence and says that `04`, `08`, `0c` and `07` are unexplained (3e).

`Datafile.read_record` returns None for it, as for a v3 deleted record, so `Table.records()`, `Bank.files()`,
`Bank.read_file` and every export leave it out. `inspect crodump` (`Datafile.dump`) dumps a v4 deleted entry's data as
it dumps a live one's, marked deleted; a v3 deleted entry prints as today, since its length is gone.

`tests/cronos_builder.py` writes a deleted v4 record as flag `02` with its data kept (it refuses today), and writes
every `.tad` header's deleted count as the number of deleted entries, as real files have it (both generations).

**Crack:** `_api/crack.py`'s `readable_records` walks record numbers up to its limit and skips deleted ones, so a
v4 file whose early entries are mostly deleted now contributes fewer records to `dbcrack` and `strucrack`. The realdata
dbcrack test (D4) is the guard; if it fails on a database it passed before, the plan reports it.

**Tests:** a v4 record with flag `02`, and one with `06`, is skipped by the API and by an export; a flag `04` record
is read; `crodump` shows a v4 deleted record's data with its marker; the layout test pins bit `0x02` and the inline
rule. `tests/test_api_bank.py`'s `golden_records` no longer leaves the deleted record out for `01.11`, so the v4 files
under `tests/golden/api/` change by that record's absence being real rather than skipped (the plan names them).

**Why:** the header counts match the flagged entries in every real file.

### D2. `open()` refuses an own-KOD CroBank with the default KOD

`open()` raises `OwnKodRequired`, a new public `CronosError` in `__all__`, when CroBank is v4, its header is
KOD-encoded, and the KOD in use equals the default one, whether it was given or left as the default. It applies to v4
only: that is where the evidence is. `01.04` and `01.05` files are also marked own-KOD, but none is among the real
databases and the builder writes `01.04` files encoded with the default table, so they keep 3c's warning. There is no
override: every own-KOD v4 CroBank seen uses a table other than the default, and an explicit `Kod.default()` cannot
be told apart from the default, since the command line builds one on every run. The check runs
right after CroBank is opened and before the database definition is decoded, so a database whose CroStru also uses its
own KOD gets this error instead of `DatabaseDefinitionError`. The message names `CroBank.dat` and the directory, says
the default KOD would decode its records as garbage, and ends with a hint naming `cronos_extract.crack_kod(path,
"dbcrack")`; the command line replaces that hint with one naming `--crack dbcrack` and `cronos-extract crack dbcrack`,
as `_cli/report.py`'s `error_message` already does for the definition error. The command exits 1 with one `Error:`
line.

Unchanged: `kod=None` (`--nokod`) keeps 3c's `mismatched_kod` warning, since it asks for no decoding; `inspect` opens
files through `Database` and keeps the warning; a KOD other than the default is never refused. CroBank's
`mismatched_kod` warning is reported while CroBank is opened, so it still precedes the error.

`open()`'s docstring and the package docstring list `OwnKodRequired` among the errors. With `--crack strucrack` on the
mixed database, strucrack recovers the default table from its v3 CroStru and the export is then refused, whose hint
names `--crack dbcrack`, the right method.

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

The check and the cap live in `open()`, for CroBank only; `inspect crodump`'s header line keeps printing the raw
value. `tests/cronos_builder.py`'s `write_raw_datafile` gains a parameter for the header's deleted count, so a test can
write one larger than the entries.

`export`, when it is nonzero, prints one line on stderr after opening, through the same escaping stream as
diagnostics: `note: CroBank.tad lists 85 deleted records, which are not exported; inspect crodump shows what remains of
them`. It is not a diagnostic: the summary does not count it and `--strict` ignores it. JSON Lines gets one line: the `Writer` protocol
gains `deleted_records(count: int)`, which the export calls once, after the diagnostics found while opening have been
written and before the first table, and only when the count is nonzero; `JsonlWriter` writes
`{"type": "deleted_records", "count": 85}`, and the CSV and SQL writers do nothing. `open()`'s docstring and the
package docstring describe `deleted_records`.

**Output changes:** `test_data/all_field_types` lists 85 deleted records, so every `export` golden stderr gains the
note and `export-jsonl.stdout` gains the line; `tests/test_cli_export.py`'s assertions of TEST_DB's full JSON Lines
output change with them; the plan names each file.

**Tests:** `deleted_records` for built v3 and v4 databases with and without deleted records; a crafted header count
above the entry count gives the diagnostic and the cap; an export subprocess test pins the note and the JSON Lines line,
and `--strict` exits 0 on a database with deleted records and no diagnostics.

**Why:** 10 of 30 real CroBanks hold deleted records; a diagnostic would make `--strict` fail on a third of real
databases for something that is not a problem reading.

### D4. The realdata checks classify per file and catch garbage

- `tests/test_realdata.py`'s `is_v4` asks whether CroBank is v4. The `.tad` check runs on every Cro file whose own
  header is v4 and gains the assertion that the header's deleted count equals the entries D1's rule marks deleted,
  reading every entry in chunks rather than the first `TAD_ENTRIES_CHECKED`; the dbcrack test runs on every database
  whose CroBank is v4.
- A new test: for every database that opens with the default KOD and whose CroBank header is KOD-encoded, at least
  90% of its first 10,000 live CroBank records carry the table id of a table in `bank.tables` or of the Files table.
  It reads records through `bank._bank_file.read_record` and the Files table's id through `bank._files_table_id`; a
  database whose CroBank is not KOD-encoded (no KOD can decode it wrongly) is skipped, saying so, and so is one with
  fewer than 100 live records among them (too few to judge a fraction by); its failure message says how many records
  carry an id of a table the definition names but `bank.tables` left out (`undecodable_table`), so a wrong KOD and a
  left-out table are told apart. A real database that fails it is reported, not the threshold loosened.
- The mixed database now raises `OwnKodRequired`: its fingerprint is removed from `local/realdata-fingerprints.json`,
  and `V4_CRACK_XFAIL`'s reason says what the run shows: dbcrack returns None for those databases because their
  CroBank and CroIndex are not KOD-encoded, so there are no encoded records to learn from; their CroStru is encoded
  with its own KOD and holds too few records for strucrack, which is the open question (3e).

### D5. 3c's records are corrected

The roadmap's v4 open item and its 3c done item, `CLAUDE.md`'s realdata note and its KOD section (which says an
own-KOD file read with the default is reported; for a v4 CroBank it is now refused), 3c's C2 table (a dated note
pointing to D2), and the 3c plan's Outcome are corrected:
the slowest real database is a mixed-generation database with 22.87 million genuine records, which was read with the
wrong KOD. The 3c Outcome gains a dated correction paragraph rather than a rewrite. The realdata run's length is
measured again after 3d and recorded.

### D6. The roadmap

Decision 14 gains Phase 3e: research into the locked v4 CroStru files (the `.dat` header's 256 bytes, known plaintext
from CroStru's known structure), the unexplained flags `04`, `08`, `0c` and `07`, and the third field's timestamps,
with this spec's Evidence as its brief. "Open items carried forward" gains decoding KOD faster (`bytes.translate` for
the table lookup, then a position ramp): about 120 µs a record, so about 45 minutes for 22.87 million records. The
status line names 3d. The v4 deleted-records item is marked done (D1).

### D7. Refinements from Fable's review of this spec (2026-09-26)

Fable reviewed this spec against the code. Each finding was checked and adopted; the decisions above include them.

- **D2 covered `01.04` and `01.05`** (`DatHeader.own_kod` is true for them) and had no override, which would have made
  an `01.04` CroBank encoded with the default table unreadable and broken an existing test. D2 now applies to v4
  CroBank only and says why there is no override.
- **A deleted v4 entry's `inline`** was `flags != 0`, true for flag `02`; it now ignores the deleted bit (D1).
- **Crack sampling** skips deleted records, so D1 changes what `dbcrack` sees; the realdata dbcrack test is the guard
  (D1).
- **The `.tad` count check** read only the first million entries; it now reads all of them (D4).
- **The JSON Lines line** needed a way to reach the writer and a fixed order: a `Writer.deleted_records` method, after
  the open-time diagnostics (D3).
- **The garbage test** needed a denominator rule, its private accessors, and a way to tell a wrong KOD from a left-out
  table (D4).
- **The cap** lives in `open()`, and the builder needs a header deleted-count parameter (D3).
- **Records:** `open()`'s and the package's docstrings, 3c's C2 table, `CLAUDE.md`'s KOD section, and the v4 API golden
  files are named (D1–D3, D5).
- **(2026-09-26, after the realdata run)** The first evidence summed only flags `02` and `06` and missed that flag
  `07` also has bit `0x02` set. The realdata `.tad` check, counting every entry with bit `0x02`, found 199,275 such
  entries in a CroIndex whose header counts 199,273: the 2 flag-`07` entries, which have bit `0x01` set too, are not
  counted. D1's rule is now bit `0x02` set and bit `0x01` clear, and the `.tad` check (D4) counts with it.

## Delivery

One branch, `phase3d-v4-fixes`, one pull request, commits in this order, each with its tests and green:

1. D1: the v4 deleted flag, the builder, `crodump`.
2. D2: `OwnKodRequired`.
3. D3: `Bank.deleted_records`, the note, the JSON Lines line, golden files.
4. D4: the realdata checks, then a realdata run (in the background; it takes hours), fingerprints.
5. D5 and D6: the records, and the plan's Outcome.
