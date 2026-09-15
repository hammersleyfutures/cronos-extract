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
uv run pytest -q tests/test_crodump.py::test_strudump_without_the_database_kod_stops_with_a_message
uv run ruff check && uv run ruff format --check && uv run ty check
uv run pip-audit --skip-editable          # CI runs this in the lint job
uv run pytest --update-golden             # rewrite tests/golden/ after a deliberate output change
uv run croconvert --csv -o out test_data/all_field_types
uv run croconvert -t postgres test_data/all_field_types
uv run crodump strudump -v -a test_data/all_field_types
uv run cronos-extract survey test_data    # report each database's format version
uv run python -m cronos_extract.dumpdbfields test_data/all_field_types   # example script, no console entry point
```

- pytest runs with `filterwarnings = error`, so any warning fails a test.
- ty runs with every rule as an error.
- ruff 0.16 also formats Python code blocks inside Markdown files, so `ruff format --check` covers `.md` files.
- After `--update-golden`, `git diff tests/golden` must show only the intended change.

## Architecture

The code is layered, from bytes up to commands (`src/cronos_extract/`):

- **`Datafile`**: one `.dat`/`.tad` pair. The `.tad` is an index of `(offset, length, flags)` entries, where a length of
  `0xFFFFFFFF` means deleted. Record numbers start at 1. `readrec(idx)` reassembles extended records from extension
  blocks, KOD-decodes the data using the record number as the shift (when bit 0 of the `.dat` header's encoding field
  is set), then decompresses zlib chunks. v3 (`01.02`–`01.05`) and v4 (`01.11`, `01.13`, `01.14`) store the flags in
  different bits; v7 (`01.19`) is not supported.
- **`Database`**: opens `CroStru`, `CroIndex`, `CroBank` and `CroSys` in a directory, matching names case-insensitively,
  and closes them via `with Database(...)`. CroStru record 1 holds the *database definition*, a list of key/value pairs.
  A value is either inline, or a reference to another CroStru record when the high bit of its length is clear.
  `BaseNNN` keys are table definitions, and `Base000` is the Files table that stores embedded files.
  `enumerate_tables`, `enumerate_records` and `enumerate_files` are the API that exports use. The Database directory
  maps to the Cronos "Bank", a table to a "Base", and a record id to the "System Number".
- **`Datamodel`**: `TableDefinition`/`FieldDefinition` decode definitions, and `Record`/`Field` turn record bytes into
  presentable content (dates, times, text). Field type 6 is a file reference into the Files table. Record fields that
  fail to decode are left empty and counted in `Database.incomplete_records`.
- **Commands**:
  - `croconvert` exports CSV (`csv_output`) or renders a Jinja2 template from `src/cronos_extract/templates/`. The
    templates call `db.enumerate_*` and helpers passed in from `croconvert.py`, such as `unique_sql_table_name` and
    `sql_value`. Only `html.j2` is autoescaped.
  - `crodump` has the inspection subcommands (`strudump`, `crodump`, `recdump`, `destruct`, `kodump`) plus `strucrack`
    and `dbcrack`.
  - `dumpdbfields` is an example of the Database API.
- **`readers.ByteReader`** is the sequential reader every decoder uses. It raises `EOFError` past the end and decodes
  names as CP-1251, replacing undefined bytes.

### KOD cipher

Records are obfuscated with a byte substitution table (KOD): `plain[i] = (KOD[enc[i]] - i - recno) % 256`
(`koddecoder.KODcoding.decode`). A valid KOD is a permutation of 0–255.

`Datafile` uses a KOD table given with `--kod` only when the file is encrypted with its own table: versions `01.04`,
`01.05` and v4. For other files it quietly substitutes the default `INITIAL_KOD`. `--nokod` passes no KOD, which turns
decoding off for every file. So `--kod` has no effect on `test_data/all_field_types`, whose records are encoded with
`INITIAL_KOD`, but `--nokod` does. To test a wrong or custom KOD, build an encrypted database, e.g.
`write_database(dir, records, kod=random_kod(seed=1))`.

`strucrack` and `dbcrack` derive a KOD statistically. They return `None` when they can't produce a permutation. Every
command's `--strucrack`/`--dbcrack` goes through `crodump.crack_kod(method, dbdir, compact)`.

### Error-handling conventions

- Diagnostics (warnings, errors, crack output) go to **stderr**. croconvert writes HTML/SQL to stdout, so a stray
  `print` corrupts the export.
- Corrupt structures raise `ValueError` naming the record and file. Readers of CroBank records turn that into
  `LookupError`, then warn and skip the record (`Database.readbankrec`). Exports keep going and report counts at the end.
- A database definition that can't be decoded prints the error and then `KOD_HINT`. `strudump` exits 1 with
  `Error: ...` instead of a traceback.

## Tests

- `tests/cronos_builder.py` writes real crafted databases, optionally KOD-encrypted, and is itself tested in
  `tests/test_cronos_builder.py`. Tests build databases with it rather than using mocks.
  `write_raw_datafile` lays out `.dat`/`.tad` bytes directly.
- Command tests run the real command in a subprocess via `tests/cli.py::run_command(module, args, cwd=None, stdin=None)`
  and assert on stdout, stderr and the exit status.
- `tests/test_cli_characterisation.py` compares full command output with `tests/golden/`.
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
- Plans and specs live in `docs/superpowers/` (untracked); the modernisation backlog is Appendix A of
  `docs/superpowers/plans/2026-09-15-pr2-bug-fixes.md`.
