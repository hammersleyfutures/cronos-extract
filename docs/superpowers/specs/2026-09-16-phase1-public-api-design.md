# Phase 1 design: the public façade API

**Date:** 2026-09-16
**Status:** design approved section by section in brainstorming with Ben (2026-09-16); written spec awaiting Ben's review
**Builds on:** `2026-09-15-modernisation-roadmap-design.md`, its decisions 1–11 and its "Public API contract"

## Goal and scope

Phase 1 publishes the `cronos_extract` library API that Phases 2 to 5 build on, implemented over today's `Database`,
`Datafile` and `Datamodel`, which become internal. The library never prints: problems it survives are `Diagnostic`s,
and problems it cannot survive raise named exceptions.

Phase 1 also carries out the roadmap's Phase 1 open item: the survey streams its results.

**Not in Phase 1:** moving `crodump`, `croconvert` or `dumpdbfields` onto the API (Phase 2); CRC checking, reading
tables with ids above 255, one CP-1251 policy and the other Phase 3 fixes; v7 (Phase 4); full API documentation
(Phase 5).

## The API that results

This is the roadmap's contract with the refinements the decisions below make.

```python
import cronos_extract

with cronos_extract.open(path, kod=cronos_extract.Kod.default(), compact=False, on_diagnostic=None) as bank:
    for table in bank.tables:
        for record in table.records():
            record["Entry #4"].value
```

- **`open(path, *, kod=Kod.default(), compact=False, on_diagnostic=None) -> Bank`**. `path` is `str` or
  `os.PathLike[str]`; `kod=None` reads without KOD decoding.
- **`Bank`**: `tables: Sequence[Table]` (the Files table excluded), `read_file(FileReference) -> EmbeddedFile | None`,
  `files() -> Iterator[EmbeddedFile]`, `info: Sequence[FileInfo]`, `diagnostics: Sequence[Diagnostic]` (the first
  1,000), `diagnostic_counts: Mapping[DiagnosticKind, int]`, `close()`, and the context manager protocol.
- **`Bank.files_abbreviation: str | None`** and **`Table.abbreviation: str`** (P12).
- **`Table`**, **`Record`**, **`Field`**, **`FieldDefinition`**, **`FileReference`**, **`EmbeddedFile`**: P8, with
  `Field.value` as P4 gives it.
- **`FileInfo`**: P5. **`Kod`** and **`crack_kod(path, method) -> Kod | None`**: P7 and P12.
- **`Diagnostic`** and **`DiagnosticKind`**: P3, P8 and P9. The kinds are `corrupt_record`, `undecodable_field`,
  `invalid_value`, `undecodable_table`, `unsupported_table`, `unexpected_structure`, `unresolved_file_reference`,
  `unreadable_file` and `unused_kod`.
- **Exceptions**: `CronosError`, and its subclasses `NotACronosFile`, `UnsupportedVersion` and
  `DatabaseDefinitionError` (P3). `Kod.from_hex` and `Kod.from_table` raise `ValueError` for invalid input.

**Changes to the roadmap contract:** `read_file` may return `None` (P3); `EmbeddedFile` has `record` and an optional
`name` (P8); `Bank` has `diagnostic_counts` and `diagnostics` is capped (P9); `info` is a sequence of `FileInfo` (P5).
The roadmap's contract section is updated to match when this spec is committed.

## Decisions

### P1. The façade drives the internal primitives, with a `warn` hook where they print (2026-09-16)

`Bank` and `Table` call the internal primitives themselves — `Database.read_db_definition`, `TableDefinition`,
`Database.readbankrec_or_raise` and `Record` — rather than the `Database.enumerate_*` generators. The few `print`
calls inside those primitives (`decode_db_definition`, `read_db_definition`, `TableDefinition.decode`,
`Datafile.readtad`) take an optional `warn` callable. Its default prints to stderr exactly as today; the façade passes
one that records a `Diagnostic`.

**Why:**

- The contract says the library never prints. Driving the primitives keeps that promise from Phase 1 onwards, and
  tests can assert that reading through the façade writes nothing to stderr.
- The primitives already report most problems by raising (`LookupError`, `ValueError`) or collecting
  (`Record.errors`); only the `enumerate_*` generators turn those into prints. The internal change is small and
  mechanical.
- The default keeps `crodump` and `croconvert` output byte for byte, so the golden files do not move in a phase that
  should not change command behaviour.

**Rejected:** wrapping `enumerate_*` as they are, which would ship an API that prints until Phase 3; and replacing
every internal `print` with diagnostics now, which pulls Phase 3 forward and moves golden output for commands that
Phase 2 deletes.

### P2. Public names come only from `cronos_extract/__init__.py`; the internal modules stay put until Phase 3 (2026-09-16)

`cronos_extract/__init__.py` re-exports the public names and lists them in `__all__`; anything not in `__all__` is
private, and the API documentation says so. The façade is implemented in new private modules under
`src/cronos_extract/_api/`. `Database.py`, `Datafile.py`, `Datamodel.py` and the other existing modules stay where
they are; Phase 3 moves them into `_format/` as it restructures them. A `py.typed` marker ships with the package.

**Why:**

- One import path per public name keeps the surface that must stay stable at 1.0 as small as it can be.
- `open` is defined in a private module and only re-exported, so `__init__.py` does not shadow the built-in `open`.
- `crodump`, `croconvert` and `dumpdbfields` import the internal modules, and Phase 2 deletes them. Moving the
  internals now would rewrite those imports and about ten test modules' imports, and Phase 3 would move the files
  again when it splits them into a reader per format version.
- `py.typed` lets type checkers in users' projects use the API's annotations.

**Rejected:** moving the internals into `_format/` now (churn that Phase 3 repeats); flat public modules such as
`cronos_extract.bank`, which give every public name two import paths to keep stable.

### P3. What raises and what is a diagnostic (2026-09-16)

`open()` checks everything a bank needs before returning it, so a returned bank can be read.

**Raised from `open()`:**

| Exception | When |
|---|---|
| `OSError`, not wrapped | the path does not exist, is not a directory (`NotADirectoryError`), or cannot be listed (P12) |
| `NotACronosFile` | no `CroStru` pair or no `CroBank` pair; a CroStru or CroBank file that is not a regular file or cannot be opened (the `OSError` is chained); a CroStru or CroBank `.dat` shorter than its header or with an unknown magic; a CroStru or CroBank `.tad` shorter than its header (P12) |
| `UnsupportedVersion` | CroStru or CroBank is v7 or an unknown version |
| `DatabaseDefinitionError` | CroStru record 1 is missing, deleted, cut off, or refers to records CroStru does not hold; the message includes the KOD hint |

**Diagnostic kinds** — a `StrEnum` whose members are upper case and whose values are the snake-case names, so that
Phase 2's JSON output has stable strings:

| Kind | Effect on the data |
|---|---|
| `corrupt_record` | a CroBank record that cannot be read is skipped; reported once per bank, not once per table |
| `undecodable_field` | from `Record.errors`; the field is left empty |
| `invalid_value` | a date or time that does not parse; `value` falls back to the text |
| `undecodable_table` | a table definition that cannot be decoded; that table is left out and the others are kept |
| `unexpected_structure` | the warn-hook cases: duplicate definition key, missing `0x03`/`0x04` prefix, unmarked or unterminated field section, leftover `.tad` bytes; the data is kept |
| `unresolved_file_reference` | a file reference to a record that is missing, deleted, corrupt or not in the Files table |
| `unreadable_file` | CroIndex or CroSys is present but cannot be read; neither is needed to read tables, so it is reported in `bank.info` and reading goes on |
| `unused_kod` | a KOD other than the default was given, but no file is encrypted with its own KOD table (`01.04`, `01.05`, v4) |

**Contract change:** `Bank.read_file(FileReference)` returns `EmbeddedFile | None`, recording
`unresolved_file_reference` when it returns `None`. The roadmap contract gave `-> EmbeddedFile` while also saying a
file reference is survivable; both cannot hold.

**Why:**

- Today `Database.__init__` opens CroIndex and CroSys too, and a corrupt header in either (a `ValueError`, which
  `getfile` does not catch) stops the whole database opening, though reading tables never needs them.
- Today one table definition that raises ends `enumerate_tables`, losing every table after it.
- A corrupt CroBank record's table id is inside the unreadable data, and each `enumerate_records` pass walks all of
  CroBank, so today it is warned about once per table.

### P4. `Field.value` and `Field.text` by field type (2026-09-16)

`text` is exactly what `Datamodel.Field.content` returns today. `value` is:

| Field | `value` |
|---|---|
| empty (no bytes) | `None`, with `text` `""` |
| type 4, a full date | `datetime.date` |
| type 4, year only (month and day stored as `00`) | the text, such as `"1985-00-00"`, with no diagnostic |
| type 5, a time stored as `hhmm` | `datetime.time` |
| type 4 or 5 that does not parse | the text, and an `invalid_value` diagnostic |
| type 6 | `FileReference` |
| everything else: the system number, numbers, text, link fields 7, 8 and 9 (hex) | `str` |

The API documentation says that a date field's `value` may be `str` for a partial date, and that a later version may
give partial dates a type of their own, as the contract's "the set of `Field.value` types may grow" allows.

**Evidence (2026-09-16):** a read-only count over the 18 of Ben's real databases that open with the default KOD found
284,362 full dates, 2,122 year-only dates (all with both month and day `00`, none with only one of them), 401 date
fields holding non-digit text, and no type 5 fields at all. Time parsing is therefore tested only on crafted databases.

**Why:** year-only dates are an ordinary CronosPro value, not damage. Reporting each one as `invalid_value` would bury
the 401 real problems under about 2,000 non-problems, and a `PartialDate` type would add public API resting on one
observed shape.

**Rejected:** a `PartialDate(year, month, day)` type in 1.0; the text plus an `invalid_value` diagnostic.

### P5. `bank.info` is a sequence of a public `FileInfo`, which the survey uses too (2026-09-16)

`Bank.info: Sequence[FileInfo]` has one entry per Cro file pair found, in the order Stru, Bank, Index, Sys. `FileInfo`
is frozen, with `name`, `path`, `version: str`, `generation: Literal["v3", "v4", "v7", "unknown"]`, `use64bit`,
`kod_encoded`, `compressed`, `own_kod` and `problem: str | None`; the flags are `None` when `problem` is set. It is
built from `_format/header.py`'s `DatHeader`, which stays private. The survey's `SurveyedFile` is replaced by
`FileInfo`; the survey's text, `--counts` and `--jsonl` output do not change.

**Why:** the contract describes `info` as the per-file versions and flags "as the survey reports them", so one type
serves both, and Phase 2's `survey` subcommand has one to choose. Exporting `DatHeader` would freeze `version` as
bytes and the raw `unknown` and `blocksize` integers, which only the internal reverse-engineering dumps use.

**Rejected:** re-exporting `DatHeader`; a `FileInfo` for `bank.info` alongside an unchanged `SurveyedFile`.

### P6. Laziness, and when values are parsed (2026-09-16)

- `open()` reads the `.dat` headers, the `.tad` indexes (unless `compact=True`), the database definition and every
  table definition, so `bank.tables` is a ready `Sequence`.
- `Table.records()` and `Bank.files()` are generators that read one CroBank record per step and keep no list of
  records. Each `records()` call walks all of CroBank, filtering on the table id, as `enumerate_records` does today.
- `corrupt_record` is reported once per bank: the bank remembers the record numbers it has reported.
- `close()` is idempotent. After it, `records()`, `files()` and `read_file` raise `ValueError` naming the closed
  bank, and a running generator raises it at its next step; the check runs before each read, so a closed file is
  never reported as `corrupt_record` (P12).
- A record's fields, including every `value`, are decoded before `records()` yields it, so `record.diagnostics` and
  `bank.diagnostics` are complete for that record whichever views the caller reads.
- **Carried-forward item:** `survey.survey_roots` becomes a generator, and `run_survey` prints each database as it is
  found. Its `problems: list[OSError]` becomes an `on_problem` callback, so a warning about an unlistable directory
  appears when the walk reaches it. Overlapping roots are still reported once; `--counts` consumes the whole walk.

**Why parse eagerly:** diagnostics must not depend on which views a caller reads, or a CSV export that reads only
`text` would count fewer problems than a JSON Lines export of the same database. Parsing a date is a few integer
conversions, small beside the KOD decoding and decompression of every record.

**Rejected:** parsing `value` on first access.

### P7. `Kod`, and `crack_kod` over a shared private cracking module (2026-09-16)

`Kod` is a frozen value type holding `table: tuple[int, ...]`. `Kod.default()` holds `INITIAL_KOD`;
`Kod.from_table(seq)` and `Kod.from_hex(text)` raise `ValueError` for anything but a permutation of 0–255 (and, for
`from_hex`, 512 hex digits). `kod.hex()` gives the 512-digit form. `Kod` compares by table, which `unused_kod` uses.
Internally a `Kod` becomes a `koddecoder.KODcoding` for `Datafile`.

The automatic cracking steps move from `crodump.py` into the private `_api/crack.py`: the CroStru and the
CroBank/CroIndex byte-count builders, `kod_from_xref`, filling a single missing entry, and the permutation check.
`crack_kod(path, method)` opens only the files its method reads (CroStru for `strucrack`; CroBank and CroIndex for
`dbcrack`), raises `NotACronosFile` when one is missing, prints nothing and returns `Kod | None`. `crodump strucrack`
and `crodump dbcrack` keep `--fix`, `--text`, the known-string hints and the dumps, and use the shared steps;
`tests/test_crack.py` and the golden files show their output unchanged.

**Why:**

- `crodump.crack_kod` builds an argparse command line to call its own handler. A public function over it would tie the
  library to a command module that Phase 2 deletes, and Phase 2's `crack` subcommand should build on the library.
- The cracking statistics exist once.
- Both crack methods open `Database`, which opens CroSys too, so a corrupt `CroSys.dat` stops a crack that never
  reads it (the problem P3 describes for `open`).
- `Kod.from_table` validating a permutation is stricter than today's `--kod`, as the contract asks.

**Rejected:** wrapping `crodump.crack_kod`; a second cracking implementation for the API.

### Evidence: the "Section 2 not marked with a 2" warning (2026-09-16)

On `test_data/all_field_types` `TableDefinition` warns "FieldDefinition Section 2 not marked with a 2" for every table,
so a crafted database always reports that `unexpected_structure` diagnostic. A read-only count over the 18 of Ben's
databases that open with the default KOD found it for 4 of 115 tables, in 2 databases, and no other structure warning.
P3 stands: on real databases the diagnostic is rare, and tests over crafted databases assert it rather than an empty
diagnostic list.

### P8. The public data types (2026-09-16)

- **`FieldDefinition`** (frozen): `name: str`, `type: int`. The type codes are documented; an `IntEnum` would reject
  codes not yet met.
- **`Table`**: `id: int`, `name: str`, `fields: Sequence[FieldDefinition]`, `records() -> Iterator[Record]`.
- **`Record`**: `number: int`, `fields: Sequence[Field]`, `diagnostics: Sequence[Diagnostic]`. `record[name]` returns
  the first field with that name and raises `KeyError` when there is none.
- **`Field`**: `definition`, `value`, `text`, `raw`. `raw` is the bytes stored in the record; the system number is not
  stored, so its `raw` is `b""`.
- **`FileReference`** (frozen): `name: str`, `extension: str`, `record: int | None`, which is `None` when the stored
  record number is not a number; `read_file` then reports it as `unresolved_file_reference`.
- **`EmbeddedFile`** (frozen): `record: int`, `data: bytes`, `name: str | None`. Read through a reference, `name` is
  `"stem.extension"`, or the stem alone when the extension is empty; from `bank.files()` it is `None`, because the
  Files table stores no names.
- **Addition to P3:** a table whose id is above 255 stays in `bank.tables`; its `records()` yields nothing and
  records an `unsupported_table` diagnostic once per bank. Record data holds the table id in one byte, so today such a
  table's records vanish silently; Phase 3 removes the limit.

**Why `EmbeddedFile` has an optional name:** the Files table holds only a table-id byte and the file's bytes; names
live only in type 6 references. An invented name such as `"1234"` could not be told from a real one, and holding the
`FileReference` itself would be circular for a caller who already has it.

**Rejected:** `EmbeddedFile` with `reference: FileReference | None`; `EmbeddedFile` with an invented `name: str`.

### P9. `Diagnostic`, the callback, and bounded memory (2026-09-16)

`Diagnostic` is frozen: `kind: DiagnosticKind`, `message: str`, `file: str | None` (a file name such as
`"CroBank.dat"`), `table: str | None` (a table name), `record: int | None`, `field: str | None` (a field name).
`on_diagnostic` is called synchronously as each diagnostic is recorded; an exception it raises reaches the caller,
which is how a caller stops reading early.

`bank.diagnostics` keeps the first 1,000 diagnostics; `bank.diagnostic_counts: Mapping[DiagnosticKind, int]` counts
every one, and `on_diagnostic` receives every one. The limit is a documented module constant, not an `open()` option.

**Why:** on a database read with the wrong KOD, or a CroBank of garbage, every record can yield diagnostics; keeping
them all is unbounded memory on untrusted input. Phase 2 needs only the counts for its summary and `--strict`, and the
callback for streaming to stderr.

**Rejected:** keeping every diagnostic unless a callback is given, which leaves library callers without one exposed;
keeping every diagnostic always.

### P10. Real databases are read by opt-in `realdata` tests that check invariants only (2026-09-16)

`pyproject.toml` deselects the `realdata` marker by default (`addopts = "-m 'not realdata'"`), so CI and ordinary runs
never collect those tests; `uv run pytest -m realdata` runs them. They read `local/mash_datasets_with_CroIndex_dat.txt`
at run time. Test ids are indexes such as `db07`, and the committed
code holds no paths and no dataset names. For every listed database:

- `open` succeeds or raises a `CronosError` subclass, never anything else;
- reading every table writes nothing to stdout or stderr;
- the façade's record count, and each field's `text`, equal what `Database.enumerate_records` gives today;
- `bank.info` agrees with the survey.

For the `01.11` databases, `crack_kod(path, "dbcrack")` returns a `Kod` that opens them, which tests cracking on real
own-KOD data.

**Why:** the `01.03` (64-bit v3) and `01.11` (v4, own KOD) files exist only in `local/`. As committed tests the checks
can be run again after each Phase 3 restructuring, which is when they matter most. A marker deselected by default keeps
CI output free of skips.

**Rejected:** a scratchpad script with results recorded only in the plan's outcome; tests that skip when `local/` is
missing.

### P11. The test builder writes every v3 version and `01.11` (2026-09-16)

`tests/cronos_builder.py` takes a `version` for `01.02`, `01.03`, `01.04`, `01.05` and `01.11`: the `.dat` header
version, the `.tad` header (8 bytes for v3, 16 for v4), the entry size (12 bytes, or 16 for 64-bit) and where the
record flags are stored (the top byte of the length for v3, of the offset for v4). The default stays `01.04`, so
existing tests do not change. Each layout is tested in `tests/test_cronos_builder.py`, and the façade tests that
depend on layout are parametrised over the versions. The `realdata` tests check that a built `01.03` and `01.11`
database has the same `.tad` layout as the real files, so that the builder is not just the reader's own assumptions
written backwards. `01.13` and `01.14` are left out: there are no real files to check them against.

**Why:** without it, CI never runs the 64-bit or v4 paths, and Phase 3 would restructure those paths with only Ben's
machine to guard them.

**Rejected:** checking other versions only in `realdata`; leaving the builder work to Phase 3.

### P12. Refinements from Fable's review of the written spec (2026-09-16)

Fable reviewed this spec against the code. Each finding below was checked against the source before it was adopted.

**Opening and errors**

- A CroStru or CroBank `.tad` shorter than its header raises `struct.error` in `Datafile.readtad`; `open()` turns it
  into `NotACronosFile`. A `.dat` without a `.tad`, or a `.tad` without a `.dat`, is a missing pair: `NotACronosFile`
  for Stru or Bank, and a `FileInfo` whose `problem` says which half is missing (with `unreadable_file`) for Index or
  Sys.
- `open()` lets `NotADirectoryError` propagate for a path that is a file, as it does other `OSError`s, and raises
  `TypeError` for a `bytes` path, which `os.listdir` would answer with `bytes` names that never match.
- `open()` reads headers through its own `O_NONBLOCK`-and-`fstat` opener, not `survey.survey_file`, whose
  stat-then-open window is a Phase 3 item.
- `DiagnosticKind` may gain members in later versions; the documentation tells callers to handle unknown kinds.
- `__all__` includes `open` on purpose, as the roadmap contract names it; `from cronos_extract import *` therefore
  shadows the built-in `open`, and the documentation recommends `import cronos_extract`.

**Diagnostics**

- `TableDefinition.decode`'s two catch-all warnings ("Error … parsing FieldDefinitions" and "Error … parsing
  Tabledefinition") are `unexpected_structure`: today the table is kept, with the fields read so far.
- `unused_kod` fires when `kod` is not `None`, its table differs from `Kod.default()`'s (so
  `Kod.from_table(INITIAL_KOD)` counts as the default), and neither CroStru nor CroBank is both `own_kod` and
  `kod_encoded`.
- Diagnostics from decoding a record (`undecodable_field`, `invalid_value`) are recorded each time the record is
  decoded, so iterating a table twice records them twice. Only `corrupt_record` and `unsupported_table` are
  deduplicated per bank. Phase 2 documents what its summary counts.
- The corrupt record numbers already reported are kept in a `bytearray` bit set sized from the CroBank `.tad`, not a
  `set[int]`, so a CroBank where every record is corrupt costs one bit per record.
- No diagnostic message embeds record data; today's `undecodable_field` warning appends the whole record in hex,
  which would let 1,000 kept diagnostics hold gigabytes.
- A diagnostic is appended to `bank.diagnostics` (while under the cap) and counted before `on_diagnostic` is called.
  `bank.diagnostics` and `bank.diagnostic_counts` are read-only views that grow; `diagnostic_counts` holds only kinds
  that occurred.
- `Diagnostic.file` is the canonical name, such as `"CroBank.dat"`, whatever the case on disk; `FileInfo.path` keeps
  the on-disk spelling.

**Data types**

- `Field.raw` is the field payload: without the `0x1e` separator, and without a complex field's `0x1b` marker and
  length. The system number's `raw` is `b""`.
- `FileReference.record` is an `int` only when the stored text is ASCII decimal digits; `" 12 "`, `"+12"` and `"1_2"`,
  which `int()` accepts, give `None`.
- `Table` gains `abbreviation: str`, and `Bank` gains `files_abbreviation: str | None` (the Files table's, `None`
  without a `Base000` key), because today's CSV export names its directory `Files-<abbreviation>` and Phase 2 must be
  able to keep that layout.
- `Table.fields[0]` is the system number; `record.fields[i]` is described by `table.fields[i]`, and every record has
  exactly `len(table.fields)` fields. `bank.tables` is in database-definition order. Generators from different tables,
  or two from one table, may be interleaved on one thread.
- Without a `Base000` key, `files()` yields nothing and every `read_file` returns `None` with
  `unresolved_file_reference`.
- `FileInfo.path` is a `pathlib.Path`; `generation` is narrowed to its `Literal` when `FileInfo` is built.
- `Kod.from_hex` accepts exactly 512 hex digits in either case and nothing else, not even whitespace.

**Cracking**

- `crack_kod(path, method: Literal["strucrack", "dbcrack"])` raises `NotACronosFile` only when the directory has no
  CroStru or CroBank pair. A missing CroIndex makes `dbcrack` return `None`, as today, since that database is
  legitimate.
- A record that cannot be read while cracking is skipped, not raised: reading encrypted records without a KOD can make
  a record look compressed by chance, and today the resulting `ValueError` ends the crack.

**Builder and tests**

- The builder rejects a `kod` for `01.02` and `01.03`, whose records `Datafile` always decodes with the default KOD.
- The builder writes no deleted entries for `01.11`, because how v4 marks a deleted record is unsettled (see the open
  items); the `realdata` tests record the flag values found in real `.tad` files.
- `realdata` guarantees that committed code and test ids hold no paths. Failure output may name paths, which is
  acceptable because the tests run only on Ben's machine.
- Until the `__init__` commit, tests import from `cronos_extract._api`; that commit moves them to `cronos_extract`.
- Parity tests capture the stderr that `Database.enumerate_records` prints separately from the assertion that the
  façade prints nothing. The 1,000-cap test builds a CroBank with more than 1,000 corrupt records and is not marked
  slow.
- The documentation recommends `compact=True` for a very large `.tad`, which is otherwise read into memory.

**Declined:**

- An exception `path` attribute: the message names the path, and an attribute can be added later without breaking
  callers.
- A `compact` option on `crack_kod`: it can also be added later without breaking callers.

## Architecture

### Modules

All new modules are fully annotated and ty-clean.

| Module (`src/cronos_extract/_api/`) | Holds |
|---|---|
| `errors.py` | `CronosError`, `NotACronosFile`, `UnsupportedVersion`, `DatabaseDefinitionError` |
| `diagnostics.py` | `DiagnosticKind`, `Diagnostic`, and a private log: the capped list, the counts, the callback and the record numbers already reported as corrupt |
| `kod.py` | `Kod` |
| `info.py` | `FileInfo`, built from `DatHeader`; `survey.py` imports it |
| `values.py` | `FieldDefinition`, `Field`, `FileReference`, `EmbeddedFile`, `Record`, and the conversion from `Datamodel.Field` to a public `Field` |
| `bank.py` | `open`, `Bank`, `Table` |
| `crack.py` | the shared cracking steps and `crack_kod` |

`src/cronos_extract/__init__.py` re-exports the public names and lists them in `__all__`. `src/cronos_extract/py.typed`
marks the package as typed.

### What `open()` does

1. Lists the directory once and matches `Cro{Stru,Bank,Index,Sys}.{dat,tad}` case-insensitively.
2. Builds a `FileInfo` per pair found. A missing CroStru or CroBank pair, or a header that is short or has an unknown
   magic, raises `NotACronosFile`; v7 or an unknown version raises `UnsupportedVersion`. CroIndex and CroSys are not
   opened as `Datafile`s: only their `FileInfo` is read, and a problem there is `unreadable_file`.
3. Opens the CroStru and CroBank `Datafile`s with the `warn` hook. When `kod` is neither `None` nor `Kod.default()` and
   no file is encrypted with its own KOD, records `unused_kod`.
4. Reads the database definition; a `ValueError` becomes `DatabaseDefinitionError`, whose message names
   `cronos_extract.crack_kod` as the way to recover a database's KOD.
5. Decodes each `BaseNNN` key into a `Table`; one that raises is `undecodable_table`. `Base000` is kept privately as
   the Files table.
6. On any exception, closes the files it has opened before raising.

### Changes inside the internals

- `warn` callables on `Database.decode_db_definition`, `Database.read_db_definition`, `TableDefinition` and
  `Datafile`, whose default prints to stderr exactly as today (P1).
- `Database` can be told which of its four files to open, so that the façade opens only CroStru and CroBank and
  `crack_kod` only the files its method reads. The commands keep opening all four.
- The automatic cracking steps move from `crodump.py` to `_api/crack.py` (P7).
- `survey.SurveyedFile` is replaced by `FileInfo` (P5), and `survey_roots` becomes a generator with an `on_problem`
  callback (P6).

`KOD_HINT` stays as it is for `crodump` and `croconvert`.

### Documentation

The `cronos_extract/__init__.py` module docstring states the documented promises: iteration is lazy; a `Bank` is not
thread-safe; the set of `Field.value` types may grow, and a partial date's `value` is `str`; names outside `__all__`
are private; `bank.diagnostics` keeps the first 1,000 diagnostics while `diagnostic_counts` and `on_diagnostic` see
all of them. The README gains a short "Python API" section with the example above.

## Hostile input

| Input | Result |
|---|---|
| the path does not exist or cannot be listed | `OSError` |
| the path is a file, not a directory | `NotADirectoryError` (P12) |
| the path is `bytes` | `TypeError` (P12) |
| a `Cro*.dat` or `Cro*.tad` that is a FIFO, socket, device or directory | not a regular file: `NotACronosFile` for Stru or Bank, `unreadable_file` for Index or Sys. Files are opened with `getattr(os, "O_NONBLOCK", 0)` (Windows has no `O_NONBLOCK`) and checked with `fstat` on the open descriptor, so there is no window between check and open |
| a dangling symlink named like a Cro file | for Stru or Bank, `NotACronosFile` naming the file and chaining the `OSError`; for Index or Sys, `unreadable_file`; other symlinks are followed, as the survey follows them |
| two names differing only in case, such as `CroStru.dat` and `crostru.dat` | the first in sorted order is used, and `unexpected_structure` names the other |
| a path, table or field name that is not valid UTF-8 or CP-1251 | kept surrogate-escaped or with replacement characters, as today; never a traceback |
| a truncated `.tad`, looping extension blocks, a corrupt zlib chunk, a `.tad` offset past the end of the `.dat` | `corrupt_record`, or `unexpected_structure` for leftover `.tad` bytes |
| any other exception from the internals while reading one record (`struct.error`, `IndexError`, `EOFError`, …) | caught for that record and reported as `corrupt_record` describing the exception; one record never ends the iteration |

Reviewers are asked to try FIFOs, sockets, dangling symlinks, undecodable names, binary files where definitions are
expected, truncated and corrupt `.dat` and `.tad` files, a wrong KOD, a table id above 255, and an `on_diagnostic`
callback that raises.

## Testing

Tests are written first, against real databases from `tests/cronos_builder.py`; nothing is mocked. Every façade test
asserts that stdout and stderr stay empty.

- `tests/test_api_open.py`: each row of P3's exception table and of the hostile-input table, with FIFOs, sockets and
  dangling symlinks made by `os.mkfifo`, `socket.bind` and `os.symlink`; each asserts the exception type or the
  diagnostic's kind and fields, and a fragment of the message.
- `tests/test_api_values.py`: each row of P4's table, and a file reference whose record number is not a number.
- `tests/test_api_bank.py`: a generator reads one record per step; `records()` after `close()` raises; a corrupt
  record is reported once across two tables; `unsupported_table`; the 1,000 cap with complete counts; a callback that
  raises; `read_file` and `files()`; and parity — the façade's `text` equals `Database.enumerate_records`'s `content`
  field by field — parametrised over the P11 versions.
- `tests/test_api_kod.py` and `tests/test_api_crack.py`: `Kod` validation; `crack_kod` recovering the KOD of
  `crackable_database` by both methods; `NotACronosFile` for a missing file.
- `tests/test_survey.py`: `survey_roots` yields a database before the walk finishes; `on_problem` is called in walk
  order. The existing output tests pass unchanged.
- `tests/test_cronos_builder.py`: each version's layout (P11).
- `tests/test_realdata.py`: P10, under the `realdata` marker, which `pyproject.toml` registers and deselects by
  default.
- Every existing test passes unchanged, and `git diff tests/golden` is empty.

Crafted databases use `test_data`'s table definitions, so they report "Section 2 not marked with a 2" as
`unexpected_structure`; tests assert that diagnostic rather than an empty list.

**Guard for Phase 3:** the parity tests compare against `Database.enumerate_records`, which Phase 3 removes. Before
removing it, Phase 3 turns their expectations into golden JSON Lines of the façade's output.

## Delivery

One branch, `phase1-public-api`, and one pull request, with one logical change per commit, in dependency order: this
spec; the plan; the builder's versions; the `warn` hooks and opening a chosen set of files; errors and diagnostics;
`Kod`; `FileInfo` and the survey moved onto it; survey streaming; values; `Bank` and `Table`; the cracking
extraction; the `realdata` tests; `__init__`, the README section and `py.typed`; and an outcome section in the plan
with the roadmap's status and open items updated. Ben approves before the PR is opened, before any code-scanning alert
is dismissed, before merging, and before the branch is deleted.

## Open items this phase records

- **Phase 3, v4 deleted records:** `Datafile.readrec` treats a record as deleted only when its `.tad` length is
  `0xFFFFFFFF`, but a read-only count over Ben's 11 real `01.11` files found no such entry, and found 51 CroBank and
  117,768 CroIndex entries with flag `02`, which `docs/cronos-research.md` calls deleted. Today those are read as live
  records. Phase 1 keeps today's behaviour (the parity tests hold it) and the v4 reader in Phase 3 settles it.
- **Phase 3, KOD selection:** an own-KOD file read with `Kod.default()` is decoded with the default table, which is not its
  own, and no diagnostic says so; and `kod=None` on a KOD-encoded file raises `DatabaseDefinitionError` whose hint suggests cracking a KOD
  the caller turned off. The "one KOD-selection function" item covers both.

- **Phase 3:** `Datafile.decompress` does not limit the decompressed size. Each chunk's size is a uint16, but a record
  may chain any number of chunks and each can inflate about a thousandfold, so a crafted record can exhaust memory.
  This is not new in Phase 1; it belongs with CRC checking.
- **Phase 3:** before removing `Database.enumerate_records`, convert the parity tests to golden output (see Testing).
