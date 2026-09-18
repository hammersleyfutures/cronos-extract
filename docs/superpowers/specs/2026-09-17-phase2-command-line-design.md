# Phase 2 design: the cronos-extract command line

**Date:** 2026-09-17
**Status:** design approved by Ben (2026-09-17); sections 2 to 6 written after he accepted the remaining design unseen,
to be reviewed in the pull request
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
cronos-extract inspect strudump|recdump|crodump|destruct|kodump [subcommand options]
                       [--kod HEX|--nokod|--crack strucrack|dbcrack] [--compact] DB
cronos-extract crack   strucrack|dbcrack [--noninteractive] [--silent] [--sys] [--fix F] [--text T]
                       [--width N] [--color] DB
```

`--csv`, `--postgres` and `--jsonl` are one required mutually exclusive group; the KOD options are another, optional
one. `survey` is unchanged from Phase 0.

## Decisions

Every decision below was made with Ben on 2026-09-17, from the questions listed in his brief. D5, D7 and D13 to D16
were written from his acceptance of the rest of the design.

### D1. The KOD options belong to `export` and `inspect`, not to the top-level parser

The roadmap's synopsis put `--kod HEX | --nokod | --crack METHOD` and `--compact` in front of the subcommand. They are
instead defined once (a shared argparse parent parser) and attached to `export` and to each `inspect` subcommand, so
they are written after the subcommand name: `cronos-extract export --csv --kod HEX DB`. `inspect destruct` and
`inspect kodump` read hex on stdin or one named file rather than a database, so they take only `--kod` and `--nokod`.

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
- An existing target is a usage error (exit 2) reported before the database is read. Nothing is ever overwritten.
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
- `Files-<abbreviation>/` holds every record of the Files table, named by its system number.
- `Files-Referenced/` holds each referenced file under its own name, created only when a reference was resolved.
- Names are made safe and unique exactly as `croconvert` does it today (`safepathname`, `unique_file_name`,
  `unique_sql_table_name`, `MAX_FILE_NAME_BYTES`, `MAX_EXTENSION_BYTES`, `POSTGRES_IDENTIFIER_BYTES` move unchanged
  into `_cli/names.py`).
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
- Every name and message is escaped before printing: control characters (which could carry terminal escape
  sequences from a hostile database), surrogate-escaped bytes and other unprintable characters become `\xNN`,
  `\uNNNN` or `\UNNNNNNNN`. So one diagnostic is always one line, and nothing from a database reaches a terminal raw.
  The same escaping is applied to the text of a fatal error, and to the messages the internal readers print through
  `inspect` (their wording does not change). This closes the carried-forward escaping item.
- The summary line lists the counts by kind from `bank.diagnostic_counts`, in kind order, and is printed once at the
  end, including when nothing went wrong (`no diagnostics`).
- A command-level problem that is not an API diagnostic is printed and counted in the same shape, with its own kind:
  `replaced_nul` for D9's NUL replacement in SQL output.
- There is no `--quiet`: `2>/dev/null` already silences stderr, and the summary is its last line.
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

- A database that cannot be read at all exits 1 with one `Error: …` line and no traceback, as `strudump` does today.
- Text naming a command says `cronos-extract crack strucrack` and `cronos-extract --kod`; `KOD_HINT` moves with it.
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
steps, as Phase 1 arranged.

Changes:

- Failure messages ("Ambiguous result when cracking …", "no CroStru.dat file found in …") and the
  "Use the following database key …" line go to stderr, so stdout on a successful run holds the dump and the KOD hex
  only, and `KOD=$(cronos-extract crack dbcrack --silent DB)` needs no filtering.
- The hints name `cronos-extract crack strucrack -f …` and `cronos-extract export --kod …`.
- "Ambigous" is spelled correctly.
- Exit statuses: 0 when a KOD is produced; 1 when `--noninteractive` cracking fails or the database cannot be opened;
  2 for an unparsable `--fix` or `--text` or one that does not fit the database (today a `CrackInputError` exit 1).
  An interactive `strucrack` that ends with entries unresolved keeps exit 0; the roadmap defers interactive crack
  statuses to after 1.0.
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
bank once and knows nothing about formats. Every subcommand handler has Phase 0's signature `run_*(args, parser) ->
int` and none calls `sys.exit`: `main` catches `CronosError`, `OSError`, `BrokenPipeError` and `KeyboardInterrupt` and
turns them into a status. This is the dispatch seam the roadmap's carried item asks for. `collect_roots` is given the
`survey` subparser instead of the top-level parser, so its usage line names `cronos-extract survey` — the second
carried item. All new modules are fully annotated and ty-clean.

**Deleted:** `crodump.py`, `croconvert.py`, `dumpdbfields.py`, `templates/` (both templates), the `crodump` and
`croconvert` console scripts, the `jinja2` dependency, and `tests/test_dumpdbfields.py`. `KOD_HINT` and the
`Database.dump*`, `recdump`, `strudump` methods stay, because `inspect` uses them.

### D15. Exit statuses

| Status | When |
|---|---|
| 0 | the command finished; skipped records and diagnostics do not change this |
| 1 | the database cannot be read at all (`CronosError`, or an `OSError` on the database directory or an output file): one `Error: …` line, no traceback. Also a failed `--crack`, a failed `crack --noninteractive`, a write error such as a full disk, and `--strict` with at least one diagnostic |
| 2 | a usage error: argparse's own, an `-o` target that exists, `--no-files` without `--csv`, a `--kod` that is not 512 hex digits or not a permutation of 0–255, a `--fix`/`--text` that cannot be parsed or does not fit |

`BrokenPipeError` (`| head`) exits 1 without a message and without Python's "Exception ignored" report;
`KeyboardInterrupt` exits 130 with no traceback. Output written before a failure is left in place, and the message
says where it is.

### D16. Golden output tests move to the new commands, with every difference recorded

`tests/test_cli_characterisation.py` runs `cronos-extract` instead of `crodump` and `croconvert`. The golden files are
renamed in one commit (`git mv`) and regenerated in the next, so the diff of the second shows only real changes.

| Golden file | Difference |
|---|---|
| `crodump-*` → `inspect-*` | stdout unchanged; hint text names `cronos-extract` |
| `crodump-sysdump.*` | deleted with the subcommand (D11) |
| `crodump-strucrack` → `crack-strucrack` | failure and key messages move to stderr; "Ambiguous" spelled correctly; hints name `cronos-extract` |
| `crodump-dbcrack` → `crack-dbcrack` | its "Ambiguous result" line moves to stderr |
| `croconvert-html.*` | deleted with the HTML export |
| `croconvert-postgres` → `export-postgres` | `SET standard_conforming_strings = on;` first; no stray blank lines or trailing spaces; stderr in the new diagnostic format with a summary |
| `croconvert-postgres-nokod` → `export-postgres-nokod` | exit status 0 → 1; one `Error: …` line naming `cronos-extract crack` in place of today's two lines |
| `croconvert-csv` → `export-csv` | the directory tree and every CSV byte unchanged; stderr in the new diagnostic format with a summary |
| `export-jsonl` | new |

## Hostile input

| Input | Result |
|---|---|
| a `Cro*` file that is a FIFO, socket, device, directory or dangling symlink | `open()` raises `NotACronosFile`: exit 1 with one line (Index and Sys give an `unreadable_file` diagnostic and the export continues) |
| a truncated or corrupt `.dat`/`.tad`, a wrong or absent KOD, a table id above 255 | diagnostics on stderr, the export finishes with exit 0 (1 with `--strict`) |
| a table, field or file name that is not valid UTF-8 or CP-1251, or holds control characters or terminal escapes | escaped on stderr (D10); made safe for file names by `safepathname` and shortened to 255 bytes; quoted for SQL with `"` replaced by `_`; written as JSON string escapes |
| a name that would escape the output directory (`..`, `/`, `\`, an empty name, only dots) | `safepathname` replaces the separators and `unique_file_name` replaces a stem that is empty or only dots with its number, so every path stays directly under the output directory. Tested with a database whose table and file names are `../../etc/passwd` and similar |
| `-o` that exists, is a dangling symlink, or is inside a directory that is not writable | exit 2 for an existing target; exit 1 with the `OSError`'s message for one that cannot be created |
| a database directory that cannot be listed, or is a file | exit 1 with the `OSError` message (`NotADirectoryError` included) |
| stdout closed early (`| head`), or a full disk | exit 1, no traceback (D15) |
| hex input to `inspect destruct` that is not hex, or a binary file to `inspect kodump` | today's behaviour, checked to give a message rather than a traceback |

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
- `tests/test_cli_inspect.py`: the moved subcommands, `--debug`, the exit-1 paths, and that `sysdump` is gone.
- `tests/test_cli_crack.py`: the existing `tests/test_crack.py` cases moved to `crack`, plus messages on stderr, the
  exit statuses of D12, and an interactive crack over a database with an unreadable record.
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
