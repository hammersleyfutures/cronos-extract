# Phase 2 design: the cronos-extract command line

**Date:** 2026-09-17
**Status:** design approved by Ben (2026-09-17); the sections after the command surface were written after he accepted
the remaining design unseen, then reviewed by Fable against the code, whose findings D17 records
**Builds on:** `2026-09-15-modernisation-roadmap-design.md`, its decisions 1–11, its "Command line (Phase 2 builds to
this)" and its open items, and `2026-09-16-phase1-public-api-design.md` (decisions P1–P12)

## Goal and scope

Phase 2 replaces `crodump` and `croconvert` with subcommands of the one `cronos-extract` command, built on the public
API that Phase 1 published. The exports are CSV, PostgreSQL and JSON Lines; the HTML export, the Jinja2 templates,
`dumpdbfields.py` and the Jinja2 dependency go. Inspection and KOD cracking keep their features under
`cronos-extract inspect` and `cronos-extract crack`.

**Not in Phase 2:** the Phase 3 restructuring (type annotations throughout, one record-decoding path, a reader per
format version, one CP-1251 policy, one KOD-selection function, diagnostics in place of the internal `print` calls,
CRC checking, table ids above 255); v7 (Phase 4); the full API reference (Phase 5).

## The command line that results

```
cronos-extract survey  [--list FILE] [--counts|--jsonl] [DIR...]
cronos-extract export  --csv|--postgres|--jsonl [-o PATH] [--delimiter ,] [--no-files] [--strict]
                       [--kod HEX|--nokod|--crack strucrack|dbcrack] [--compact] DB
cronos-extract inspect strudump|recdump|crodump [subcommand options] KODOPTS DB
cronos-extract inspect destruct [-t TYPE] [-v] [-a] [--kod HEX|--nokod] [--compact] [DB]
cronos-extract inspect kodump [subcommand options] [--kod HEX|--nokod] [FILE]
cronos-extract crack   strucrack [--noninteractive] [--silent] [--sys] [--color] [--fix F]
                       [--text T] [--width N] DB
cronos-extract crack   dbcrack [--silent] DB
```

`KODOPTS` is `[--kod HEX | --nokod | --crack strucrack|dbcrack] [--compact]`.

`--csv`, `--postgres` and `--jsonl` are one required mutually exclusive group; the KOD options are another, optional
one. `survey` is unchanged from Phase 0.

## Decisions

Every decision below was made with Ben on 2026-09-17, from the questions listed in his brief. D5, D7 and D13 to D16
were written from his acceptance of the rest of the design.

### D1. The KOD options belong to `export` and `inspect`, not to the top-level parser

The roadmap's synopsis put `--kod HEX | --nokod | --crack METHOD` and `--compact` in front of the subcommand. They are
instead defined once (a shared argparse parent parser) and attached to `export` and to each `inspect` subcommand, so
they are written after the subcommand name: `cronos-extract export --csv --kod HEX DB`. `inspect kodump` reads one
named file or stdin rather than a database, so it takes only `--kod` and `--nokod`. `inspect destruct` reads hex on
stdin, but `-t 1` resolves a definition key stored by reference through CroStru (`Database.decode_db_definition`), so
it takes an optional `DB` argument, `.` by default as today, and `--compact` with it.

**Why:** `survey` and `crack` never read with a caller's KOD, so as global options they would have to be rejected for
half the subcommands with a hand-written usage error. argparse accepts a parent parser's options only before the
subcommand name, so the global form makes the natural `export --csv --kod …` a usage error, and `crodump` already
needed a second `--nokod` with `argparse.SUPPRESS` to work around exactly that. With the options on the subcommands,
argparse produces the right usage message by itself.

**Recorded in the roadmap:** its "Command line" synopsis is updated to this one.

**Rejected:** the roadmap's global form; accepting both positions, which needs the `SUPPRESS` trick on every
subparser and a hand-written error for the option given twice.

### D2. `-o` names a target that must not exist; CSV keeps a timestamped default

- `export --csv -o DIR` creates `DIR`, which must not exist. Without `-o` it creates
  `cronos-extract-YYYY-mm-dd-HH-MM-SS-ffffff/` in the current directory (today's name says `cronodump-`).
- `export --postgres` and `export --jsonl` write to stdout, or to the file `-o` names, which must not exist.
- An existing target is a usage error (exit 2). It is checked before the database is read and created after
  `open()` has succeeded, so a target that appears in between is caught by the create (D15) and nothing is ever
  overwritten.
- The export writes through paths under the output directory instead of `chdir`ing into it, so the process's working
  directory does not change.

**Why:** these databases are evidence, and a second run must not overwrite the first. Refusing before any reading
means a mistyped `-o` costs nothing. Writing PostgreSQL and JSON Lines to a named file lets users avoid shell
redirection, which on Windows PowerShell 5 re-encodes output to UTF-16.

**Rejected:** requiring `-o` for CSV; accepting an existing empty directory; `-o` for CSV only.

### D3. `export --jsonl` writes self-contained table and record lines

One JSON object per line, `ensure_ascii=False`, `\n`-terminated:

```json
{"type": "table", "table": "Люди", "table_id": 1, "abbreviation": "ЛЮ",
 "fields": [{"name": "Системный номер", "type": 0}, {"name": "ФИО", "type": 2}]}
{"type": "record", "table": "Люди", "table_id": 1, "record": 12,
 "fields": [{"name": "Системный номер", "value": "3"}, {"name": "ФИО", "value": "Иванов"}]}
```

A table's line comes before its records, and a table with no records still gets one. Fields are a list in definition
order, holding the database's own names, duplicates and empty names included. `type` in a `fields` entry of a table
line is the CronosPro field type code.

**Why:** field names inside a table can repeat or be empty, which is why `unique_sql_column_names` exists, so an
object keyed by name would have to rename fields. A record line that names its own table and fields can be grepped,
piped through `jq '.fields[] | select(.name == "ФИО") | .value'` or read by an agent without joining it to anything.
The names repeat on every line, which costs size and compresses away.

**Rejected:** fields as an object keyed by a uniquified name; positional values aligned with the table line.

### D4. A JSON Lines field carries `value` only

`value` is a JSON string, `null`, or an object for a file reference:

| Field | `value` |
|---|---|
| empty | `null` |
| date parsed as a date | `"1985-04-02"` (`date.isoformat()`) |
| date stored with only its year | `"1985-00-00"` |
| date or time that does not parse | the text |
| time | `"14:30"` (`time.isoformat(timespec="minutes")`) |
| file reference | `{"name": "scan", "extension": "jpg", "record": 40}`, `"record"` `null` when the stored number is not a number |
| everything else | the text |

`text` and `raw` are not written. `raw` may be added in a later version, which does not break a JSON reader.

**Diagnostics are lines of the stream too**, at the point they happened, so a script reading the JSON Lines alone
knows which records had problems without parsing stderr:

```json
{"type": "diagnostic", "kind": "invalid_value", "message": "the value is not a date; it is kept as text",
 "file": "CroBank.dat", "table": "Люди", "record": 13, "field": "Дата"}
```

`kind` is the `DiagnosticKind` value; `file`, `table`, `record` and `field` are present and `null` when they do not
apply. Messages and names are written as JSON string escapes, not through D10's escaping, because JSON has its own.
A record's diagnostics precede its record line, because the API decodes a record's fields before yielding it. The
same lines are written when the output goes to a `-o` file, and each one is also printed on stderr and counted in the
summary and by `--strict` (D10). A command-level problem (D10's `replaced_nul`, D17's `duplicate_table`) is written
the same way with `"file"`, `"table"`, `"record"` and `"field"` filled in as far as they apply.

**Why:** once `value` is JSON, `text` repeats it for every type but a file reference (where `text` is
`"name ext record"`) and an empty field (`""` against `null`). `raw` would roughly double or treble the output; the
`inspect` subcommands show bytes for the rare case where a decoded value has to be checked against them.

**Rejected:** `value` plus `raw` always; a `--raw` option; all three views.

### D5. A date or time field of only NUL bytes keeps Phase 1's behaviour

`raw` is the NUL bytes, `text` is `""`, `value` is `""` and an `invalid_value` diagnostic says the value is not a
date. The JSON shape freezes with `"value": ""` for that case.

**Evidence (2026-09-17):** a read-only count over the 30 listed real databases — 23 open with the default KOD, 6 raise
`DatabaseDefinitionError`, 1 was left out after 15 minutes — found 25,005,715 dates that parse, 3,739,471 empty date
fields, 225,290 year-only dates, 81,712 date fields holding other text, **no** date field whose bytes are all NUL or
all NULs and spaces, and no type 5 (time) field at all.

**Why:** the case does not occur in real data, only in a crafted or damaged database, where the bytes are genuinely
not a date and `raw` tells the caller they were there. This closes the carried-forward open item.

**Rejected:** `value` `None` with no diagnostic for date and time fields; the same for every field type, which would
change API behaviour Phase 1 froze, for a case no real database holds.

### D6. Embedded files are exported by `--csv` only

`--csv` writes the Files table and the referenced files as today (D8). `--postgres` and `--jsonl` carry file
references but no file bytes, as the PostgreSQL export does today. `--no-files` is accepted only with `--csv`; with
another format it is a usage error (exit 2), so nobody believes it excluded something.

**Why:** base64 in JSON Lines grows the output by a third more than the files themselves and turns one large file
into one very long line that line-based tools mishandle; a `bytea` table in SQL is more design and testing for
something the CSV export already does well.

**Rejected:** base64 `{"type": "file"}` lines; files in both formats.

### D7. CSV keeps today's layout and today's cell contents

- `<table name>.csv` per table, the header row holding the field names, the system number first, `--delimiter`
  unchanged, UTF-8 without a BOM.
- `Files-<abbreviation>/` holds every record of the Files table, named by its system number. The whole directory name,
  prefix included, goes through `unique_file_name(stem=f"Files-{abbreviation}", extension="", number=<Files table
  id>, used_names)` on the same `used_names` map the table CSVs use, with `files-referenced` pre-claimed casefolded.
  So an abbreviation of `Referenced`, one differing only in case, and one of 510 UTF-8 bytes each give a unique name
  within the 255-byte limit, where today the prefix is added after the fact and neither check applies (D17).
- `Files-Referenced/` holds each referenced file under its own name. It is created whenever the export met a file
  reference, resolved or not, as today.
- Names are made safe and unique as `croconvert` does today. `safepathname`, `truncate_utf8`, `unique_name`,
  `unique_file_name` and the three byte limits move unchanged into `_cli/names.py`; `unique_sql_table_name`,
  `unique_sql_column_names` and `sql_value` take an API `Table`, `FieldDefinition` and `Field` instead of
  `TableDefinition` and `Datamodel.Field`, so they read `name`, `id` and `text` (D17).
- Cells hold exactly what the API decoded. Neither a formula-neutralising prefix nor a BOM is added.

**Why:** prefixing `'` to a cell starting with `=`, `+`, `-` or `@` would change evidence and mangle `-5` and `+7…`;
a BOM puts `﻿` into the first header name for Python's `csv` module and pandas' default. The README instead says
to import a CSV through a spreadsheet's CSV import as UTF-8, never by double-clicking, because cells can hold
formulas that came from the database.

**Rejected:** a BOM; OWASP-style formula neutralising.

### D8. Referenced files are written while the records are read

The CSV export resolves each type 6 field with `bank.read_file` as it writes the record, instead of collecting every
file reference in a list and resolving them at the end. The order in which names are claimed is unchanged, because
the records are read in the same order.

**Why:** the list grew with the number of references in the database — the roadmap's Phase 3 item "the CSV export
holding every file reference in memory" — and the API makes streaming the natural way to write it. The item is marked
done in the roadmap.

### D9. PostgreSQL is written by a Python module, and Jinja2 goes

`_cli/sql_out.py` writes the SQL. Semantics are today's: every column `TEXT`, unique quoted table and column names
within 63 bytes, `NULL` for an empty value, single quotes doubled, a NUL character replaced by U+FFFD with a warning
naming the table, record and field. Two changes: the output starts with `SET standard_conforming_strings = on;`, and
the layout has no stray blank lines or trailing spaces. `templates/`, `croconvert.py`'s `template_convert` and the
`jinja2` dependency are deleted, which leaves the package with no runtime dependencies.

**Why:** one format does not need a templating engine, a dependency or a template search path; `SET
standard_conforming_strings = on;` makes the quoting correct whatever the server's setting, which today is only a
README warning.

**Rejected:** a Python writer reproducing today's bytes exactly; keeping `postgres.j2`.

### D10. Diagnostics: every one on stderr, escaped, then a summary

`_cli/report.py` is the only module that writes to stderr for `export` and `crack`; the internal readers that
`inspect` drives keep their own prints until Phase 3 (see the open items). `report.py` is passed to `open()` as
`on_diagnostic` and prints one line per diagnostic as it happens:

```
warning: invalid_value: table "Люди", record 13, field "Дата": the value is not a date; it is kept as text
warning: corrupt_record: CroBank.dat record 88: CroBank record 88 is corrupt and is skipped: EOFError

3 diagnostics: 1 corrupt_record, 1 invalid_value, 1 unexpected_structure
```

- The kind is the `DiagnosticKind` value; then whichever of `file`, `table`, `record` and `field` are set; then the
  message.
- Everything written to stderr is escaped: control characters (which could carry terminal escape sequences from a
  hostile database), surrogate-escaped bytes and other unprintable characters become `\xNN`, `\uNNNN` or
  `\UNNNNNNNN`. So one diagnostic is always one line, and nothing a database holds reaches the terminal raw **through
  stderr**. The internal readers print to stderr directly in places `warn` does not cover (`Database.dump_ns1`,
  `Database.recdump`, `Database.readbankrec`), so the escaping is a wrapper installed on `sys.stderr` for the whole
  process; it covers `export`, `inspect` and `crack` alike and changes no wording. stdout is not escaped: `inspect`
  dumps and SQL literals keep the database's bytes, which D11 requires, and the README tells users to write export
  output to a file or `-o` rather than to a terminal (D17). This closes the carried-forward escaping item.
- The summary line lists the counts by kind from `bank.diagnostic_counts`, in `DiagnosticKind` declaration order with
  command-level kinds last, and is printed once at the end, including when nothing went wrong (`no diagnostics`).
  When a fatal error stops the run, the counts so far are printed first and the `Error: …` line last, so the error is
  the last thing on stderr. `crack` prints no summary: it opens no bank, and its stderr must stay usable in
  `KOD=$(cronos-extract crack dbcrack --silent DB)` (D17).
- A command-level problem that is not an API diagnostic is printed and counted in the same shape, with its own kind:
  `replaced_nul` for D9's NUL replacement in SQL output, and `duplicate_table` for D14's skipped duplicate table.
  Both count towards the summary and `--strict`.
- There is no `--quiet`: `2>/dev/null` already silences stderr, and the summary, or the `Error: …` line after it,
  is the last thing on it.
- `--strict` (on `export`) finishes the export and then exits 1 when any diagnostic, API or command-level, was
  reported. The output written so far is kept.

**Why:** an investigator must be able to see every problem a database caused, and a diagnostic hidden behind a
`--verbose` nobody types is a silent data loss. Counting each kind gives the summary the roadmap asks for.
`export` walks each table once, so each problem is reported once, despite P12's note that decoding a record twice
records its diagnostics twice.

**Rejected:** printing only the first 100 of a kind; a summary-only default with `--verbose`.

### D11. `inspect` reads the internal readers directly, and its stdout does not change

`inspect strudump|recdump|crodump|destruct|kodump` keep their options and their output byte for byte. They call
today's internal readers, which the public API hides on purpose: raw definition keys, the unknown fields of a
`TableDefinition`, NS1, `.dat` record and byte-range dumps, and KOD decoding of an arbitrary file.

Changes:

- A database that cannot be read at all exits 1 with one `Error: …` line and no traceback. Today it does not:
  `Database.getfile` catches only `OSError` (`Database.py:101`), so a `CroIndex.dat` of ten bytes ends `strudump`,
  `crodump` and `recdump` in a `ValueError` traceback from `read_dat_header`, and an unknown `.tad` version raises a
  bare `Exception` (`Datafile.py:106`) — for a file the subcommand never reads. `_cli/inspect.py` therefore opens the
  files each subcommand needs through its own opener, which maps `ValueError`, `struct.error` and that `Exception`
  from `Datafile` construction to exit 1 naming the file, and reports a damaged CroIndex or CroSys that the
  subcommand does not need as one `warning:` line on stderr in D10's shape, and nothing else: `inspect` opens no bank,
  so it has no diagnostic counts and prints no summary (D17).
- `inspect strudump` calls `Database.dump_db_table_defs` and maps `ValueError` to exit 1 itself, with the hint;
  `Database.strudump`, which calls `sys.exit` twice (`Database.py:144,148`), is deleted as dead code.
- Text naming a command says `cronos-extract crack strucrack` and `cronos-extract export --kod`; `KOD_HINT` moves
  with it. The API's `DEFINITION_HINT` names the Python function `cronos_extract.crack_kod` and sits inside the
  exception's message (`_api/bank.py:25,250`), so `report.py` replaces that sentence with the command-line hint when
  it prints a `DatabaseDefinitionError`. The exception keeps its message; Phase 1's API does not change.
- The global `--debug` becomes `inspect recdump --debug`, its only user.
- `sysdump` is dropped: `inspect crodump` dumps CroSys among the four files, and `inspect recdump --sys` its records.
- `--strict` is not offered, because no `inspect` subcommand reads through the API.

**Why:** these commands exist to show what the API hides, so building them on the API would mean making internals
public. Keeping the bytes identical means the golden files move by name only, and Phase 3 changes their stderr when it
replaces the internal `print` calls with diagnostics.

**Rejected:** keeping `sysdump`; opening through the API in `strudump` for consistent stderr.

### D12. `crack` keeps every feature; its messages move to stderr

`crack strucrack` keeps `--fix/-f`, `--text/-t`, `--width`, `--color`, `--sys`, `--silent`, `--noninteractive`, the
known-string hints and the interactive dump. `crack dbcrack` keeps `--silent`. Both build on `_api/crack.py`'s shared
statistics, as Phase 1 arranged.

**Which files each method opens.** The shared steps cover only the statistics, so `_cli/crack.py` opens the files
itself, through `_api.datafiles.open_datafile` with a `DiagnosticLog` that `report.py` prints: `strucrack` opens
CroStru alone, or CroSys alone with `--sys`; `dbcrack` opens CroBank and CroIndex. Neither opens a file its method
does not read, so a damaged CroIndex no longer ends a `strucrack` (today it does, through `Database`), and the
`tests/test_crack.py` cases that build a directory holding only CroStru or only CroBank keep passing —
`crack_kod` could not serve them, because it opens both (`_api/crack.py:126,128`). Cracking always reads the index
from disk, as `crack_kod` does, so `crack` has no `--compact` option.

Changes:

- Failure messages ("Ambiguous result when cracking …", "no CroStru.dat file found in …") and the
  "Use the following database key …" line go to stderr, so stdout on a successful run holds the dump and the KOD hex
  only, and `KOD=$(cronos-extract crack dbcrack --silent DB)` needs no filtering.
- The hints name `cronos-extract crack strucrack -f …` and `cronos-extract export --kod …`.
- "Ambigous" is spelled correctly.
- Exit statuses: 0 when a KOD is produced; 1 when `--noninteractive` `strucrack` fails, when `dbcrack` fails
  (it is non-interactive by nature, and today such a run exits 0, which would make
  `KOD=$(cronos-extract crack dbcrack --silent DB)` succeed with an empty value), or when a file the method needs is
  missing or cannot be opened; 2 for an unparsable `--fix` or `--text` or one that does not fit the database (today a
  `CrackInputError` exit 1). `--silent` never changes the status. An interactive `strucrack` that ends with entries
  unresolved keeps exit 0; the roadmap defers interactive crack statuses to after 1.0.
- The interactive dump reads records the way `--noninteractive` does, through `_api/crack.readable_records`, so a
  record it cannot read is skipped instead of ending the crack. This closes that carried-forward item.

`export --crack METHOD` and `inspect --crack METHOD` call `cronos_extract.crack_kod`, which prints nothing, and exit
1 with one message naming `cronos-extract crack strucrack` when it returns `None`.

**Rejected:** dropping `--silent`; exiting 1 from an interactive crack that leaves entries unresolved.

### D13. `compact=False` stays the default for `cronos_extract.open()`

The API keeps `compact=False`, which reads the whole CroBank `.tad` index into memory (4.1 GB for one real database).
`--compact` on the command line, and `compact=True` in the API, are the documented way to read a very large database;
the realdata tests use it. The roadmap's open item is closed.

**Why (Ben, 2026-09-17):** the default that is fastest for ordinary databases stays the default, and the option and
its documentation cover the large ones.

### D14. Module structure, and one place that decides the exit status

```
cli.py              main(), the parser, dispatch through args.handler, exit statuses
_cli/options.py     the shared KOD and --compact parent parser, and turning it into a Kod
_cli/report.py      escaping, the stderr diagnostic line, the summary, --strict counting
_cli/export.py      opening the bank, the -o target, and one walk over the tables
_cli/csv_out.py     the CSV directory layout
_cli/names.py       the safe unique name helpers from croconvert
_cli/sql_out.py     the PostgreSQL writer
_cli/jsonl_out.py   the JSON Lines writer
_cli/inspect.py     strudump, recdump, crodump, destruct, kodump over the internal readers
_cli/crack.py       strucrack, dbcrack, the interactive dump, --fix and --text parsing
survey.py           unchanged
```

The three writers share one interface — `table(table)`, `record(table, record)`, `finish()` — so `export.py` walks the
bank once and knows nothing about formats. `export.py` skips a table whose name and id repeat one it has already
written, before calling `table()`, for every format, and reports it as `duplicate_table`: today CSV and SQL skip it
only as a side effect of their name helpers returning `None`, so a JSON Lines export would hold its records twice. Every subcommand handler has Phase 0's signature `run_*(args, parser) ->
int` and none calls `sys.exit`: `main` catches `CronosError`, `OSError`, `CrackInputError`, `BrokenPipeError` and
`KeyboardInterrupt` and turns them into a status. Every subcommand group is `required=True`, so
`cronos-extract inspect` with no subcommand is argparse's usage error and exit 2, where `crodump` prints help and
exits 0 today. This is the dispatch seam the roadmap's carried item asks for. `collect_roots` is given the
`survey` subparser instead of the top-level parser, so its usage line names `cronos-extract survey` — the second
carried item. All new modules are fully annotated and ty-clean.

**Deleted:** `crodump.py`, `croconvert.py`, `dumpdbfields.py`, `templates/` (both templates), the `crodump` and
`croconvert` console scripts, the `jinja2` dependency, `Database.strudump` (D11) and `tests/test_dumpdbfields.py`.
`KOD_HINT` and the `Database.dump*` and `recdump` methods stay, because `inspect` uses them.

**Tests that move, not go.** `tests/test_croconvert.py`, `tests/test_crodump.py` and `tests/test_crack.py` run the
deleted commands as subprocesses and import them (`croconvert`'s helpers, `crodump.build_parser` and
`crodump.derive_kod_*`), so every case moves into `tests/test_cli_export.py`,
`tests/test_cli_inspect.py` or `tests/test_cli_crack.py`, keeping its assertions except where a decision here changes
them. Only the HTML cases go, with the export they test. No case is dropped for failing.

**Dead code flagged, not removed:** once `croconvert` goes, `Database.enumerate_tables`, `enumerate_records` and
`enumerate_files` are used only by the Phase 1 parity tests, which Phase 3 replaces with golden output before
removing them (the roadmap's existing item). `_cli/export.py` never calls them.

### D15. Exit statuses

| Status | When |
|---|---|
| 0 | the command finished; skipped records and diagnostics do not change this |
| 1 | the database cannot be read at all (`CronosError`, or an `OSError` on the database directory or an output file): one `Error: …` line, no traceback. Also a failed `--crack`, a failed `crack --noninteractive`, a write error such as a full disk, and `--strict` with at least one diagnostic |
| 2 | a usage error: argparse's own (a missing subcommand included), an `-o` target that exists, `--no-files` or `--delimiter` without `--csv`, a `--delimiter` that is not one character, a `--kod` that is not 512 hex digits or not a permutation of 0–255, a `--fix`/`--text` that cannot be parsed or does not fit. A `--kod` is validated by an argparse type that raises `ArgumentTypeError` with `Kod.from_hex`'s reason, so the message is not argparse's generic "invalid from_hex value" |

`BrokenPipeError` (`| head`) exits 1 without a message and without Python's "Exception ignored" report;
`KeyboardInterrupt` exits 130 with no traceback. Output written before a failure is left in place, and the message
says where it is. `--strict` only ever raises a status: a run that already exits 1 or 2 keeps it. The output target is
created after `open()` has succeeded, so a database that cannot be read leaves no empty directory behind. `export`
reconfigures stdout to UTF-8 with `errors="backslashreplace"`, so SQL on a Windows console with a legacy code page is
not silently transcoded (D17).

### D16. Golden output tests move to the new commands, with every difference recorded

`tests/test_cli_characterisation.py` runs `cronos-extract` instead of `crodump` and `croconvert`. The golden files are
renamed in one commit (`git mv`) and regenerated in the next, so the diff of the second shows only real changes. The
harness takes an expected exit status per case, because it hard-codes 0 today and two cases now end in 1
(`export-postgres-nokod`, `crack-dbcrack`).

| Golden file | Difference |
|---|---|
| `crodump-*` → `inspect-*` | stdout unchanged; hint text names `cronos-extract` |
| `crodump-sysdump.*` | deleted with the subcommand (D11) |
| `crodump-strucrack` → `crack-strucrack` | failure and key messages move to stderr; "Ambiguous" spelled correctly; hints name `cronos-extract` |
| `crodump-dbcrack` → `crack-dbcrack` | its "Ambiguous result" line moves to stderr; exit status 0 → 1 (D12) |
| `croconvert-html.*` | deleted with the HTML export |
| `croconvert-postgres` → `export-postgres` | `SET standard_conforming_strings = on;` first; no stray blank lines or trailing spaces; stderr in the new diagnostic format with a summary |
| `croconvert-postgres-nokod` → `export-postgres-nokod` | exit status 0 → 1; one `Error: …` line naming `cronos-extract crack` in place of today's two lines |
| `croconvert-csv` → `export-csv` | the directory tree and every CSV byte unchanged; stderr in the new diagnostic format with a summary |
| `export-jsonl` | new |

Nothing else about the golden database's CSV tree changes: `Files-Referenced/` is still created whenever a file
reference was met, resolved or not, so `test_a_file_reference_to_a_record_of_another_table_is_skipped`
(`tests/test_croconvert.py:686`) keeps its assertion when it moves, and the `Files-FL` directory keeps its name,
because no collision or length limit applies to it. Databases whose abbreviations collide or are over-long get a
different directory name than today (D7), and `crack` exit statuses change (D12).

### D17. Refinements from Fable's review of the written spec (2026-09-17)

Fable reviewed this spec against the code and probed today's commands. Each finding below was checked against the
source before it was adopted; the decisions above carry the changes, and this list records where they came from.

**Opening files and exit statuses**

- `inspect` needs its own opener: `Database.getfile` catches only `OSError` (`Database.py:101`), so a ten-byte
  `CroIndex.dat` gives a `ValueError` traceback from `strudump`, `crodump`, `recdump` and `strucrack`, and an unknown
  `.tad` version a bare `Exception` (`Datafile.py:106`) — for a file the subcommand never reads (D11).
- `Database.strudump` calls `sys.exit` (`Database.py:144,148`), which D14's "no handler calls `sys.exit`" forbids, so
  it is deleted and `inspect strudump` maps the `ValueError` itself (D11).
- `crack` opens only the files its method reads, not through `crack_kod`, which opens CroStru and CroBank both
  (`_api/crack.py:126,128`) while several `tests/test_crack.py` cases build a directory with only one of them (D12).
- `dbcrack` failure exits 1. Today it exits 0, so `KOD=$(… crack dbcrack --silent DB)` would succeed with an empty
  value — the very use D12 offers (D12).
- `CrackInputError` is added to what `main` maps to a status, and a missing subcommand is exit 2 rather than help and
  0 (D14, D15).
- A wrong KOD is exit 1, not a diagnostic: `open()` raises `DatabaseDefinitionError` (`_api/bank.py:250`). The
  hostile-input row said exit 0, contradicting D16's own `export-postgres-nokod` row.

**Output and names**

- `inspect destruct -t 1` does read a database — `Database(".", …)` and `stru.readrec` for keys stored by reference
  (`crodump.py:200`, `Database.py:173-185`), which `tests/test_crodump.py:37` relies on — so it keeps an optional `DB`
  and `--compact` (D1).
- The `Files-<abbreviation>` directory is neither uniquified nor length-limited today (`croconvert.py:217`), so an
  abbreviation of `Referenced` gives `FileExistsError` and a 510-byte one `ENAMETOOLONG`, after the CSVs are written
  (D7).
- `unique_sql_table_name`, `unique_sql_column_names` and `sql_value` read `TableDefinition` and `Datamodel.Field`
  attributes (`croconvert.py:145,158,169`), so they cannot move unchanged (D7).
- `--delimiter` that is not one character is a `TypeError` traceback today (`croconvert.py:200`), and `--delimiter`
  with a format that has no delimiter was undefined (D15).
- `-o` is checked with `os.path.lexists` and created atomically, because `os.path.exists` passes a dangling symlink
  and a check-then-create gap is a race (D15).
- A duplicate table (same name and id) is skipped for every format: CSV and SQL skip it only as a side effect of
  their name helpers returning `None` (`croconvert.py:194`), so JSON Lines would export its records twice (D3, D14).
- stdout is not escaped, and cannot be while D11 keeps `inspect` byte for byte: `TableDefinition.__str__` and
  `sql_value` pass a name's control bytes through (`Datamodel.py:37-43,152`, `croconvert.py:172`). The escaping claim is
  scoped to stderr, and the README says to write export output to a file (D10).
- `export` sets stdout to UTF-8, because a Windows console with a legacy code page would transcode SQL silently
  (D15).
- The escaping is a `sys.stderr` wrapper: `Database.dump_ns1`, `recdump` and `readbankrec` print to stderr without
  going through `warn` (`Database.py:235,248,332,380`) (D10).

**Definitions the spec was missing**

- The JSON Lines diagnostic line had no shape, though Ben chose to put diagnostics in the stream (D4).
- What the summary prints when a fatal error stops a run, and that `crack` prints none, was undefined (D10).
- `tests/test_croconvert.py`, `tests/test_crodump.py` and `tests/test_crack.py` were neither deleted nor moved; they
  import `croconvert` and run the deleted commands (D14).
- Summary order is `DiagnosticKind` declaration order with command-level kinds last; `--kod` gets an argparse type
  that reports `Kod.from_hex`'s reason (D10, D15).
- `Database.enumerate_*` becomes dead code once `croconvert` goes, kept only for the Phase 1 parity tests (D14).

**Knowingly not changed**

- `--strict` will exit 1 on every crafted database, because `TableDefinition` reports "Section 2 not marked with a 2"
  as `unexpected_structure` for `test_data`'s definitions (Phase 1's evidence). The README says so.
- A database whose every record is corrupt writes one stderr line per record: D10 rejected a cap deliberately.
- `inspect destruct` and `kodump` keep today's tracebacks for bad hex, a bad `--shift`, `--offset` or `--length`; the
  roadmap puts that error handling after 1.0.

## Hostile input

| Input | Result |
|---|---|
| a `Cro*` file that is a FIFO, socket, device, directory or dangling symlink | `export`: `open()` raises `NotACronosFile`, exit 1 with one line (Index and Sys give an `unreadable_file` diagnostic and the export continues). `inspect` and `crack`: their own opener, exit 1 naming the file, and only for a file the subcommand reads (D11, D12) |
| a wrong or absent KOD, or a CroStru/CroBank `.dat` or `.tad` shorter than its header | exit 1 with one `Error: …` line: a wrong KOD decodes the definition as garbage, which `open()` raises as `DatabaseDefinitionError` (`_api/bank.py:250`), and a short header as `NotACronosFile`. D16's `export-postgres-nokod` golden file is this case |
| a truncated CroBank body, a corrupt record, looping extension blocks, a table id above 255 | diagnostics on stderr, the export finishes with exit 0 (1 with `--strict`) |
| a table, field or file name that is not valid UTF-8 or CP-1251, or holds control characters or terminal escapes | escaped on stderr (D10); made safe for file names by `safepathname` and shortened to 255 bytes; quoted for SQL with `"` replaced by `_`; written as JSON string escapes |
| a name that would escape the output directory (`..`, `/`, `\`, an empty name, only dots) | `safepathname` replaces the separators and `unique_file_name` replaces a stem that is empty or only dots with its number, so every path stays directly under the output directory. Tested with a database whose table and file names are `../../etc/passwd` and similar |
| `-o` that exists, including as a dangling symlink | exit 2. The check is `os.path.lexists`, because `os.path.exists` follows a link and would pass a dangling one, and the target is then created with `os.mkdir` or `open(mode="x")`, whose `FileExistsError` is exit 2 as well, so the check-then-create race cannot overwrite anything (D17) |
| `-o` inside a directory that is not writable, or on a read-only file system | exit 1 with the `OSError`'s message |
| a table name or abbreviation that collides with `Files-Referenced`, differs only in case, or is 510 UTF-8 bytes long | a unique, shortened name from `unique_file_name` (D7); today the `Files-<abbreviation>` directory is neither, and gives `FileExistsError` or `ENAMETOOLONG` after the CSVs are written |
| two table definitions with the same name and id | the second is skipped for every format, with a `duplicate_table` note; today only CSV and SQL skip it, and JSON Lines would export its records twice (D17) |
| `--delimiter` that is not one character, or `--delimiter` without `--csv` | exit 2; today `csv.writer` raises `TypeError` (D17) |
| a database directory that cannot be listed, or is a file | exit 1 with the `OSError` message (`NotADirectoryError` included) |
| stdout closed early (`| head`), or a full disk | exit 1, no traceback (D15) |
| hex input to `inspect destruct` that is not hex, or `inspect kodump -s zz`, `-l -5`, `-o` past the end | today's tracebacks stay: the roadmap puts "`crodump destruct` error handling" after 1.0, and this phase does not pull it forward. A binary file to `inspect kodump` already works. `inspect recdump --debug` re-raises on purpose (`Database.py:412`), the one deliberate traceback |

Reviewers are asked to try all of the above, plus a database whose every record is corrupt (stderr flood), an
`-o` directory on a read-only file system, names differing only in case, and `--fix`/`--text` values that do not fit
the database.

## Testing

Tests are written first, against real crafted databases from `tests/cronos_builder.py`; nothing is mocked. Command
tests run the real command in a subprocess through `tests/cli.py::run_command` and assert on stdout, stderr and the
exit status.

- `tests/test_cli_export.py`: each format's layout; the `-o` rules of D2 including an existing target; `--no-files`
  with and without `--csv`; the JSON Lines shape of D3 and D4 field by field, including a file reference whose record
  number is not a number, a partial date, a NUL-only date (D5) and an empty field; diagnostic lines in the stream and
  on stderr; the summary; `--strict` exit 1 with the output kept; `--delimiter`; CSV cells kept verbatim; the
  `Files-<abbreviation>` and `Files-Referenced` layout; over-long and hostile names; every exit status of D15.
- `tests/test_cli_inspect.py`: the moved subcommands and the cases from `tests/test_crodump.py`; `--debug`; a damaged
  CroIndex or CroSys that the subcommand does not read (a diagnostic, not exit 1) and one it does (exit 1, no
  traceback); `destruct -t 1` with and without a `DB`; and that `sysdump` is gone.
- `tests/test_cli_export.py` also covers `--delimiter` validation, a duplicate table skipped once per format, and an
  abbreviation that collides with `Files-Referenced`, differs only in case, or is 510 UTF-8 bytes long.
- `tests/test_cli_crack.py`: the existing `tests/test_crack.py` cases moved to `crack`, plus messages on stderr, the
  exit statuses of D12, a `strucrack` over a directory holding only CroStru and one whose CroIndex is damaged, a
  `dbcrack` over a directory holding only CroBank, and an interactive crack over a database with an unreadable record.
- `tests/test_cli_report.py`: escaping of control characters, surrogate-escaped bytes and terminal escapes; the
  summary wording; `replaced_nul`.
- `tests/test_cli_characterisation.py`: the golden files of D16.
- `tests/test_realdata.py`: for each listed database, the real command in a subprocess with `--compact`, writing to a
  temporary directory: no traceback on stderr; exit status 0, or 1 with one `Error:` line; `--jsonl` output parses
  line by line and its record count equals the API's; `--postgres` writes one `INSERT` per record. Databases whose
  CroBank index is larger than Phase 1's limit are skipped for the record-reading runs, and CSV file export runs on
  the smallest few. Test ids stay indexes such as `db07`; no path or dataset name is committed, and only counts are
  reported.
- The Phase 1 API tests and `tests/test_survey.py` pass unchanged.

## Documentation

The README is rewritten in place, keeping its order of sections, all re-pointed at `cronos-extract`: quick start with
`export --csv`, a section per export format (with the JSON Lines shape and a `jq` example), survey, inspect, crack
(both methods and the interactive workflow), the Python API section as it is, installing (one command, no
dependencies), development, terminology, licence and references. The Templates section goes, and with it every
`croconvert` and `crodump` line. The spreadsheet warning of D7 is in the CSV section. Phase 5 still adds the full API
reference.

## Delivery

This spec and the roadmap update are merged first, on the branch `phase2-command-line`, so that the plan is written
against a committed design. The plan and the implementation follow on `phase2-implementation`, as one pull request
with one logical change per commit, in dependency order: the plan; `_cli/report.py` and `_cli/options.py`; the export walk and the CSV writer;
the PostgreSQL writer; the JSON Lines writer; `inspect`; `crack`; the parser, dispatch and exit statuses; the golden
file rename; the golden file regeneration; deleting `crodump.py`, `croconvert.py`, `dumpdbfields.py` and the
templates; the realdata tests; the README; and an outcome section in the plan with the roadmap's status and open items
updated. Ben approves before the pull request is opened, before any code-scanning alert is dismissed, before merging,
and before the branch is deleted.

## Open items this phase records

- **Phase 3:** the `inspect` subcommands print warnings through the internal readers' default `warn`, so their
  wording is today's while `export` prints the new escaped diagnostic lines. Phase 3's "diagnostics in place of
  `print`" settles it.
- **Phase 3:** `report.py` counts `replaced_nul` itself, because writing a NUL to a PostgreSQL `TEXT` column is a
  problem of the SQL writer, not of reading. If Phase 3 gives the API a diagnostic kind for output problems, this
  moves there.
- **After 1.0:** an interactive `crack strucrack` that ends without a complete KOD exits 0 (the roadmap's existing
  item).
