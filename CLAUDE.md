# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

cronos-extract reads CronosPro databases (directories of `Cro*.dat` + `Cro*.tad` file pairs) and exports or inspects
them. It is the successor to alephdata/cronodump; the full upstream history is kept. Treat every database as untrusted
input (often leaked data analysed by investigators): crashes, hangs, unbounded memory, path traversal, HTML/SQL
injection and silent data loss are bugs.

## Commands

```bash
uv sync                                   # dev environment (Python 3.12+)
uv run pre-commit install                 # ruff, ty and pytest before each commit
uv run pytest -q                          # all tests
uv run pytest -q -m realdata              # the real databases listed in local/, deselected by default; a node id needs -m realdata too
uv run pytest -q tests/test_cli_inspect.py::test_strudump_without_the_database_kod_stops_with_a_message
uv run ruff check && uv run ruff format --check && uv run ty check
uv run pip-audit --skip-editable          # CI runs this in the lint job
uv run pytest --update-golden             # rewrite tests/golden/ after a deliberate output change
uv run cronos-extract export --csv -o out test_data/all_field_types
uv run cronos-extract export --postgres test_data/all_field_types
uv run cronos-extract export --jsonl test_data/all_field_types
uv run cronos-extract inspect strudump -v -a test_data/all_field_types
uv run cronos-extract survey test_data    # report each database's format version
```

- pytest runs with `filterwarnings = error`, so any warning fails a test.
- ty runs with every rule as an error.
- ruff 0.16 also formats Python code blocks inside Markdown files, so `ruff format --check` covers `.md` files.
- After `--update-golden`, `git diff tests/golden` must show only the intended change.

## Architecture

The code is layered, from bytes up to commands (`src/cronos_extract/`):

- **Public API** (`cronos_extract/__init__.py`, implemented in `_api/`): `open()` returns a `Bank` of `Table`s whose
  `records()` yield `Record`s of `Field`s with `value`, `text` and `raw`; problems it survives are `Diagnostic`s,
  and a database it cannot read raises a `CronosError`. It drives `Datafile`, `Database.read_db_definition` and
  `TableDefinition` directly, passing each a `report` callback (`_diagnostic.py`'s `Reporter`) that turns every
  problem reading survives into a `Diagnostic` with its `DiagnosticKind`; no reader prints. Only names in `__all__`
  are public. `_format/files.py`'s `open_regular_file` is the one way Cro files are opened.
- **`Datafile`**: one `.dat`/`.tad` pair. The `.tad` is an index of `(offset, length, flags)` entries, where a length of
  `0xFFFFFFFF` means deleted. Record numbers start at 1. Each `.tad` entry is parsed by `_format/tad.py`'s layout for
  its generation: v3 keeps the inline flag in bit 31 of the length, v4 in the top byte of the offset. Every record is
  decoded by `_format/record.py`'s `decode_record`, one pipeline of reassembling extension blocks, KOD-decoding the
  data using the record number as the shift (when bit 0 of the `.dat` header's encoding field is set), then
  CRC-checking and decompressing zlib chunks, at most 256 MiB decompressed. `read_record` returns the decoded parts
  together with the chunks whose CRC did not match. v3 (`01.02`–`01.05`) and v4 (`01.11`, `01.13`, `01.14`) store the
  flags in different bits; v7 (`01.19`) is not supported.
- **`Database`**: opens `CroStru`, `CroIndex`, `CroBank` and `CroSys` in a directory, matching names case-insensitively,
  and closes them via `with Database(...)`. CroStru record 1 holds the *database definition*, a list of key/value pairs.
  A value is either inline, or a reference to another CroStru record when the high bit of its length is clear.
  `BaseNNN` keys are table definitions, and `Base000` is the Files table that stores embedded files. The Database
  directory maps to the Cronos "Bank", a table to a "Base", and a record id to the "System Number".
- **`Datamodel`**: `TableDefinition`/`FieldDefinition` decode definitions, and `Record`/`Field` turn record bytes into
  presentable content (dates, times, text). Field type 6 is a file reference into the Files table. `_api/values.py`'s
  `decode_record` reports a field that fails to decode as `undecodable_field`, and a date or time that fails to parse
  as `invalid_value`; the field's `value` is `None` and its `text` falls back to the raw text.
- **Commands**:
  - `cronos-extract` (`cli.py`) builds the parser and dispatches to four subcommands; its `main()` is the one place
    that turns an exception into an `Error:` line and an exit status (0 finished, 1 cannot read or failed, 2 usage,
    130 interrupted), and it escapes everything written to stderr.
  - `survey` walks directories for `Cro*.dat` files and reports each file's format version, generation and encoding
    flags from `survey.py`, reading only the 19-byte `.dat` header. `--counts` and `--jsonl` choose the output
    format, and `--list` takes a file naming the directories.
  - `export` (`_cli/export.py`) opens the database through the public API and walks its tables once, handing each
    table and record to one writer: `_cli/csv_out.py`, `_cli/sql_out.py` or `_cli/jsonl_out.py`. `_cli/report.py`
    prints each diagnostic and the summary; `_cli/names.py` makes file names and SQL identifiers safe and unique.
  - `inspect` (`_cli/inspect.py`) has `strudump`, `recdump`, `crodump`, `destruct` and `kodump` over the internal
    readers, opening the Cro files itself so that only a file the subcommand reads can stop it.
  - `crack` (`_cli/crack.py`) has `strucrack` and `dbcrack` over `_api/crack.py`'s statistics.
- **`readers.ByteReader`** is the sequential reader every decoder uses. It raises `EOFError` past the end. All CP-1251
  text in the readers, names included, decodes through `readers.decode_cp1251`, which replaces the one byte CP-1251
  leaves undefined (`0x98`) with U+FFFD instead of dropping or raising on it.

### KOD cipher

Records are obfuscated with a byte substitution table (KOD): `plain[i] = (KOD[enc[i]] - i - recno) % 256`
(`koddecoder.KODcoding.decode`). A valid KOD is a permutation of 0–255.

`Datafile` uses a KOD table given with `--kod` only when the file is encrypted with its own table: versions `01.04`,
`01.05` and v4. For other files it quietly substitutes the default `INITIAL_KOD`. `--nokod` passes no KOD, which turns
decoding off for every file. So `export --kod` has no effect on `test_data/all_field_types`, whose records are
encoded with `INITIAL_KOD`, but `--nokod` does. To test a wrong or custom KOD, build an encrypted database, e.g.
`write_database(dir, records, kod=random_kod(seed=1))`.

`crack strucrack` and `crack dbcrack` derive a KOD statistically and print it; `cronos_extract.crack_kod(path, method)`
does the same without printing and returns `None` when it can't produce a permutation. `export --crack` and
`inspect … --crack` call `crack_kod`.

### Error-handling conventions

- A problem a reader survives is a `Diagnostic` (`_diagnostic.py`): a `kind`, `message`, and the `file`, `table`,
  `record` and `field` it concerns, each `None` when it does not apply. Readers take a required `report` callback and
  call it with each `Diagnostic` as it happens; none of them prints. `export` passes `cronos_extract.open`'s
  `on_diagnostic`; `inspect` passes a `_cli/report.py` `Report`'s `diagnostic` method. Either way the diagnostic
  becomes one escaped `warning: kind: location: message` line on **stderr**, through `_cli/report.py`; `export`
  writes SQL and JSON Lines to stdout, so a stray `print` corrupts the export.
- Corrupt structures raise `ValueError` naming the record and file. `Bank._read` (`_api/bank.py`) catches an
  exception reading a CroBank record, reports it as `corrupt_record` the first time only, and skips the record.
  Exports keep going and report counts at the end.
- A database definition that can't be decoded is `DatabaseDefinitionError`: `export` exits 1 with one `Error:` line
  naming `cronos-extract crack strucrack`; `inspect strudump` prints the error and `KOD_HINT`.

## Tests

- `tests/cronos_builder.py` writes real crafted databases, optionally KOD-encrypted, and is itself tested in
  `tests/test_cronos_builder.py`. Tests build databases with it rather than using mocks.
  `write_raw_datafile` lays out `.dat`/`.tad` bytes directly.
- Command tests run the real command in a subprocess via `tests/cli.py::run_command(module, args, cwd=None, stdin=None)`
  and assert on stdout, stderr and the exit status.
- Before a subcommand is wired into `cli.py`, or to read its output in this process,
  `tests/cli.py::run_in_process(add_parser, args)` parses real arguments and runs the handler.
- `tests/test_cli_characterisation.py` compares full command output with `tests/golden/`.
- `tests/golden/api/*.jsonl` pin the public API's field text per record, one file per builder version, KOD case and
  record layout (`tests/test_api_golden.py`).
- `local/` is gitignored and holds machine-local test assets. `local/mash_datasets_with_CroIndex_dat.txt` lists
  real CronosPro database directories (v3 `01.02` and `01.03`, v4 `01.11`, no v7) for
  `cronos-extract survey --list` and for trying the readers on real data. Never commit its contents or quote its
  entries: they name datasets that are not ours to publish. `local/realdata-fingerprints.json` holds a per-database
  record count and a SHA-256 of the API's field text for those real databases, rewritten by
  `uv run pytest -q -m realdata tests/test_realdata.py -k fingerprint --update-golden`.
- `docs/cronos-research.md` documents the file format (`.dat`/`.tad` layout, CroStru, CroBank, table and field
  definitions, compressed records, v4).

## Repository and GitHub

- GitHub: `hammersleyfutures/cronos-extract`, a fork of `alephdata/cronodump`. Always pass
  `-R hammersleyfutures/cronos-extract` to `gh pr` commands, because otherwise `gh` targets the parent repository.
  Never open issues or PRs against `alephdata/cronodump`.
- Merge PRs with a merge commit (`gh pr merge --merge`), never squash or rebase: `.git-blame-ignore-revs` lists exact
  commit hashes of formatting-only commits.
- CI (`.github/workflows/ci.yml`) runs lint, ty and pip-audit, and pytest on Python 3.12, 3.13 and 3.14. CodeQL
  (`codeql.yml`) runs security-and-quality queries. CodeQL alert `py/clear-text-logging-sensitive-data` (strudump
  printing the NS1 password) is intended and was dismissed.
- Plans and specs are committed under `docs/superpowers/`. The modernisation roadmap, its decisions, the public API
  contract and the open items carried forward between phases are in
  `docs/superpowers/specs/2026-09-15-modernisation-roadmap-design.md`; the older backlog is Appendix A of
  `docs/superpowers/plans/2026-09-15-pr2-bug-fixes.md`.
