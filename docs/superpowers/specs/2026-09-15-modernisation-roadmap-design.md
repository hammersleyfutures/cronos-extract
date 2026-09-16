# cronos-extract modernisation roadmap and 1.0 design

**Date:** 2026-09-15
**Status:** approved by Ben (2026-09-15)
**Covers:** the road from today's code (master `a10d51a`, after PR 2, PR 3 and PR 4) to a 1.0 release on PyPI, and the detailed design of Phase 0. Later phases get their own specs.

## Goal

cronos-extract reads CronosPro databases for two audiences that count equally: investigators and journalists who run the command line on databases they have been given, and developers whose pipelines import cronos-extract as a library. 1.0 makes both stable: one `cronos-extract` command, and a documented Python API that the command line is a thin layer over.

## Decisions

Every decision below was made with Ben on 2026-09-15.

1. **Audience:** command line and library API both matter; the CLI is a thin layer over the API, and both are stable at 1.0.
2. **Approach:** design and publish the API first, then restructure the internals behind it (the "API first" approach). Not a rewrite: the existing readers carry years of worked-out edge cases and the fixes from PR 2 and PR 3.
3. **CLI shape:** one `cronos-extract` command with subcommands. `crodump` and `croconvert` are removed outright, with no aliases: their names clash with the `cronodump` package.
4. **API shape:** a façade. `cronos_extract.open(...)` returns a `Bank`; today's `Datafile`, `Database` and `Datamodel` become internal, with one reader per format version behind the façade.
5. **Problem reporting:** structured `Diagnostic` objects collected on the bank, with an optional callback. The library never prints. Fatal problems raise named exceptions.
6. **Field values:** three views per field — `value` (typed), `text` (display string) and `raw` (bytes). Numeric fields stay `str` in 1.0 until real databases show how CronosPro formats numbers.
7. **Format support in 1.0:** CronosPro v7 (`01.19`), tables with ids above 255, and CRC checking of compressed chunks. Link fields (7, 8, 9, 17), dictionary fields (3), external files (29) and multi-valued fields come after 1.0.
8. **Exports in 1.0:** CSV, PostgreSQL and JSON Lines. The HTML export and its template are removed.
9. **Release:** nothing is published to PyPI before 1.0, and the repository stays private until then. If Phase 4 finds no real v7 file, 1.0 labels v7 as experimental; if v7 hits a blocker, the release plan is revisited with Ben.
10. **Specs and plans** are committed to the repository.

## Roadmap

Each phase is a separate spec, plan and pull request, in this order.

### Phase 0 — version survey

A `cronos-extract survey` command that reports the CronosPro version of every database under a directory, reading only file headers. Ben runs it on his own databases; the result tells us whether v7 support can be confirmed against real files. Designed in full below.

### Phase 1 — public API over today's internals

`cronos_extract.open()` and the `Bank`, `Table`, `Record`, `Field`, `FileReference`, `EmbeddedFile`, `Kod`, `Diagnostic` and exception types, implemented over the existing `Database`, `Datafile` and `Datamodel` classes, which become internal. Tests are written against the public API using databases from `tests/cronos_builder.py`.

### Phase 2 — new command line on the API

The `cronos-extract` subcommands (`survey`, `export`, `inspect`, `crack`), global KOD options, exit statuses and `--strict`. Removes the `crodump` and `croconvert` commands, the HTML export and `dumpdbfields`. Golden output tests move to the new commands; the README is rewritten.

### Phase 3 — restructure behind the façade

Type annotations throughout; one record-decoding path in place of the copies in `Datafile.readrec` and `Datafile.dump`; a reader interface per format version; one CP-1251 decoding policy; one KOD-selection function; diagnostics in place of `print`. Fixes: tables with ids above 255, CRC checking, a diagnostic when a supplied KOD is not used, the CSV export holding every file reference in memory, warnings printed once per problem instead of once per table pass, and the Files table header. The Phase 1 and Phase 2 tests guard every step.

### Phase 4 — v7 reader

A `01.19` reader behind the façade, from the research in alephdata/cronodump#24 (record envelope, plaintext CroBank, per-bank KOD, known-plaintext recovery) and whatever the survey finds, with v7 support in `tests/cronos_builder.py` for crafted databases.

### Phase 5 — 1.0 release

Version 1.0, API documentation, PyPI publishing, making the repository public, detaching the fork from alephdata's network, and removing the duplicate CodeQL "Code Quality" analysis. Ben posts the courtesy issue on alephdata/cronodump afterwards.

### After 1.0

KOD recovery that chooses the best whole permutation (an assignment problem, e.g. the Hungarian algorithm) instead of deciding each entry independently; link, dictionary, external-file and multi-valued fields; numeric value types; `crodump destruct` error handling; interactive crack exit statuses.

## Public API contract (Phases 1 and 2 build to this)

```python
import cronos_extract

with cronos_extract.open(path, kod=..., compact=False, on_diagnostic=None) as bank:
    for table in bank.tables:
        for record in table.records():
            record["Entry #4"].value
```

- **`open(path, *, kod=Kod.default(), compact=False, on_diagnostic=None) -> Bank`** — `kod=None` reads without KOD decoding. `Bank` is a context manager that closes its files.
- **`Kod`** — `Kod.default()`, `Kod.from_hex(str)`, `Kod.from_table(Sequence[int])`. A valid table is a permutation of 0–255.
- **`crack_kod(path, method="strucrack" | "dbcrack") -> Kod | None`** — returns `None` when it cannot recover a permutation.
- **`Bank`** — `tables: Sequence[Table]` (the Files table excluded), `read_file(FileReference) -> EmbeddedFile`, `files() -> Iterator[EmbeddedFile]`, `info` (per-file versions and flags, as the survey reports them), `diagnostics: Sequence[Diagnostic]`, `close()`.
- **`Table`** — `id: int`, `name: str`, `fields: Sequence[FieldDefinition]`, `records() -> Iterator[Record]` (lazy).
- **`Record`** — `number: int`, `fields: Sequence[Field]`, `__getitem__(name)`, `diagnostics`.
- **`Field`** — `definition`, `value`, `text: str`, `raw: bytes`. `value` is `str`, `datetime.date`, `datetime.time`, `FileReference` or `None`; a value that does not parse as its type falls back to the text and records a diagnostic.
- **`FileReference`** — `name`, `extension`, `record`. **`EmbeddedFile`** — `name`, `data: bytes`.
- **`Diagnostic`** — frozen: `kind` (enum, e.g. `corrupt_record`, `undecodable_field`, `unresolved_file_reference`, `unused_kod`), `message`, `file`, `table`, `record`, `field`.
- **Exceptions** — `CronosError` base; `NotACronosFile`, `UnsupportedVersion`, `DatabaseDefinitionError`. Anything survivable (one record, field or file reference) is a diagnostic, not an exception.

**Documented promises:** iteration is lazy, and `bank.diagnostics` grows while reading; a `Bank` is not thread-safe; the set of `Field.value` types may grow in later versions.

## Command line (Phase 2 builds to this)

```
cronos-extract [--kod HEX | --nokod | --crack strucrack|dbcrack] [--compact] <subcommand>
```

- `survey [--list FILE] [--counts|--jsonl] [DIR...]`
- `export --csv|--postgres|--jsonl [-o PATH] [--delimiter ,] [--no-files] DB`
- `inspect strudump|recdump|crodump|destruct|kodump [options] DB`
- `crack strucrack|dbcrack [--noninteractive] [--silent] DB`

Data goes to stdout, diagnostics to stderr followed by a summary count. Exit statuses: 0 on success (skipped records included), 1 when the database cannot be read at all (one message, no traceback), 2 for a usage error. `--strict` turns any diagnostic into exit status 1.

## Phase 0 design: `cronos-extract survey`

### What it reads

A `.dat` file starts with a 19-byte header, `struct.unpack("<8sH5sHH", ...)`: magic `CroFile\0`, an unknown uint16, a 5-byte version, uint16 encoding flags (bit 0 KOD-encoded, bit 1 compressed) and a uint16 block size. Versions `01.02`–`01.05` are v3, `01.11`/`01.13`/`01.14` are v4, `01.19` is v7; `01.03`, `01.05` and `01.11` use 64-bit offsets; `01.04`, `01.05` and v4 are encrypted with the database's own KOD table. The survey reads those 19 bytes and nothing else: no `.tad` file, no record, no file content.

### Behaviour

- `cronos-extract survey [--list FILE] [--counts | --jsonl] [DIR...]` walks each directory recursively without following symlinks, and treats every directory containing `Cro*.dat` files as one database. File names are matched case-insensitively.
- **`--list FILE`:** survey the directories named in a text file, one per line, as one group, alone or alongside directories given as arguments. Blank lines and lines starting with `#` are ignored, and a relative path is taken from the current directory. A database found under more than one root is reported once, so `--counts` totals count it once.
- **Default output:** a block per database — its path, then one line per file with the name (`Stru`, `Bank`, `Index`, `Sys` or another), version, generation (`v3`, `v4`, `v7`, or `unknown`), 32- or 64-bit, and whether it is KOD-encoded, compressed and encrypted with its own KOD.
- **`--counts`:** totals per version and generation only, with no paths, for sensitive directory names.
- **`--jsonl`:** one JSON object per database, for scripts and agents.
- **Problems** (a file shorter than 19 bytes, an unknown magic, an unreadable file, an unknown version) are reported as a problem line for that file, and the walk continues. No tracebacks. Exit status 0 when the walk completes, 2 for a missing directory or a usage error.
- **A list entry that is not a directory** is a warning on stderr and the run continues with exit status 0: the file is data, and a database may have moved since it was written. A directory given as an argument, a `--list` file that cannot be read, and giving neither a directory nor a list are usage errors with exit status 2.

### Files

- `src/cronos_extract/cli.py` — the `cronos-extract` entry point: an argparse parser whose only subcommand is `survey` for now; Phase 2 adds the rest here.
- `src/cronos_extract/survey.py` — finding databases, reading a `--list` file, surveying several roots as one group without reporting a database twice, and the three output formats.
- `src/cronos_extract/_format/header.py` — a frozen, annotated `DatHeader` and `read_dat_header(file) -> DatHeader`, raising `ValueError` for a short file or an unknown magic. `Datafile.readdathdr` is changed to use it, so the header is parsed in one place. This creates the internal `_format` package that Phase 3 fills.
- `pyproject.toml` — adds the console script `cronos-extract = "cronos_extract.cli:main"`. The `crodump` and `croconvert` scripts stay until Phase 2.
- New modules are fully annotated and ty-clean.

### Tests

Real files only, no mocks: v3 databases from `tests/cronos_builder.py`; v4 and v7 headers written as raw bytes; a nested tree and mixed-case names; problem files (short, bad magic, unknown version); `--counts` output containing no paths; the `--jsonl` structure; and `Datafile` still reading `test_data` unchanged, so the existing golden files do not move.

### Exit criterion

Ben runs the survey on his own databases and reports which versions appear. That decides whether Phase 4 can confirm v7 against real files or must label it experimental.
