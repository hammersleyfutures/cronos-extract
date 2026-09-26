# Phase 3b design: definitions and diagnostics

**Date:** 2026-09-26
**Status:** design approved by Ben (2026-09-26), section by section; reviewed by Fable against the code, whose findings
B7 records; executed unattended, as Ben asked
**Builds on:** `2026-09-15-modernisation-roadmap-design.md` (decision 14 splits Phase 3 into 3a–3d; "Open items carried
forward"), `2026-09-17-phase2-command-line-design.md` (D10, D11) and `2026-09-25-phase3a-datafile-core-design.md`

## Goal and scope

The internal readers (`Datafile`, `Database`, `TableDefinition`) report the problems they survive as structured
diagnostics with their proper kinds, instead of strings or prints; `inspect` prints them in `export`'s escaped
format; one CP-1251 decoding policy applies everywhere; the reader modules are fully annotated; and the `Database`
methods that only tests still call are removed, after their test oracle is replaced.

**Not in 3b:** the single-pass CroBank walk, KOD selection and file-reference context (3c); v4 flags and the
uncrackable v4 KOD (3d).

## Evidence gathered for this design (2026-09-26, read-only, counts only)

- **Table ids:** the 24 real databases that open with the default KOD hold 128 tables; none has an id above 255, and
  the highest is 50.
- **CP-1251:** 19 real databases under the test suite's size limit, 617,282 records, 5,230,365 text fields (types other
  than 6–9): none holds byte `0x98`, the one byte CP-1251 leaves undefined.

## Decisions

Each decision below was made with Ben on 2026-09-26.

### B1. Readers report `Diagnostic`s through a required `report` callback

`Datafile`, `Database` and `TableDefinition` take `report: Callable[[Diagnostic], object]` in place of today's
`warn: Callable[[str], None]`. It is required: there is no default, so no reader can print. Each problem is reported
with its kind and location:

| Problem | Reader | Kind | Location |
|---|---|---|---|
| leftover bytes after the last `.tad` entry | `Datafile.readtad` | `unexpected_structure` | `file` = `Cro<name>.dat` |
| a compressed record whose CRC-32 does not match, read through `readrec` | `Datafile.readrec` | `checksum_mismatch` | `file`, `record` |
| a duplicate database definition key | `Database.decode_db_definition` | `unexpected_structure` | `file` = `CroStru.dat` |
| a key's reference record not starting with `0x04` | `Database.decode_db_definition` | `unexpected_structure` | `file` = `CroStru.dat`, `record` |
| the definition record not starting with `0x03` | `Database.read_db_definition` | `unexpected_structure` | `file` = `CroStru.dat`, `record` = 1 |
| an NS1 value too short (both places) | `Database.dump_ns1` | `unexpected_structure` | `file` = `CroStru.dat` |
| a field definition section 2 not marked with a 2; an error parsing field definitions; a definition not terminated; an error parsing the table definition | `TableDefinition.decode` | `unexpected_structure` | `file` = `CroStru.dat` |

The messages lose their `WARN: ` and `Warning: ` prefixes and otherwise keep their wording. The API still prefixes a
table definition's problems with its key (`Base001: …`), as `warn_into` does today, so `export`'s output and its golden
files do not change. `hexdump.warn_on_stderr`, `_api/datafiles.warn_into` and its `WARNING_PREFIX` regex are removed.
`Datafile.read_record` keeps returning the mismatched chunks for the API, which reports CroBank mismatches itself as
it does now; only `readrec` reports through `report`.

`Diagnostic` and `DiagnosticKind` move to a new package-level module, `src/cronos_extract/_diagnostic.py`, which both
the readers and `_api` import; `_api/diagnostics.py` keeps `DiagnosticLog`, `DiagnosticsView` and `RecordNumbers`
and re-exports the two types, and `cronos_extract.__all__` is unchanged.

**Why:** the kinds are decided where the problem is understood, not recovered from message text; a CroStru checksum
mismatch gets `checksum_mismatch` instead of `unexpected_structure`; and no reader can print, which the library
promises.

**Rejected:** keeping string hooks and mapping message prefixes to kinds; readers collecting problems in a list for
callers to read afterwards (problems would arrive late, and `on_diagnostic` would no longer see them as they happen).

### B2. `inspect` prints reader problems through `_cli/report.py`

`inspect` builds one `Report` per run and passes `report.diagnostic` to the readers it constructs, so every reader
problem is one escaped `warning: kind: location: message` line on stderr, as `export` prints it. It still prints no
summary (Phase 2 D11). Its stdout does not change. The `inspect-*.stderr` golden files change; the diff is reviewed
line by line and recorded in the plan's outcome. This settles the Phase 2 open item on `inspect`'s warning wording.

### B3. One CP-1251 policy: `replace`

`readers.decode_cp1251(data: bytes) -> str` decodes with `errors="replace"`, and every CP-1251 decode in the readers
uses it: `ByteReader.readname` and `readlongstring` (already `replace`), field text in `Datamodel.Field` (today
`ignore`, which drops an undefined byte silently), `TableImage`'s file name (today `ignore`), a file reference's name,
extension and record (today `ignore`), and the NS1 password in `Database.dump_ns1` (today strict, which raises
`UnicodeDecodeError` for an undefined byte). `hexdump`'s display helpers, which decode single bytes for dumps, keep
their own handling.

**Why:** an undefined byte becomes U+FFFD, visible and never silently lost, and decoding never raises. No real field
holds such a byte (Evidence), so no real export changes.

### B4. The reader modules are fully annotated

`readers.py`, `Datamodel.py`, `Database.py`, `hexdump.py`, `koddecoder.py` and `kodump.py` are fully type-annotated and
ty-clean, joining `Datafile.py` and the `_format`, `_api` and `_cli` packages.

### B5. The dead `Database` methods are removed, after their oracle is replaced

`Database.enumerate_tables`, `enumerate_records`, `enumerate_files`, `incomplete_records`, `files_tableid`,
`get_record`, `readbankrec_or_raise` and `readbankrec` have no production caller; `enumerate_tables` and `readbankrec`
also print to stderr, which B1 forbids a reader to do. Two parity tests use `enumerate_records` as the
oracle for the API's field text (`tests/test_api_bank.py`, on built databases; `tests/test_realdata.py`, on the real
ones). They are replaced, in the commit before the removal:

- **Committed golden files** `tests/golden/api/<version>-<layout>.jsonl`, one line per record (table id, table name,
  record number, field texts), for every version the builder writes, inline and extended, over a database holding
  every field type and a stored file. A new `tests/test_api_golden.py` compares the API's output with them and rewrites
  them with `--update-golden`. When first generated, each file is checked equal to `enumerate_records`' output.
- **Local fingerprints** for the real databases: `tests/test_realdata.py` gains a test that computes, per database, the
  record count and a SHA-256 of the API's field texts over the same records the parity test compares, and compares
  them with `local/realdata-fingerprints.json` (git-ignored, keyed by the database directory), writing it with
  `--update-golden`. The fingerprints are written while the parity test still passes, so they hold what
  `enumerate_records` produced.

The builder's tests and `tests/test_database.py` move from the removed methods to the API (`cronos_extract.open()`,
`Bank.tables`, `Table.records()`, `Bank.read_file`); `KOD_HINT` stays, for `inspect strudump` and the command line's
error text.

### B6. Two items close without code

- **Tables with ids above 255.** No real table has one (Evidence), and CroBank records hold the table id in one byte,
  so there is no known layout to read. The API's `unsupported_table` diagnostic stays; the roadmap item is closed.
- **The Files table header.** It was a `croconvert` CSV defect and went with `croconvert` in Phase 2.

### B7. Refinements from Fable's review of this spec (2026-09-26)

Fable reviewed this spec against the code. Each finding below was checked and adopted; where it changes a decision
above, this section takes precedence.

- **Fingerprints are generated by the executor, before the removal (B5).** The realdata tests already read the
  git-ignored list of real databases; the rule is only that nothing from it is committed or quoted. The commit that adds
  the golden files also adds the fingerprint test, and the executor runs `uv run pytest -q -m realdata
  tests/test_realdata.py -k fingerprint --update-golden` once while `enumerate_records` still exists, then the same
  without `--update-golden`, before the removal commit. The fingerprint file is `local/realdata-fingerprints.json`,
  keyed by `str(directory.resolve())`; each value holds, per table in `bank.tables` order, the table id, the table name
  and the first `RECORDS_COMPARED` records' field texts, serialised as JSON with `sort_keys=True` and hashed with
  SHA-256, plus the record count; the test uses the parity test's skip conditions. Under `-m realdata` without
  `--update-golden`, a missing file or a missing database entry fails naming the command that writes it.
- **`inspect recdump` of a file that is not there** (`Database.recdump`'s `.dat not found` print, `Database.py:369`) is
  a reader printing a problem: `run_recdump` raises `NotACronosFile` naming the file, as `run_strudump` does for a
  missing CroStru, and exits 1 through `main`; the print goes. (This replaces Phase 2's choice 14, which kept `.dat not
  found` and exit 0.)
- **The key prefix lives in one helper.** A table definition's problems carry no file and no key from
  `TableDefinition`; one helper (in `_api/datafiles.py` or next to `Diagnostic`) returns a `report` callback that adds
  `file="CroStru.dat"` and the `BaseNNN: ` prefix, and both the API (`_api/bank.py`) and `Database.dump_db_table_defs`
  use it. `inspect-strudump.stderr` then changes from two `Warning: FieldDefinition Section 2 not marked with a 2`
  lines to `warning: unexpected_structure: CroStru.dat: Base000: FieldDefinition Section 2 not marked with a 2` and the
  same for `Base001`; that is the only golden file expected to change. The prefix, rather than `table=`, is kept on
  purpose so that `export`'s golden files do not change.
- **B1 and B2 are one commit.** A required `report` changes every constructor site at once, including `inspect`'s
  (`_cli/inspect.py` `open_database` and `run_destruct -t 2`, `Database.dump_db_table_defs`) and the tests'.
  `tests/test_datafile.py::test_leftover_tad_bytes_are_printed_without_a_warn_hook` asserts behaviour B1 abolishes; it is
  replaced by a test that the leftover bytes arrive as a `Diagnostic` and nothing is printed, and the plan names this
  replacement.
- **`crack`'s stderr changes too.** `crack`'s `raw_datafile` passes `Report().diagnostic`; a CroStru checksum mismatch it
  meets prints as `warning: checksum_mismatch: CroStru.dat record N: …` instead of `unexpected_structure`. Messages
  whose location now carries the file and record drop the words that repeated them (for example the checksum message
  says only that the compressed data's checksum does not match and the data is kept; the `.tad` message names the
  `.tad` file).
- **The golden database is the parity test's.** `tests/test_api_golden.py` uses `tests/test_api_bank.py`'s parity
  records and cases unchanged — a corrupt compressed record, an undecodable complex field, an invalid date, a deleted
  record and the own-KOD variants — over every builder version, inline and extended; KOD variants whose output is
  identical share a file, and the file names say which. In the golden commit, the parity test also asserts that each
  golden file equals `enumerate_records`' output; the removal commit deletes that test with the method.
- **The escaping test uses a hostile definition key.** The only reader message holding database bytes is the duplicate
  key's (`Database.py:156`); the test builds a database whose duplicated key name holds terminal escapes and checks
  `inspect strudump`'s stderr escapes them.
- **Smaller points.** `hexdump.strescape` decodes strictly but only receives values the regex in `dump_db_definition`
  has let through, so it keeps its handling, with a comment saying so. B3 changes `FileReference.record` for a record
  number holding an undefined byte: it becomes `None` and the reference `unresolved_file_reference`, where `ignore`
  dropped the byte and could resolve to a different record. The duplicate-key problem carries `record=1`.
  `TableDefinition`'s `image` defaults to `b""`. The documentation that B1 and B5 make false is corrected:
  `CLAUDE.md`'s `warn` hook, `enumerate_*`, `incomplete_records` and `Database.readbankrec` sentences, and
  `tests/cronos_builder.py`'s `database_with_wrong_kod_record_out_of_range` docstring.

## Error contracts

Exceptions that stop reading, the `ValueError`s naming a record, and `DatabaseDefinitionError` are unchanged. A
`report` callback that raises propagates as the `warn` hook's did; `DiagnosticLog.guard_callback_errors` still covers
the readers' broad `except` blocks.

## Testing

Tests are written first, against real files from `tests/cronos_builder.py`; nothing is mocked.

- Each row of B1's table: the problem arrives as a `Diagnostic` of that kind and location, and nothing is printed
  (`capfd`).
- API: `export`'s stderr and golden files are unchanged; a CroStru checksum mismatch reaches `bank.diagnostic_counts`
  as `checksum_mismatch`.
- `inspect strudump` and `crodump` print the new escaped lines; a table name holding terminal escapes is escaped on
  `inspect`'s stderr.
- B3: field text keeps an undefined byte as U+FFFD; an NS1 password holding it no longer raises.
- B5: `tests/test_api_golden.py`; the realdata fingerprint test.
- Guards: every earlier test, the damage test and `export`'s golden files pass unchanged; `inspect`'s stderr golden
  files change only as B2 says.

## Documentation

`CLAUDE.md` (the readers' `report` hook, `_diagnostic.py`, the CP-1251 policy, the removed methods), the roadmap's open
items and status line, and the plan's outcome.

## Delivery

One pull request on the branch `phase3b-definitions-diagnostics`, one logical change per commit, in this order: this
spec; `_diagnostic.py`, the readers' `report` callback and `inspect` through `Report`, with `inspect-strudump.stderr`
regenerated (B1, B2, B7); the CP-1251 policy (B3); the annotations (B4); the API golden files, the realdata
fingerprints and their generation (B5, B7); the removal of the dead methods and the moved tests (B5); the
documentation; and the outcome.
