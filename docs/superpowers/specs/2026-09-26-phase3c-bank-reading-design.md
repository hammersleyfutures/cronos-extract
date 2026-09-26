# Phase 3c design: bank reading

**Date:** 2026-09-26
**Status:** design approved by Ben (2026-09-26), section by section; reviewed by Fable against the code, whose
findings C7 records; Ben asked for it to be implemented after the review
**Builds on:** `2026-09-15-modernisation-roadmap-design.md` (decision 14 splits Phase 3 into 3a–3d; "Open items carried
forward"), `2026-09-16-phase1-public-api-design.md` and `2026-09-26-phase3b-definitions-diagnostics-design.md`, whose
plan's Outcome leaves two items for 3c

## Goal and scope

Reading a database takes time proportional to its records, not to its tables times its records; the KOD a file is
decoded with is chosen in one function, which reports when the KOD given does not fit the file; a file reference that
cannot be read is reported where the reference is; and two items 3b left are settled: an unreachable branch in
`TableDefinition.decode` goes, and `inspect destruct -t 3` says it cannot decode a CroSys record of type 3.

**Not in 3c:** v4 deleted-record flags and the v4 databases no crack method recovers (3d); moving `replaced_nul` into
the API; CroSys type 3's layout (after 1.0, given a real CroSys file).

## Evidence gathered for this design (2026-09-26, read-only)

- **Cost of the walk today:** `Table.records()` reads every CroBank record for every table. The realdata run of Phase 2
  exported one real database of about 28,000 records over 22.8 million `.tad` entries in 19.8 minutes, and
  `tests/test_realdata.py` skips 12 checks on databases whose `CroBank.tad` exceeds `MAX_BANK_TAD_BYTES` (32 MB) as
  "too large to walk once per table".
- **KOD selection today** is in two places: `Datafile.__init__` substitutes the default KOD for any file not encrypted
  with its own (`Datafile.py:46`), and `open()` reports `unused_kod` when neither CroStru nor CroBank uses a non-default
  KOD given (`_api/bank.py`). `inspect` builds `Datafile`s through `Database` and never reports `unused_kod`. An
  own-KOD file read with the default KOD, and a KOD-encoded file read with no KOD, are reported by nothing; both
  usually end in a `DatabaseDefinitionError`.
- **CroSys:** no listed real database and nothing in `test_data` holds a `CroSys.dat`; CronosPro keeps it in its
  application directory. There is no file to check a type 3 layout against.

## Decisions

Each decision below was made with Ben on 2026-09-26.

### C1. One pass indexes CroBank; each table then reads only its own records

`Bank` gains a private index of CroBank, filled as records are read rather than in a pass of its own: a scan
position (the next CroBank record number not yet indexed, starting at 1) and, per table-id byte, an `array` of the
record numbers found for it, `dict[int, array]`. Advancing the scan by one step reads record `position` through
`Bank._read`, as today, appends its number to its table-id byte's array when it is live and not empty, and moves the
position on. A deleted or empty record is not listed; a corrupt record is reported as `corrupt_record`, once as today,
and not listed; a checksum mismatch is reported, and `Bank`'s `RecordNumbers` keeps a later read of the same record from
reporting it again. A record whose table-id byte belongs to no table is listed under that byte and never read again.

`Bank._records(table)` and `Bank._files()` keep a position in their table's array. Each step yields the next record
already indexed for the table, reading and decoding it as today; when there is none and the scan has not reached the
end of CroBank, it advances the scan until a record of its table is indexed or the scan ends, and decodes that record
from the data the scan just read, without reading it again. So the first table read walks CroBank one record per step,
exactly as today, and indexes every other table's records on the way; a later table reads only its own records. Two
generators interleaved on one thread share the scan and the arrays and see every record once each.

The scan position moves on only after its record is indexed, so an exception during a step (from `on_diagnostic`, an
`OSError`, `KeyboardInterrupt`) leaves the index consistent, and the next step or call re-reads that record; the
`RecordNumbers` sets keep its diagnostics from repeating. A step whose record was indexed meanwhile by a re-entrant
call (a `records()` loop started from `on_diagnostic`) does not index it again: the step checks that the position is
still the one it read. The `unsupported_table` check for ids above 255 is unchanged. `read_file` reads its one record
directly, as today.

The arrays use type code `"I"` when its item size is 4 bytes and `nrofrecords` fits in it, else `"Q"`.

**Costs:** the `.tad` is scanned once per bank; a live record is decoded once when the table that is scanning owns it,
and at most twice otherwise (by the scan and by its table). **Memory:** the index holds one array item per live
record, whatever `compact` is. A hostile `.tad` whose every entry points at readable bytes makes every entry live, so
the bound is 4 bytes per `.tad` entry of 12 or more bytes, at most a third of the `.tad`'s size; `open()`'s docstring,
which says `compact` reads the CroBank index from disk, gains that the table index of C1 is held in memory either way.

**Unchanged:** the public API's signatures, the promise that iteration is lazy and reads one CroBank record per step
(Phase 1, P6), the export, the order of every output and diagnostic, and the golden files. The existing tests of
laziness and of stopping from `on_diagnostic` (`test_records_are_read_one_crobank_record_per_step`,
`test_an_exception_from_on_diagnostic_stops_reading_and_the_bank_still_closes`,
`test_a_later_records_pass_records_diagnostics_after_on_diagnostic_stopped_one`) stay unchanged and must pass.

**Tests:** over a built multi-table database with a Files table, a whole export reads each live CroBank record at most
twice, counted by a wrapper around the open bank's real `Datafile.read_record` that delegates to it unchanged; the
assertion is on the record numbers really read. Two interleaved generators of different tables yield the same records
as two generators run one after the other. A table read after another reads none of the other table's records. An
exception raised from `on_diagnostic` part-way through the scan, then a fresh `records()` call, yields every record.
**Realdata:** `MAX_BANK_TAD_BYTES`, `bank_is_small` and the checks they skip (12 skips in the 3b realdata run) go; the
fingerprints of the databases they used to skip are written with `--update-golden`; the plan's Outcome records how
long the largest real database's export takes.

**Why:** export time becomes proportional to records, with no change to any output, to the API or to its laziness.

**Rejected:** a public `Bank.records()` yielding `(table, record)` in CroBank order, with the export writing from it.
It decodes each record once, but changes the order of every output (SQL would write every `CREATE TABLE` first, JSON
Lines would interleave tables, CSV would hold a file open per table, which a database with thousands of tables turns
into a file-descriptor limit), every golden file, and the API contract. An index built in one pass before the first
record is yielded (the design first approved; C7) breaks P6's laziness and moves every `corrupt_record` and
`checksum_mismatch` ahead of the first record.

### C2. One function selects the KOD, and reports a KOD that does not fit the file

`koddecoder.select_kod(header, kod, filename)` returns the coder to decode the file's records with, or None, and at
most one `Diagnostic`. `Datafile.__init__` calls it in place of its inline choice and reports the diagnostic through
its `report` callback; `open()`'s own `unused_kod` check goes. Every reader of a Cro file, whether through the API or
`inspect`, therefore chooses and reports the same way, per file.

| KOD given | The file is | Decoded with | Diagnostic (`file` = `Cro<name>.dat`) |
|---|---|---|---|
| none | KOD-encoded | no KOD | `mismatched_kod`: `the file is KOD-encoded, but is read without KOD decoding` |
| none | not KOD-encoded | no KOD | none |
| the default | not KOD-encoded | no KOD | none |
| another | not KOD-encoded | no KOD | `unused_kod`: `the file is not KOD-encoded, so the KOD given is not used for it` |
| the default | encoded with the default KOD | the default | none |
| another | encoded with the default KOD | the default | `unused_kod`: `the file is encrypted with the default KOD, so the KOD given is not used for it` |
| the default | encoded with its own KOD | the default | `mismatched_kod`: `the file is encrypted with its own KOD, but is read with the default one; if its records do not decode, recover its KOD by cracking it` |
| another | encoded with its own KOD | the KOD given | none |

"KOD-encoded" is bit 0 of the `.dat` header's encoding field (`DatHeader.kod_encoded`); "its own KOD" is
`DatHeader.own_kod` (versions `01.04`, `01.05` and v4). `kod_encoded` is tested first: `own_kod` matters only for an
encoded file, so a v4 file whose header is not KOD-encoded (as some real v4 databases are) takes the "not KOD-encoded"
rows and is read with no KOD, as today. "The default" is a KOD whose table equals `INITIAL_KOD`. The exact message
wording is the plan's to fix; each names what was given and what the file is.

`DiagnosticKind` gains `MISMATCHED_KOD = "mismatched_kod"`, and `_cli/report.py`'s kind order gains it.

**Crack reads raw on purpose.** `crack_kod` discards diagnostics already. The command line's `raw_datafile`
(`_cli/crack.py`) opens files without a KOD because cracking needs the encoded bytes, so it drops `mismatched_kod`
before printing; the crack golden files do not change.

**Output changes:** every Cro file opened reports for itself: an encoded v4 database opened without `--kod` reports
`mismatched_kod` for CroStru and CroBank through `export` and the API, and for CroIndex and CroSys too through
`inspect`, which opens all four. In `test_data/all_field_types` CroStru is KOD-encoded and CroBank is not, so
`tests/golden/export-postgres-nokod.stderr` gains exactly one `mismatched_kod` line, for CroStru. A database whose
CroStru and CroBank both leave a given KOD unused reports `unused_kod` twice instead of once.

**Tests:** a table-driven test of `select_kod`, one row per line of the table above, on built headers;
`test_a_kod_that_no_file_uses_is_reported` becomes per file; a subprocess test shows `inspect strudump --kod <another>`
now prints `unused_kod`; a subprocess test shows `crack strucrack` prints no `mismatched_kod`.

**Why:** the choice and its diagnostics live in one place that every reader goes through; the two silent cases of the
roadmap's open item are reported where they happen, before the `DatabaseDefinitionError` they usually lead to.

**Rejected:** a `raw=True` parameter on `Datafile` for crack (a flag on every `Datafile` for one caller); reusing
`unused_kod` for the two new cases (the problem is a KOD that does not fit, not one that goes unused); keeping the
aggregate check in `open()` (inspect would still not report).

### C3. A file reference records where it was read, and is reported there

`FileReference` gains three attributes after `record`, each defaulting to None and each compared for equality:
`table` (the name of the table holding the reference), `referrer` (the CroBank record holding it) and `field` (the
field's name). `_api/values.py`'s `decode_record` fills them in. A `FileReference` built by hand has None for each.

`Bank.read_file`'s `unresolved_file_reference` diagnostic is located at the reference: `file="CroBank.dat"`,
`table`, `record=referrer` and `field` from the reference. Its message names the target record, for example
`the file in CroBank record 99 cannot be read: CroBank has no such record`, or, when the reference holds no number,
`the file cannot be read: its record number is not a number`. On the command line this prints as
`warning: unresolved_file_reference: table "Scans", record 5, field "Photo": the file in CroBank record 99 cannot be
read: CroBank has no such record`. For a hand-built reference the location is `CroBank.dat` alone.

The message does not name the file: `Diagnostic` promises that a message never holds CroBank record data, and a file
name is record data. The location identifies the reference, and `reference.name` holds the name. The target record
number is parsed from the field, but a record number is a location, as in every diagnostic's `record`, and messages
already name CroBank record numbers; the promise concerns record content. The `Diagnostic` docstring says so.

Equality now includes the context, so two references to one file from different records are unequal. Nothing
compares or deduplicates `FileReference`s: the CSV export names referenced files by their CroBank record, and the CSV
and JSON Lines writers read only `name`, `extension` and `record`, so no export output changes.

**Output changes:** the unresolved-reference assertions in `tests/test_cli_export.py`, the `read_file` tests in
`tests/test_api_bank.py`, and any golden file holding an unresolved reference. `tests/golden/api/*.jsonl` do not
change: they hold field text, not values.

**Tests:** a built database whose file field refers to a missing record reports `unresolved_file_reference` at the
referring table, record and field, through the API and on the export's stderr; a decoded `FileReference` carries its
table, referrer and field.

**Why:** the open item: the diagnostic named the target record and the reason, but not the record holding the
reference.

**Rejected:** `read_file(reference, *, table=, record=, field=)` (context only as good as each caller makes it);
naming the file in the message only (breaks the `Diagnostic` promise, and still no referring record).

### C4. The unreachable branch in `TableDefinition.decode` goes

The `except Exception` clause after `except EOFError` around the terminator's `readdword()` (`Datamodel.py`) is
removed: `ByteReader.readdword` raises only `EOFError`, which the clause before it handles. Nothing tests it, so no test
changes.

### C5. `inspect destruct -t 3` says a CroSys type 3 record cannot be decoded

`destruct_sys3_def` is removed. `destruct_sys_definition` raises `ValueError("CroSys record type 3 cannot be decoded:
its layout is not known")` for type 3, which `run_destruct` already turns into one `Error:` line and exit status 1.
Type 4 keeps its decoder. The `-t` help says type 3 records are recognised but not decoded. A subprocess test pins the
`Error:` line and the exit status.

**Why:** there is no CroSys file to learn type 3's layout from (Evidence), and printing nothing with exit 0 looked like
success.

### C6. Records

- The roadmap: the 3c open items (the single-pass walk, KOD selection, file-reference context) are marked done; "CroSys
  record type 3, given a real CroSys file" joins "After 1.0"; the status line names 3c.
- `CLAUDE.md`: the KOD section describes `select_kod` and `mismatched_kod`, and the Datafile paragraph's sentence on
  substituting the default KOD points to it; the realdata note loses "too large" if it has one.
- The Phase 1 promise that iteration is lazy stands (C1); `open()`'s docstring gains the index's memory (C1).
- `docs/cronos-research.md` is unchanged.
- The plan ends with an Outcome section, as every plan does.

### C7. Refinements from Fable's review of this spec (2026-09-26)

Fable reviewed this spec against the code. Each finding below was checked and adopted, and the decisions above already
include it.

- **Laziness (Critical).** The first C1 built the whole index before the first record was yielded. That breaks Phase 1's
  P6 (a generator reads one CroBank record per step) and the roadmap's "iteration is lazy", and fails
  `test_records_are_read_one_crobank_record_per_step` and the `on_diagnostic` stopping test. C1 now fills the index as
  records are read, with a shared scan position, so laziness and diagnostic order are as today.
- **A scan that stops part-way** (an exception from `on_diagnostic`, `OSError`, an interrupt, a re-entrant call) leaves
  the index consistent: the position moves only after its record is indexed (C1).
- **Memory** is bounded by one array item per `.tad` entry, whatever `compact` is, and `open()`'s docstring says so; the
  array's type code is chosen by its item size (C1).
- **KOD precedence:** `kod_encoded` is tested before `own_kod`, so an unencoded v4 file is read with no KOD, as today
  (C2).
- **`inspect` opens all four Cro files,** so it reports `mismatched_kod` for CroIndex and CroSys too; `test_data`'s
  CroBank is not KOD-encoded, so the `--nokod` golden file gains one line, not two (C2).
- **Record numbers in messages** are locations, not record content; the `Diagnostic` docstring says so (C3).
- **`FileReference` equality** now includes the context; nothing depends on it (C3).
- **The read-count test** wraps the real `Datafile.read_record` and delegates to it unchanged; it asserts on records
  really read, not on the wrapper (C1).

## Delivery

One branch, `phase3c-bank-reading`, one pull request, commits in this order, each with its tests and green:

1. C4 and C5 (independent, small).
2. C2: `select_kod`, `mismatched_kod`, `Datafile`, `open()`, the crack filter, golden files.
3. C3: `FileReference`'s context and `read_file`'s location.
4. C1: the CroBank index, its read-count test, then the realdata changes and fingerprints.
5. C6: the roadmap, `CLAUDE.md`, the plan's Outcome.

The realdata run (`uv run pytest -q -m realdata`) is made after step 4 and its counts recorded, never its database
names.
