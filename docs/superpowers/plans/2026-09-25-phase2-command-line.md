# Phase 2: the cronos-extract command line Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `crodump` and `croconvert` with the `cronos-extract export`, `inspect` and `crack` subcommands, built
on the public API, with CSV, PostgreSQL and JSON Lines exports, escaped diagnostics on stderr, and one place that
decides the exit status.

**Architecture:** A private package `src/cronos_extract/_cli/` holds one module per subcommand and per shared part:
`report.py` (escaping, the diagnostic line, the summary, `Failure`), `options.py` (the KOD and `--compact` options),
`export.py` (one walk over a bank's tables) with three writers (`csv_out.py`, `sql_out.py`, `jsonl_out.py`) and the
name helpers (`names.py`), `inspect.py` over the internal readers, and `crack.py` over `_api/crack.py`'s statistics.
Each subcommand module owns `add_parser(subcommands)` and its `run_*(args, parser) -> int` handlers. `cli.py`
assembles the parsers and its `main()` is the only code that turns an exception into an `Error:` line and a status.

**Tech Stack:** Python 3.12+, argparse, csv, json; uv; ruff (line length 120); ty (every rule an error); pytest
(`filterwarnings = error`); real crafted databases from `tests/cronos_builder.py`.

**Spec:** `docs/superpowers/specs/2026-09-17-phase2-command-line-design.md` (decisions D1–D17, Hostile input, Testing,
Documentation, Delivery). It builds on `docs/superpowers/specs/2026-09-15-modernisation-roadmap-design.md` and
`docs/superpowers/specs/2026-09-16-phase1-public-api-design.md`. Read the Phase 2 spec before starting any task.

## Global Constraints

- Address the user as "Ben". Ben's global rules in `~/.claude/CLAUDE.md` override skills. The repository's rules are
  in `CLAUDE.md`.
- Work in the repository root on branch `phase2-implementation`. Never push to `master`. GitHub is
  `hammersleyfutures/cronos-extract`; always pass `-R hammersleyfutures/cronos-extract` to `gh pr` commands. Never
  open anything against `alephdata/cronodump`. Ben approves before the pull request is opened, before any
  code-scanning alert is dismissed, before merging, and before the branch is deleted.
- Test-first for every change: write the test, run it, confirm it fails for the stated reason, write the code, run it
  green. Real crafted databases from `tests/cronos_builder.py` and real files only. Never mock.
- One commit per task, in the order below. Subject in imperative mood, at most 72 characters; the body says what and
  why. Every commit message ends with exactly `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` — use this
  line verbatim.
- Every new code file starts with two comment lines beginning `# ABOUTME: `. Neither line may contain `coding:` or
  `coding=`: Python reads that as a source encoding declaration.
- New modules are fully type-annotated and ty-clean. The internal readers (`Database`, `Datafile`, `Datamodel`,
  `kodump`, `hexdump`) are unannotated, so their values are `Unknown` to ty; narrow at the boundary with `int(...)`,
  `str(...)` or `typing.cast(...)`, as `_api/bank.py` does.
- Names and comments describe what code is, never its history. Never delete a comment unless it is false.
- Run `uv run ruff format` on changed files before checking. Before every commit, all clean, each checked by exit
  code: `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check`, `uv run ty check`. The pre-commit hook
  runs them too. pytest turns every warning into an error, so a file left open in an in-process test fails it.
- Bash tool: `set -e` does not stop a multi-line command. Guard commits with explicit checks, e.g.
  `fail() { echo "STOPPED: $*"; exit 1; }` and `uv run pytest -q > /tmp/t3-pytest.txt 2>&1 || fail pytest`. Never
  pipe a checked command through `tail`.
- Never run `git checkout -- <file>` or `git restore` on a file holding uncommitted work.
- `tests/golden/` does not change until Task 9 (renames only) and Task 10 (regeneration). `git diff master --
  tests/golden` must be empty after Tasks 2–8.
- `crodump` and `croconvert` keep their behaviour until Task 11 deletes them; their tests keep passing until then.
- stdout of `inspect` stays byte for byte what `crodump` prints today (D11).
- Diagnostic messages never embed record data or field values.
- `local/mash_datasets_with_CroIndex_dat.txt` names real datasets. Never commit it, never quote its entries or any
  path from it in code, commits, PRs, test ids or reports.
- Follow the code when this plan and the code disagree about existing behaviour; report the divergence rather than
  loosening an assertion.
- Plain, factual language in commits and PRs. Avoid: critical, crucial, essential, significant, comprehensive,
  robust, elegant.
- Scratch files go in `/tmp` with names prefixed by the task number.

## How the tasks are tested before the command exists

The spec's delivery order puts the modules (Tasks 2–7) before the parser and dispatch (Task 8), so
`cronos-extract export …` cannot run as a subprocess until Task 8. Tasks 2–7 therefore test in this process:
`tests/cli.py` gains `run_in_process(add_parser, args)`, which builds a parser holding only the subcommand that
`add_parser` registers, parses real argv and calls the handler, letting exceptions reach the test as they would reach
`main`. Tests read stdout and stderr with `capsys`. Task 8 adds the subprocess tests of exit statuses, and Task 11
moves the old subprocess tests.

`tests/test_croconvert.py`, `tests/test_crodump.py` and `tests/test_crack.py` run the old commands and import their
modules, so they move in Task 11, the commit that deletes those modules. Three more tests use the old commands and
are repointed in Task 11 as well: `tests/test_api_crack.py:43` (compares with `crodump.crack_kod`),
`tests/test_datafile.py:132` (runs `crodump crodump`) and `tests/test_database.py:62` (runs `croconvert --csv`).

## Choices this plan makes where the spec is silent or leaves a gap

Ben, these are the places where I had to decide something the spec does not settle. Each is small and reversible;
please look at them when reviewing the plan.

1. **The diagnostic line leaves out the file when it names a table.** D10 says "whichever of `file`, `table`,
   `record` and `field` are set", but its own example prints `table "Люди", record 13, field "Дата"` for an
   `invalid_value` whose `file` is `CroBank.dat`. The plan follows the example: with a table, the location is
   `table "T", record N, field "F"`; without one, it is `FILE record N, field "F"` (Task 2).
2. **`report.py` counts problems itself.** D10 says the summary comes from `bank.diagnostic_counts`, but when
   `open()` raises `DatabaseDefinitionError` there is no bank, and D10 still wants the counts so far before the
   `Error:` line. `Report` counts every problem it prints, which gives the same numbers (Task 2).
3. **The writer interface has two more methods than D14 names:** `diagnostic(problem)`, which only the JSON Lines
   writer uses (D4 puts diagnostics in its stream), and `close()`, which releases files on a failure (Task 3).
4. **`Files-<abbreviation>` is numbered with the Files table's id,** which `Bank` keeps in the private
   `_files_table_id`; `_cli` reads it rather than widening the public API. `Files-Referenced` is claimed first with
   the number -1, which no table id can be, and the `Files-<abbreviation>` name is claimed next, before any table, so
   neither claim can fail (Task 3).
5. **`Files-Referenced/` is created at the first record of a table with a type 6 field, even an empty one.** This is
   today's rule (`croconvert.py:225,234`); the golden database has no records, which is why its tree lacks the
   directory. `--no-files` leaves out both file directories, as today (Task 3).
6. **A writer reports `duplicate_table` too,** when two tables with the same id get the same safe name — names that
   differ only in case, or in characters that `safepathname` or the SQL quoting replace. Such tables hold the same
   records, because records are chosen by id; today they are skipped silently (Tasks 3 and 4).
7. **`crack --silent` prints only the KOD hex on success.** D12's `KOD=$(cronos-extract crack dbcrack --silent DB)`
   needs the hex on stdout, which today's `--silent` suppresses. A file that cannot be opened is still an `Error:`
   line on stderr with `--silent` (Task 7).
8. **`crack` reports a missing file with the API's message** (`DIR has no CroStru.dat and CroStru.tad`) and exit 1,
   in place of "no CroStru.dat file found in …" (Task 7).
9. **The unresolved-crack block goes to stderr without colour.** "Ambiguous result when cracking…", the missing
   mappings, the KOD estimate and the `-f` hint move to stderr (D12); the stderr escaping (D10) would turn colour codes
   into `\x1b[…` text, so they are printed plain. "Duplicates found" stays on stdout with the dump it annotates
   (Task 7).
10. **An unresolved file reference is reported as the API reports it.** `unresolved_file_reference` names the
    referenced CroBank record and the reason, but not the file name or the record that holds the reference, which
    `croconvert`'s warning named. Task 14 records this as a Phase 3 open item.
11. **`KOD_HINT` stays in `Database.py`,** which `Database.enumerate_tables` still uses; its text changes to name
    `cronos-extract crack strucrack` in Task 10, the commit whose golden diff shows it.
12. **`-n` stays the short form of `--nokod`** on `export` and `inspect`, as on `crodump` and `croconvert`.
13. **An interrupted export that has created its output ends with `Error: interrupted; the output written so far is
    in PATH` and exit 130,** so D15's "the message says where it is" holds for Ctrl-C too (Task 3).
14. **`inspect crodump` reads every file present,** so a damaged CroIndex or CroSys is exit 1 for it.
    `inspect recdump` of a file that is absent keeps today's `.dat not found` and exit 0 (Task 6).
15. **Code moves instead of being copied while the old commands still exist.** `croconvert.py` imports the name
    helpers from `_cli/names.py` (Task 3); `crodump.py` imports `parse_fix`, `parse_text`, `positive_int`,
    `color_code` and `CrackInputError` from `_cli/crack.py` (Task 7) and the CroSys `destruct` helpers from
    `_cli/inspect.py` (Task 6). `crodump.py`'s own `derive_kod_*` stay until Task 11, because their messages are what
    `crodump`'s golden files hold.

## Review Focus

Inputs and conditions the spec implies but does not list as tests, most likely to bite first. Each has its test in
the task named.

1. **A `--delimiter` that `csv` rejects** (`"`, a line break, two characters, empty) → exit 2 with the reason, not a
   `TypeError` or `ValueError` traceback after the output directory is created. Task 3, `test_a_delimiter_csv_rejects_is_a_usage_error`.
2. **CSV cells holding line breaks, quotes, the delimiter or formula-like text** (`=1+1`, `-5`, `@x`) → a
   `csv.reader` reads back exactly the API's text. Task 3, `test_csv_cells_hold_exactly_what_the_api_decoded`.
3. **`-o` inside a directory that does not exist** → exit 1 with the `OSError` message, not exit 2 and not a
   traceback. Task 8, `test_an_output_in_a_missing_directory_exits_1`.
4. **Ctrl-C during an export** → exit 130, no traceback, and the last stderr line says where the partial output is.
   Task 8, `test_an_interrupted_export_says_where_its_output_is`.
5. **A database path holding bytes that are not UTF-8** → the `Error:` line shows them as `\xNN` and the command
   exits 1 without a traceback. Task 8, `test_a_path_that_is_not_utf8_is_escaped_in_the_error`.

## File Structure

Created:

- `src/cronos_extract/_cli/__init__.py` — package marker.
- `src/cronos_extract/_cli/report.py` — `escape`, `EscapingStream`, `Problem`, `format_problem`, `Report`,
  `Failure`, `error_message`, `print_error`, the command-level kinds.
- `src/cronos_extract/_cli/options.py` — `Subcommands`, `kod_argument`, `kod_options`, `selected_kod`.
- `src/cronos_extract/_cli/names.py` — `safepathname`, `truncate_utf8`, `unique_name`, `unique_file_name` and the
  byte limits, moved from `croconvert.py`.
- `src/cronos_extract/_cli/export.py` — `add_parser`, `run_export`, `Writer`, `Problems`, `walk`, the `-o` rules.
- `src/cronos_extract/_cli/csv_out.py` — `CsvWriter`.
- `src/cronos_extract/_cli/sql_out.py` — `SqlWriter`, `unique_sql_table_name`, `unique_sql_column_names`,
  `sql_value`.
- `src/cronos_extract/_cli/jsonl_out.py` — `JsonlWriter`, `json_value`.
- `src/cronos_extract/_cli/inspect.py` — `add_parser`, the five `run_*` handlers, `open_database`, the CroSys
  `destruct` helpers.
- `src/cronos_extract/_cli/crack.py` — `add_parser`, `run_strucrack`, `run_dbcrack`, `raw_datafile`,
  `derive_kod_from_stru`, `derive_kod_from_bank_and_index`, `parse_fix`, `parse_text`, `positive_int`, `color_code`,
  `CrackInputError`.
- Tests: `tests/test_cli_report.py`, `tests/test_cli_options.py`, `tests/test_cli_names.py`,
  `tests/test_cli_export.py`, `tests/test_cli_inspect.py`, `tests/test_cli_crack.py`, `tests/test_cli.py`.

Modified:

- `src/cronos_extract/cli.py` — the parser for all four subcommands, dispatch, exit statuses, the stderr wrapper.
- `src/cronos_extract/Database.py` — `KOD_HINT` names `cronos-extract`; `strudump` deleted.
- `src/cronos_extract/_api/crack.py`, `src/cronos_extract/kodump.py` — comments name the new commands.
- `tests/cli.py` — `run_in_process`.
- `tests/cronos_builder.py` — `record_with_file_field`, `renamed_table_definition`, `files_table_definition`,
  `database_with_files_abbreviation`, `duplicate_table_name_database`.
- `tests/test_cli_characterisation.py`, `tests/golden/` — the new commands and their output.
- `tests/test_realdata.py` — the command over the real databases.
- `tests/test_api_crack.py`, `tests/test_datafile.py`, `tests/test_database.py` — repointed at the new commands.
- `pyproject.toml`, `uv.lock` — no `crodump`/`croconvert` scripts, no `jinja2`.
- `README.md`, `CLAUDE.md`, `docs/superpowers/specs/2026-09-15-modernisation-roadmap-design.md`, this plan.

Deleted (Task 11): `src/cronos_extract/crodump.py`, `croconvert.py`, `dumpdbfields.py`, `templates/`,
`tests/test_croconvert.py`, `tests/test_crodump.py`, `tests/test_crack.py` (their cases moved),
`tests/test_dumpdbfields.py`.

---

### Task 1: Commit this plan

**Files:**
- Create: `docs/superpowers/plans/2026-09-25-phase2-command-line.md` (this file)

- [ ] **Step 1: Check the branch and the plan's formatting**

Run: `git branch --show-current` — Expected: `phase2-implementation`.
Run: `uv run ruff format --check docs/superpowers/plans/2026-09-25-phase2-command-line.md` — Expected: exit 0 (run
`uv run ruff format` on it first if not).

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/plans/2026-09-25-phase2-command-line.md
git commit -m "Plan Phase 2: the cronos-extract command line" -m "The task list, interfaces and tests for implementing the Phase 2 design, in its delivery order.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `_cli/report.py` and `_cli/options.py`

**Files:**
- Create: `src/cronos_extract/_cli/__init__.py`, `src/cronos_extract/_cli/report.py`,
  `src/cronos_extract/_cli/options.py`
- Modify: `tests/cli.py`
- Test: `tests/test_cli_report.py`, `tests/test_cli_options.py`

**Interfaces:**
- Consumes: `Diagnostic`, `DiagnosticKind` (`_api/diagnostics.py`); `DEFINITION_HINT` (`_api/bank.py`); `KOD_HINT`
  (`Database.py`); `Kod` (`_api/kod.py`); `crack_kod(path, method) -> Kod | None` (`_api/crack.py`).
- Produces (every later task relies on these names):
  - `report.DUPLICATE_TABLE = "duplicate_table"`, `report.REPLACED_NUL = "replaced_nul"`,
    `report.COMMAND_KINDS`, `report.KIND_ORDER`.
  - `report.escape(text: str, keep: str = "") -> str`
  - `report.EscapingStream(stream: TextIO)` — an `io.TextIOBase` that escapes all but `"\n"`.
  - `report.Problem(kind: str, message: str, file: str | None = None, table: str | None = None, record: int | None =
    None, field: str | None = None)`, frozen, with `Problem.from_diagnostic(diagnostic) -> Problem`.
  - `report.format_problem(problem) -> str` — `warning: KIND: LOCATION: MESSAGE`, escaped.
  - `report.Report()` with `.problem(problem)`, `.diagnostic(diagnostic)`, `.total -> int`, `.summary() -> str`,
    `.print_summary()`; it prints on `sys.stderr` as it is at call time.
  - `report.Failure(message: str, status: int = 1)` with `.status`.
  - `report.error_message(error: BaseException) -> str`, `report.print_error(message: str) -> None`.
  - `options.Subcommands` — the type of `ArgumentParser.add_subparsers()`'s result.
  - `options.kod_argument(text: str) -> Kod`, `options.kod_options(*, crack: bool = True, compact: bool = True) ->
    argparse.ArgumentParser` (a parent parser), `options.selected_kod(args) -> Kod | None`.
  - `tests/cli.py`: `run_in_process(add_parser: Callable[[Subcommands], None], args: list[str]) -> int`.

- [ ] **Step 1: Write the failing report tests**

Create `tests/test_cli_report.py`:

```python
# ABOUTME: Tests for how the command reports problems: escaping, the diagnostic line, the summary and error text.
# ABOUTME: They call _cli/report.py in this process and read what it prints on stderr.
import io

import pytest

from cronos_extract import DatabaseDefinitionError, Diagnostic, DiagnosticKind
from cronos_extract._api.bank import DEFINITION_HINT
from cronos_extract._cli.report import (
    DUPLICATE_TABLE,
    REPLACED_NUL,
    EscapingStream,
    Failure,
    Problem,
    Report,
    error_message,
    escape,
    format_problem,
)
from cronos_extract.Database import KOD_HINT


@pytest.mark.parametrize(
    ("text", "escaped"),
    [
        ("Люди", "Люди"),
        ("a b", "a b"),
        ("\x1b[31mred", "\\x1b[31mred"),
        ("tab\there", "tab\\x09here"),
        ("line\nbreak", "line\\x0abreak"),
        ("\x7f", "\\x7f"),
        ("\u0085", "\\x85"),
        ("‮evil", "\\u202eevil"),
        ("\udcff", "\\xff"),
        ("\U000e0001", "\\U000e0001"),
    ],
    ids=[
        "cyrillic",
        "space",
        "terminal-escape",
        "tab",
        "line-break",
        "delete",
        "c1-control",
        "rtl-override",
        "surrogate-escaped-byte",
        "astral-format-character",
    ],
)
def test_escape_writes_unprintable_characters_as_escapes(text: str, escaped: str) -> None:
    assert escape(text) == escaped


def test_escape_keeps_the_characters_asked_for() -> None:
    assert escape("a\nb\x1b", keep="\n") == "a\nb\\x1b"


def test_a_record_problem_names_its_table_record_and_field() -> None:
    diagnostic = Diagnostic(
        DiagnosticKind.INVALID_VALUE,
        "the value is not a date; it is kept as text",
        file="CroBank.dat",
        table="Люди",
        record=13,
        field="Дата",
    )

    assert format_problem(Problem.from_diagnostic(diagnostic)) == (
        'warning: invalid_value: table "Люди", record 13, field "Дата": the value is not a date; it is kept as text'
    )


def test_a_problem_without_a_table_names_its_file_and_record() -> None:
    diagnostic = Diagnostic(
        DiagnosticKind.CORRUPT_RECORD,
        "CroBank record 88 is corrupt and is skipped: EOFError",
        file="CroBank.dat",
        record=88,
    )

    assert format_problem(Problem.from_diagnostic(diagnostic)) == (
        "warning: corrupt_record: CroBank.dat record 88: CroBank record 88 is corrupt and is skipped: EOFError"
    )


def test_a_problem_with_only_a_file_names_the_file() -> None:
    problem = Problem(
        "unexpected_structure", "Base001: FieldDefinition Section 2 not marked with a 2", file="CroStru.dat"
    )

    assert format_problem(problem) == (
        "warning: unexpected_structure: CroStru.dat: Base001: FieldDefinition Section 2 not marked with a 2"
    )


def test_a_problem_with_no_location_has_only_its_kind_and_message() -> None:
    assert format_problem(Problem("unused_kod", "the KOD given is not used")) == (
        "warning: unused_kod: the KOD given is not used"
    )


def test_a_hostile_table_name_stays_on_one_line_and_escaped() -> None:
    problem = Problem("invalid_value", "m", table="x\n\x1b]0;owned\x07", record=1)

    assert format_problem(problem) == 'warning: invalid_value: table "x\\x0a\\x1b]0;owned\\x07", record 1: m'


def test_report_prints_each_problem_as_it_is_reported(capsys: pytest.CaptureFixture[str]) -> None:
    Report().problem(Problem(REPLACED_NUL, "m", table="t", record=1, field="f"))

    assert capsys.readouterr().err == 'warning: replaced_nul: table "t", record 1, field "f": m\n'


def test_report_takes_api_diagnostics(capsys: pytest.CaptureFixture[str]) -> None:
    report = Report()

    report.diagnostic(Diagnostic(DiagnosticKind.UNUSED_KOD, "not used"))

    assert capsys.readouterr().err == "warning: unused_kod: not used\n"
    assert report.total == 1


def test_the_summary_says_when_there_were_no_diagnostics(capsys: pytest.CaptureFixture[str]) -> None:
    Report().print_summary()

    assert capsys.readouterr().err == "no diagnostics\n"


def test_the_summary_counts_kinds_in_declaration_order_with_command_kinds_last(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = Report()
    for kind in (REPLACED_NUL, "invalid_value", DUPLICATE_TABLE, "corrupt_record", "invalid_value"):
        report.problem(Problem(kind, "m"))
    capsys.readouterr()

    report.print_summary()

    assert capsys.readouterr().err == (
        "\n5 diagnostics: 1 corrupt_record, 2 invalid_value, 1 duplicate_table, 1 replaced_nul\n"
    )


def test_one_diagnostic_is_counted_in_the_singular() -> None:
    report = Report()
    report.diagnostic(Diagnostic(DiagnosticKind.UNUSED_KOD, "not used"))

    assert report.summary() == "1 diagnostic: 1 unused_kod"


def test_the_escaping_stream_escapes_everything_but_line_breaks() -> None:
    target = io.StringIO()
    stream = EscapingStream(target)

    written = stream.write("a\x1bb\nc\udcff")
    print("x\x07", file=stream)

    assert written == 6
    assert target.getvalue() == "a\\x1bb\nc\\xffx\\x07\n"


def test_an_error_message_names_the_command_line_hint_in_place_of_the_api_one() -> None:
    error = DatabaseDefinitionError(f"the definition cannot be decoded: ValueError: bad. {DEFINITION_HINT}")

    assert error_message(error) == f"the definition cannot be decoded: ValueError: bad. {KOD_HINT}"
    assert error_message(OSError(2, "No such file or directory")) == "[Errno 2] No such file or directory"


def test_a_failure_exits_1_unless_given_a_status() -> None:
    assert Failure("x").status == 1
    assert Failure("x", status=2).status == 2
```

- [ ] **Step 2: Run the report tests to see them fail**

Run: `uv run pytest -q tests/test_cli_report.py`
Expected: collection error, `ModuleNotFoundError: No module named 'cronos_extract._cli'`.

- [ ] **Step 3: Write `_cli/__init__.py` and `_cli/report.py`**

Create `src/cronos_extract/_cli/__init__.py`:

```python
# ABOUTME: The cronos-extract subcommands and the parts they share, built on the public cronos_extract API.
# ABOUTME: cli.py assembles their parsers; each module here owns one subcommand or one shared part.
```

Create `src/cronos_extract/_cli/report.py`:

```python
# ABOUTME: How the command reports problems on stderr: escaped text, one line per problem, and a summary of counts.
# ABOUTME: Also Failure, which a subcommand raises to end with one Error line and an exit status.
import io
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Self, TextIO, override

from .._api.bank import DEFINITION_HINT
from .._api.diagnostics import Diagnostic, DiagnosticKind
from ..Database import KOD_HINT

# Kinds the command reports itself, for problems of writing the output rather than of reading the database.
DUPLICATE_TABLE = "duplicate_table"
REPLACED_NUL = "replaced_nul"
COMMAND_KINDS = (DUPLICATE_TABLE, REPLACED_NUL)
# The order of the summary: the API's kinds as DiagnosticKind declares them, then the command's own.
KIND_ORDER = (*(kind.value for kind in DiagnosticKind), *COMMAND_KINDS)
# The surrogates that the surrogateescape error handler uses for the bytes 0x80 to 0xff of an undecodable name.
ESCAPED_BYTES = range(0xDC80, 0xDD00)


def escape(text: str, keep: str = "") -> str:
    """
    `text` with every character that is not printable written as an escape, except those in `keep`.

    A byte that a file name held surrogate-escaped is written \\xNN; any other character as \\xNN, \\uNNNN or
    \\UNNNNNNNN. Control characters, line breaks and format characters such as a right-to-left override are all
    unprintable, so an escaped text is one line and cannot carry a terminal control sequence.
    """
    escaped = []
    for char in text:
        code = ord(char)
        if char.isprintable() or char in keep:
            escaped.append(char)
        elif code in ESCAPED_BYTES:
            escaped.append(f"\\x{code - 0xDC00:02x}")
        elif code <= 0xFF:
            escaped.append(f"\\x{code:02x}")
        elif code <= 0xFFFF:
            escaped.append(f"\\u{code:04x}")
        else:
            escaped.append(f"\\U{code:08x}")
    return "".join(escaped)


class EscapingStream(io.TextIOBase):
    """
    A text stream that writes to `stream` everything it is given, escaped as `escape` does, except line breaks.

    main() puts it in place of sys.stderr, so that text the internal readers print there is escaped too.
    """

    def __init__(self, stream: TextIO) -> None:
        super().__init__()
        self._stream = stream

    @override
    def write(self, s: str, /) -> int:
        self._stream.write(escape(s, keep="\n"))
        return len(s)

    @override
    def flush(self) -> None:
        self._stream.flush()

    @override
    def writable(self) -> bool:
        return True

    @override
    def isatty(self) -> bool:
        return self._stream.isatty()

    @override
    def fileno(self) -> int:
        return self._stream.fileno()


@dataclass(frozen=True)
class Problem:
    """
    A diagnostic from the API, or a problem the command found itself, in the shape both are reported in.

    `kind` is a DiagnosticKind value or one of COMMAND_KINDS; the other fields are as in Diagnostic.
    """

    kind: str
    message: str
    file: str | None = None
    table: str | None = None
    record: int | None = None
    field: str | None = None

    @classmethod
    def from_diagnostic(cls, diagnostic: Diagnostic) -> Self:
        return cls(
            diagnostic.kind.value,
            diagnostic.message,
            diagnostic.file,
            diagnostic.table,
            diagnostic.record,
            diagnostic.field,
        )


def location(problem: Problem) -> str:
    """
    Where `problem` is: its table, record and field when it names a table, else its file, record and field.

    A table's records are all in CroBank, so the file is left out when a table is named.
    """
    parts = []
    if problem.table is not None:
        parts.append(f'table "{problem.table}"')
        if problem.record is not None:
            parts.append(f"record {problem.record}")
    else:
        where = [] if problem.file is None else [problem.file]
        if problem.record is not None:
            where.append(f"record {problem.record}")
        if where:
            parts.append(" ".join(where))
    if problem.field is not None:
        parts.append(f'field "{problem.field}"')
    return ", ".join(parts)


def format_problem(problem: Problem) -> str:
    """The stderr line for `problem`, escaped so that it is one line and holds no terminal control sequence."""
    where = location(problem)
    if where:
        return escape(f"warning: {problem.kind}: {where}: {problem.message}")
    return escape(f"warning: {problem.kind}: {problem.message}")


class Report:
    """Prints each problem on stderr as it is reported, and counts them by kind for the summary."""

    def __init__(self) -> None:
        self._counts: Counter[str] = Counter()

    def problem(self, problem: Problem) -> None:
        self._counts[problem.kind] += 1
        print(format_problem(problem), file=sys.stderr)

    def diagnostic(self, diagnostic: Diagnostic) -> None:
        """Report an API diagnostic; this is what the command passes to cronos_extract.open as on_diagnostic."""
        self.problem(Problem.from_diagnostic(diagnostic))

    @property
    def total(self) -> int:
        """The number of problems reported."""
        return sum(self._counts.values())

    def summary(self) -> str:
        """The counts of problems by kind, as one line."""
        total = self.total
        if not total:
            return "no diagnostics"
        noun = "diagnostic" if total == 1 else "diagnostics"
        counts = ", ".join(f"{self._counts[kind]} {kind}" for kind in KIND_ORDER if self._counts[kind])
        return f"{total} {noun}: {counts}"

    def print_summary(self) -> None:
        """Print the summary on stderr, after a blank line when problem lines precede it."""
        if self.total:
            print(file=sys.stderr)
        print(self.summary(), file=sys.stderr)


class Failure(Exception):
    """A problem that ends the command: main prints "Error: " and the message on stderr and exits with `status`."""

    def __init__(self, message: str, status: int = 1) -> None:
        super().__init__(message)
        self.status = status


def error_message(error: BaseException) -> str:
    """The text of the Error line for `error`, with the API's hint about recovering a KOD replaced by the command's."""
    return str(error).replace(DEFINITION_HINT, KOD_HINT)


def print_error(message: str) -> None:
    """Print the one Error line that ends a command that failed."""
    print(f"Error: {message}", file=sys.stderr)
```

`Report` only ever receives kinds from `DiagnosticKind` and `COMMAND_KINDS`, which `KIND_ORDER` lists in full, so
the summary counts every problem printed.

- [ ] **Step 4: Run the report tests to see them pass**

Run: `uv run pytest -q tests/test_cli_report.py` — Expected: all pass.

- [ ] **Step 5: Write the failing options tests**

Create `tests/test_cli_options.py`:

```python
# ABOUTME: Tests for the KOD and --compact options that export and inspect share, and the Kod they select.
# ABOUTME: They parse real arguments and crack real encrypted databases from tests/cronos_builder.py.
import argparse
from pathlib import Path

import pytest
from cronos_builder import TEST_TABLE_ID, bank_record, crackable_database, random_kod, write_database

from cronos_extract import Kod
from cronos_extract._cli.options import kod_options, selected_kod
from cronos_extract._cli.report import Failure

KOD = random_kod(seed=3)
PERSON_FIELDS = [b"42", b"Hammersley", b"", b"1240315", b"0930", b"", b"", b"", b"", b"", b""]


def parser_with(*, crack: bool = True, compact: bool = True) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="test", parents=[kod_options(crack=crack, compact=compact)])
    parser.add_argument("dbdir")
    return parser


def test_kod_reads_512_hex_digits() -> None:
    args = parser_with().parse_args(["--kod", bytes(KOD).hex(), "db"])

    assert args.kod == Kod.from_table(KOD)


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("zz" * 256, "exactly 512 hex digits"),
        ("00" * 255, "exactly 512 hex digits"),
        ("00" * 256, "each number from 0 to 255 exactly once"),
    ],
    ids=["not-hex", "too-short", "not-a-permutation"],
)
def test_kod_that_is_not_a_kod_is_a_usage_error_giving_the_reason(
    text: str, reason: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        parser_with().parse_args(["--kod", text, "db"])

    assert stopped.value.code == 2
    error = capsys.readouterr().err
    assert reason in error
    assert "--kod" in error


@pytest.mark.parametrize(
    "options",
    [["--kod", bytes(KOD).hex(), "--nokod"], ["--nokod", "--crack", "dbcrack"], ["-n", "--crack", "strucrack"]],
)
def test_kod_nokod_and_crack_exclude_each_other(options: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        parser_with().parse_args([*options, "db"])

    assert stopped.value.code == 2
    assert "not allowed with" in capsys.readouterr().err


def test_options_left_out_still_have_their_defaults() -> None:
    args = parser_with(crack=False, compact=False).parse_args(["db"])

    assert (args.kod, args.nokod, args.crack, args.compact) == (None, False, None, False)


@pytest.mark.parametrize("option", ["--crack", "--compact"])
def test_options_left_out_are_not_accepted(option: str) -> None:
    with pytest.raises(SystemExit) as stopped:
        parser_with(crack=False, compact=False).parse_args([option, "strucrack", "db"])

    assert stopped.value.code == 2


def test_the_default_kod_is_selected_without_options() -> None:
    assert selected_kod(parser_with().parse_args(["db"])) == Kod.default()


def test_nokod_selects_no_kod() -> None:
    assert selected_kod(parser_with().parse_args(["--nokod", "db"])) is None


def test_kod_selects_the_kod_given() -> None:
    assert selected_kod(parser_with().parse_args(["--kod", bytes(KOD).hex(), "db"])) == Kod.from_table(KOD)


@pytest.mark.parametrize("method", ["strucrack", "dbcrack"])
def test_crack_selects_the_kod_it_recovers(tmp_path: Path, method: str) -> None:
    dbdir = crackable_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, PERSON_FIELDS)], KOD)

    assert selected_kod(parser_with().parse_args(["--crack", method, dbdir])) == Kod.from_table(KOD)


def test_crack_that_recovers_nothing_fails_naming_the_crack_command(tmp_path: Path) -> None:
    dbdir = write_database(
        tmp_path / "db", [bank_record(TEST_TABLE_ID, PERSON_FIELDS)], KOD, index_records=[bytes(12)] * 3
    )

    with pytest.raises(Failure) as failed:
        selected_kod(parser_with().parse_args(["--crack", "dbcrack", dbdir]))

    assert failed.value.status == 1
    assert f"cronos-extract crack strucrack {dbdir}" in str(failed.value)
```

- [ ] **Step 6: Run the options tests to see them fail**

Run: `uv run pytest -q tests/test_cli_options.py`
Expected: collection error, `ModuleNotFoundError: No module named 'cronos_extract._cli.options'`.

- [ ] **Step 7: Write `_cli/options.py`**

```python
# ABOUTME: The command-line parts that subcommands share: the KOD and --compact options, and the Kod they select.
# ABOUTME: --kod is validated as it is parsed, and --crack recovers the KOD with cronos_extract.crack_kod.
import argparse

from .._api.crack import crack_kod
from .._api.kod import Kod
from .report import Failure

# The result of ArgumentParser.add_subparsers(), to which each subcommand module adds its parser.
type Subcommands = argparse._SubParsersAction[argparse.ArgumentParser]

CRACK_METHODS = ("strucrack", "dbcrack")


def kod_argument(text: str) -> Kod:
    """Parse a --kod value. Raises argparse.ArgumentTypeError with Kod.from_hex's reason when it is not a KOD."""
    try:
        return Kod.from_hex(text)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from e


def kod_options(*, crack: bool = True, compact: bool = True) -> argparse.ArgumentParser:
    """
    A parent parser holding --kod and --nokod, and --crack and --compact unless they are turned off.

    --kod, --nokod and --crack exclude each other. An option turned off still gets its default, None for --crack and
    False for --compact, so selected_kod and the handlers can read all four from every subcommand's arguments.
    """
    parser = argparse.ArgumentParser(add_help=False)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--kod", type=kod_argument, metavar="HEX", help="decode the records with this KOD table, as 512 hex digits"
    )
    group.add_argument("--nokod", "-n", action="store_true", help="read the records without KOD decoding")
    if crack:
        group.add_argument(
            "--crack", choices=CRACK_METHODS, help="first recover the database's KOD with this method, then use it"
        )
    else:
        parser.set_defaults(crack=None)
    if compact:
        parser.add_argument(
            "--compact",
            action="store_true",
            help="read the indexes from disk instead of memory, for very large databases; about 15%% slower",
        )
    else:
        parser.set_defaults(compact=False)
    return parser


def selected_kod(args: argparse.Namespace) -> Kod | None:
    """
    The KOD that the options in `args` select: --kod's, None for --nokod, the one --crack recovers from the database
    in args.dbdir, or the default KOD.

    Raises Failure when --crack recovers no KOD, and CronosError or OSError when --crack cannot read the database.
    """
    if args.kod is not None:
        return args.kod
    if args.nokod:
        return None
    if args.crack is not None:
        kod = crack_kod(args.dbdir, args.crack)
        if kod is None:
            raise Failure(
                f"{args.crack} cannot recover the KOD of {args.dbdir}; recover it with "
                f"cronos-extract crack strucrack {args.dbdir} and pass it with --kod"
            )
        return kod
    return Kod.default()
```

- [ ] **Step 8: Add `run_in_process` to `tests/cli.py`**

Replace the whole file with:

```python
# ABOUTME: Runs the cronos_extract commands for tests: in a subprocess with the interpreter running pytest, or
# ABOUTME: one subcommand's parser and handler in this process, before the command line assembles them all.
import argparse
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from cronos_extract._cli.options import Subcommands


def run_command(
    module: str, args: list[str], cwd: Path | None = None, stdin: str | None = None, timeout: float | None = None
) -> subprocess.CompletedProcess[str]:
    """Run `python -m cronos_extract.<module> <args>`, feeding it `stdin`, and capture its output as UTF-8 text.

    With `timeout`, the command is killed after that many seconds and subprocess.TimeoutExpired is raised, so a
    test of a command that could block cannot hang the suite.
    """
    return subprocess.run(
        [sys.executable, "-m", f"cronos_extract.{module}", *args],
        cwd=cwd,
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=timeout,
    )


def run_in_process(add_parser: Callable[[Subcommands], None], args: list[str]) -> int:
    """
    Parse `args` with a parser holding only the subcommand that `add_parser` adds, and run its handler here.

    Returns the handler's exit status. Exceptions reach the caller as they would reach cli.main, and argparse's usage
    errors raise SystemExit.
    """
    parser = argparse.ArgumentParser(prog="cronos-extract")
    add_parser(parser.add_subparsers(dest="subcommand", required=True))
    parsed = parser.parse_args(args)
    return int(parsed.handler(parsed, parsed.command_parser))
```

- [ ] **Step 9: Run every check**

Run: `uv run pytest -q tests/test_cli_report.py tests/test_cli_options.py` — Expected: all pass.
Run: `uv run ruff format && uv run ruff check && uv run ty check && uv run pytest -q` — Expected: all clean.

- [ ] **Step 10: Commit**

```bash
git add src/cronos_extract/_cli tests/cli.py tests/test_cli_report.py tests/test_cli_options.py
git commit -m "Add the command line's problem reporting and KOD options" -m "report.py escapes what the command writes to stderr, prints one line per diagnostic, counts them for the summary, and defines Failure. options.py holds the shared --kod, --nokod, --crack and --compact options and the Kod they select.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The export walk and the CSV writer

**Files:**
- Create: `src/cronos_extract/_cli/names.py`, `src/cronos_extract/_cli/export.py`,
  `src/cronos_extract/_cli/csv_out.py`
- Modify: `src/cronos_extract/croconvert.py` (imports the name helpers), `tests/cronos_builder.py`,
  `tests/test_cronos_builder.py`, `tests/test_croconvert.py` (imports the helpers that move to the builder)
- Test: `tests/test_cli_names.py`, `tests/test_cli_export.py`

**Interfaces:**
- Consumes: Task 2's `Report`, `Problem`, `Failure`, `DUPLICATE_TABLE`, `error_message`, `Subcommands`,
  `kod_options`, `selected_kod`, `run_in_process`. The API: `cronos_extract._api.bank.open(path, *, kod, compact,
  on_diagnostic) -> Bank`; `Bank.tables`, `Bank.files() -> Iterator[EmbeddedFile]`, `Bank.read_file(FileReference) ->
  EmbeddedFile | None`, `Bank.files_abbreviation -> str | None`, `Bank._files_table_id: int | None`; `Table.id`,
  `.name`, `.abbreviation`, `.fields: tuple[FieldDefinition, ...]`, `.records()`; `Record.number`, `.fields`;
  `Field.definition`, `.value`, `.text`; `FileReference(name, extension, record)`; `EmbeddedFile(record, data, name)`.
- Produces:
  - `names.safepathname(name: str) -> str`, `names.truncate_utf8(text: str, max_bytes: int) -> str`,
    `names.unique_name(stem: str, extension: str, number: int, used_names: dict[str, int], max_bytes: int) -> str |
    None`, `names.unique_file_name(stem: str, extension: str, number: int, used_names: dict[str, int]) -> str | None`,
    `names.MAX_FILE_NAME_BYTES`, `names.MAX_EXTENSION_BYTES`, `names.POSTGRES_IDENTIFIER_BYTES`.
  - `export.Writer` (Protocol): `table(table: Table) -> None`, `record(table: Table, record: Record) -> None`,
    `diagnostic(problem: Problem) -> None`, `finish() -> None`, `close() -> None`.
  - `export.Problems(report)` with `.problem(problem)`, `.diagnostic(diagnostic)`, `.start(writer)`.
  - `export.add_parser(subcommands)`, `export.run_export(args, parser) -> int`, `export.walk(bank, writer,
    on_problem)`, `export.make_writer(...)`, `export.output_target(args) -> Path | None`,
    `export.delimiter_argument(text) -> str`.
  - `csv_out.CsvWriter(directory: Path, bank: Bank, on_problem: Callable[[Problem], None], *, delimiter: str, files:
    bool)`, `csv_out.REFERENCED_DIRECTORY = "Files-Referenced"`.
  - Builder: `record_with_file_field(file_field: bytes) -> bytes`, `files_table_definition() -> bytes`,
    `renamed_table_definition(definition: bytes, *, name: bytes | None = None, abbreviation: bytes | None = None) ->
    bytes`, `database_with_files_abbreviation(directory: Path, abbreviation: bytes, bank_records=()) -> str`,
    `duplicate_table_name_database(directory: Path, second_table_name: bytes = b"erdgeist") -> str`.

- [ ] **Step 1: Write the failing builder tests**

Append to `tests/test_cronos_builder.py` (add `import cronos_extract` and the new builder names to its imports):

```python
def test_renamed_table_definition_changes_the_name_and_the_abbreviation(tmp_path: Path) -> None:
    second = renamed_table_definition(patched_table_definition(tableid=2), name=b"other", abbreviation=b"OT")
    dbdir = database_with_extra_definition_key(tmp_path / "db", "Base002", second)

    with cronos_extract.open(dbdir) as bank:
        assert [(table.id, table.name, table.abbreviation) for table in bank.tables] == [
            (1, "erdgeist", "ER"),
            (2, "other", "OT"),
        ]


def test_database_with_files_abbreviation_gives_the_files_table_that_abbreviation(tmp_path: Path) -> None:
    dbdir = database_with_files_abbreviation(tmp_path / "db", "Файлы".encode("cp1251"), [file_record(b"DATA")])

    with cronos_extract.open(dbdir) as bank:
        assert bank.files_abbreviation == "Файлы"
        assert [file.data for file in bank.files()] == [b"DATA"]


def test_duplicate_table_name_database_holds_two_tables_with_one_name(tmp_path: Path) -> None:
    with cronos_extract.open(duplicate_table_name_database(tmp_path / "db")) as bank:
        assert [(table.id, table.name) for table in bank.tables] == [(1, "erdgeist"), (2, "erdgeist")]
        assert [[record.fields[2].text for record in table.records()] for table in bank.tables] == [["one"], ["two"]]


def test_record_with_file_field_puts_the_reference_in_the_file_field(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [record_with_file_field(file_reference_field("scan", "jpg", 7))])

    with cronos_extract.open(dbdir) as bank:
        (record,) = bank.tables[0].records()
        assert record["Entry #6"].value == cronos_extract.FileReference("scan", "jpg", 7)
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest -q tests/test_cronos_builder.py` — Expected: `ImportError` for `renamed_table_definition`.

- [ ] **Step 3: Add the builder helpers**

In `tests/cronos_builder.py`, add after `bank_record`:

```python
def record_with_file_field(file_field: bytes) -> bytes:
    """Build a record of the test table whose fields are empty except for the file reference `file_field`."""
    fields = [b""] * TEST_TABLE_FIELD_COUNT
    fields[TEST_TABLE_FILE_FIELD_INDEX] = file_field
    return bank_record(TEST_TABLE_ID, fields)
```

Add after `erdgeist_table_definition`:

```python
def files_table_definition() -> bytes:
    """Return the definition bytes of TEST_DB's Files table, the value of its Base000 key."""
    with Database(str(TEST_DB), False, KODcoding(INITIAL_KOD)) as db:
        return cast(bytes, db.read_db_definition()["Base000"])


def renamed_table_definition(
    definition: bytes, *, name: bytes | None = None, abbreviation: bytes | None = None
) -> bytes:
    """Return the table definition `definition` with its name or abbreviation replaced by CP-1251 bytes.

    Both follow the table id, each stored as a length byte and the bytes, so each is at most 255 bytes long.
    """
    name_start = TABLE_ID_OFFSET + 4
    abbreviation_start = name_start + 1 + definition[name_start]
    abbreviation_end = abbreviation_start + 1 + definition[abbreviation_start]
    new_name = definition[name_start:abbreviation_start] if name is None else bytes([len(name)]) + name
    new_abbreviation = (
        definition[abbreviation_start:abbreviation_end]
        if abbreviation is None
        else bytes([len(abbreviation)]) + abbreviation
    )
    return definition[:name_start] + new_name + new_abbreviation + definition[abbreviation_end:]
```

Replace `database_with_extra_definition_key`'s body line that builds `stru[0]` with a call to a new helper, and add
the helper and two database writers after it:

```python
def definition_with_extra_key(dbinfo: bytes, keyname: str, value: bytes) -> bytes:
    """Return the database definition `dbinfo` with the key `keyname` appended, holding `value` inline."""
    name = keyname.encode("cp1251")
    return dbinfo + bytes([len(name)]) + name + struct.pack("<L", len(value) | INLINE_DEFINITION_VALUE) + value


def database_with_extra_definition_key(
    directory: Path, keyname: str, value: bytes, bank_records: Sequence[bytes | None] = ()
) -> str:
    """Write a database whose database definition has an extra key `keyname` holding `value` inline.

    The key is appended after TEST_DB's own keys; a key already there, such as "BankName", becomes a duplicate.
    """
    stru = stru_records_from_test_db()
    dbinfo = stru[0]
    assert dbinfo is not None
    stru[0] = definition_with_extra_key(dbinfo, keyname, value)
    write_datafile(directory, "Stru", stru)
    write_datafile(directory, "Bank", bank_records)
    return str(directory)


def database_with_files_abbreviation(
    directory: Path, abbreviation: bytes, bank_records: Sequence[bytes | None] = ()
) -> str:
    """Write a database whose Files table has the abbreviation `abbreviation`, given in CP-1251.

    TEST_DB's Base000 key is renamed Xase000, which is not a table key, and a Base000 key holding the Files table's
    definition with the new abbreviation is appended.
    """
    stru = stru_records_from_test_db()
    dbinfo = stru[0]
    assert dbinfo is not None
    assert dbinfo.count(b"\x07Base000") == 1
    files_table = renamed_table_definition(files_table_definition(), abbreviation=abbreviation)
    stru[0] = definition_with_extra_key(dbinfo.replace(b"\x07Base000", b"\x07Xase000"), "Base000", files_table)
    write_datafile(directory, "Stru", stru)
    write_datafile(directory, "Bank", bank_records)
    return str(directory)


def duplicate_table_name_database(directory: Path, second_table_name: bytes = b"erdgeist") -> str:
    """Write a database with tables "erdgeist" and `second_table_name`, ids 1 and 2, with records "one" and "two".

    The second table is the first table's definition with its table id and name changed, added to CroStru's
    database definition as an inline Base002 entry.
    """
    fields_one = [b""] * TEST_TABLE_FIELD_COUNT
    fields_one[1] = b"one"
    fields_two = [b""] * TEST_TABLE_FIELD_COUNT
    fields_two[1] = b"two"
    second = renamed_table_definition(patched_table_definition(tableid=2), name=second_table_name)
    return database_with_extra_definition_key(
        directory, "Base002", second, [bank_record(TEST_TABLE_ID, fields_one), bank_record(2, fields_two)]
    )
```

In `tests/test_croconvert.py`, delete its own `record_with_file_field`, `duplicate_table_name_database` and
`TABLE_ID_OFFSET`, import `record_with_file_field` and `duplicate_table_name_database` from `cronos_builder`, and
remove imports that become unused (`uv run ruff check` names them).

- [ ] **Step 4: Run the builder and croconvert tests**

Run: `uv run pytest -q tests/test_cronos_builder.py tests/test_croconvert.py` — Expected: all pass.

- [ ] **Step 5: Write the failing name tests**

Create `tests/test_cli_names.py`:

```python
# ABOUTME: Tests for the safe, unique names an export gives its files, directories and PostgreSQL identifiers.
# ABOUTME: They call _cli/names.py directly.
import pytest

from cronos_extract._cli.names import MAX_FILE_NAME_BYTES, safepathname, truncate_utf8, unique_file_name


def test_safepathname_replaces_separators_and_characters_windows_forbids() -> None:
    assert safepathname('a/b\\c:d*e?f"g<h>i|j\x00k\x1fl') == "a_b_c_d_e_f_g_h_i_j_k_l"


def test_truncate_utf8_cuts_at_a_character_boundary() -> None:
    assert truncate_utf8("яяя", 5) == "яя"


@pytest.mark.parametrize(("stem", "expected"), [("", "7"), ("..", "7"), ("../..", ".._.."), ("a/b", "a_b")])
def test_a_file_name_is_safe_and_never_only_dots(stem: str, expected: str) -> None:
    assert unique_file_name(stem, "", 7, {}) == expected


def test_a_name_used_by_another_number_gets_the_number_appended() -> None:
    used: dict[str, int] = {}

    assert unique_file_name("same", "txt", 3, used) == "same.txt"
    assert unique_file_name("SAME", "txt", 4, used) == "SAME-4.txt"
    assert unique_file_name("same", "txt", 3, used) is None


def test_a_long_name_fits_the_file_name_limit_and_keeps_its_extension() -> None:
    name = unique_file_name("я" * 200, "x" * 100, 1, {})

    assert name is not None
    assert len(name.encode("utf-8")) <= MAX_FILE_NAME_BYTES
    assert name.startswith("яяя")
    assert name.endswith("." + "x" * 63)
```

- [ ] **Step 6: Run them to see them fail**

Run: `uv run pytest -q tests/test_cli_names.py` — Expected: `ModuleNotFoundError: No module named 'cronos_extract._cli.names'`.

- [ ] **Step 7: Move the name helpers into `_cli/names.py`**

Create `src/cronos_extract/_cli/names.py` holding `safepathname`, `MAX_FILE_NAME_BYTES`, `MAX_EXTENSION_BYTES`,
`POSTGRES_IDENTIFIER_BYTES`, `truncate_utf8`, `unique_name` and `unique_file_name`, cut from `croconvert.py` with
their docstrings, comments and bodies unchanged, and these annotations added:

```python
# ABOUTME: Safe, unique names for what an export writes: file and directory names, and PostgreSQL identifiers.
# ABOUTME: Names are compared case-insensitively and shortened at a character boundary to fit a byte limit.
import re
from itertools import chain, count

# ... constants as in croconvert.py ...


def safepathname(name: str) -> str: ...
def truncate_utf8(text: str, max_bytes: int) -> str: ...
def unique_name(stem: str, extension: str, number: int, used_names: dict[str, int], max_bytes: int) -> str | None: ...
def unique_file_name(stem: str, extension: str, number: int, used_names: dict[str, int]) -> str | None: ...
```

In `croconvert.py`, delete those definitions and add
`from ._cli.names import POSTGRES_IDENTIFIER_BYTES, safepathname, unique_file_name, unique_name`; remove the imports
that become unused (`re`, `chain`, `count`).

- [ ] **Step 8: Run the name and croconvert tests**

Run: `uv run pytest -q tests/test_cli_names.py tests/test_croconvert.py tests/test_cli_characterisation.py`
Expected: all pass.

- [ ] **Step 9: Write the failing CSV export tests**

Create `tests/test_cli_export.py`:

```python
# ABOUTME: Tests for the export subcommand: each format's layout, the -o rules, diagnostics and exit statuses.
# ABOUTME: They export crafted databases from tests/cronos_builder.py, in this process or by running the command.
import csv
import os
import re
from pathlib import Path

import pytest
from cli import run_in_process
from cronos_builder import (
    TEST_DB,
    TEST_TABLE_FIELD_COUNT,
    TEST_TABLE_ID,
    bank_record,
    database_with_extra_definition_key,
    database_with_files_abbreviation,
    erdgeist_table_definition,
    file_record,
    file_reference_field,
    patched_table_definition,
    record_with_file_field,
    renamed_table_definition,
    write_database,
)

from cronos_extract import DatabaseDefinitionError
from cronos_extract._cli import export

HEADER = ["Системный номер", *(f"Entry #{number}" for number in range(1, 12))]
# Both of TEST_DB's table definitions report that their Section 2 is not marked with a 2.
TEST_DB_SUMMARY = "2 diagnostics: 2 unexpected_structure"


def table_record(values: dict[int, bytes]) -> bytes:
    """A record of the test table holding `values` by field index, Entry #1 being 0, with every other field empty."""
    fields = [b""] * TEST_TABLE_FIELD_COUNT
    for index, value in values.items():
        fields[index] = value
    return bank_record(TEST_TABLE_ID, fields)


def export_csv(dbdir: str | Path, outdir: Path, *options: str) -> int:
    return run_in_process(export.add_parser, ["export", "--csv", *options, "-o", str(outdir), str(dbdir)])


def csv_rows(path: Path, delimiter: str = ",") -> list[list[str]]:
    with path.open(encoding="utf-8", newline="") as file:
        return list(csv.reader(file, delimiter=delimiter))


def names_in(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir())


def snapshot(path: Path) -> tuple[str, object]:
    """What `path` is and holds, to check that an export left it alone."""
    if path.is_symlink():
        return "link", os.readlink(path)
    if path.is_dir():
        return "directory", names_in(path)
    return "file", path.read_bytes()


def test_csv_export_writes_a_file_per_table_and_the_files_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    outdir = tmp_path / "out"

    assert export_csv(TEST_DB, outdir) == 0

    assert names_in(outdir) == ["Files-FL", "erdgeist.csv"]
    assert names_in(outdir / "Files-FL") == []
    assert csv_rows(outdir / "erdgeist.csv") == [HEADER]
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines()[-1] == TEST_DB_SUMMARY


def test_csv_files_are_utf8_without_a_bom_and_end_rows_with_crlf(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [table_record({0: "Иванов".encode("cp1251")})])

    assert export_csv(dbdir, tmp_path / "out") == 0

    data = (tmp_path / "out" / "erdgeist.csv").read_bytes()
    assert data.startswith("Системный номер,Entry #1,".encode())
    assert data.endswith(("1,Иванов" + "," * 10 + "\r\n").encode())


def test_csv_cells_hold_exactly_what_the_api_decoded(tmp_path: Path) -> None:
    texts = ["=1+1", "-5", "+7 900", "@x", "multi\nline", "carriage\rreturn", 'a,"b"', "C:\\Users\\x"]
    dbdir = write_database(tmp_path / "db", [table_record({0: text.encode("cp1251")}) for text in texts])

    assert export_csv(dbdir, tmp_path / "out") == 0

    assert [row[1] for row in csv_rows(tmp_path / "out" / "erdgeist.csv")[1:]] == texts


def test_csv_export_creates_a_timestamped_directory_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert run_in_process(export.add_parser, ["export", "--csv", str(TEST_DB)]) == 0

    (created,) = tmp_path.iterdir()
    assert re.fullmatch(r"cronos-extract-\d{4}(-\d{2}){5}-\d{6}", created.name)
    assert (created / "erdgeist.csv").is_file()


@pytest.fixture(params=["directory", "file", "dangling-symlink"])
def existing_target(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    target = tmp_path / "out"
    if request.param == "directory":
        target.mkdir()
    elif request.param == "file":
        target.write_text("kept")
    else:
        target.symlink_to(tmp_path / "nowhere")
    return target


def test_csv_export_refuses_a_target_that_exists(
    existing_target: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = snapshot(existing_target)

    with pytest.raises(SystemExit) as stopped:
        export_csv(TEST_DB, existing_target)

    assert stopped.value.code == 2
    assert "already exists" in capsys.readouterr().err
    assert snapshot(existing_target) == before
    assert not (tmp_path / "nowhere").exists()


def test_csv_export_creates_nothing_when_the_database_cannot_be_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(DatabaseDefinitionError):
        export_csv(TEST_DB, tmp_path / "out", "--nokod")

    assert not (tmp_path / "out").exists()
    assert capsys.readouterr().err.splitlines()[-1] == "1 diagnostic: 1 unexpected_structure"


def test_csv_export_leaves_the_working_directory_unchanged(tmp_path: Path) -> None:
    before = Path.cwd()

    export_csv(TEST_DB, tmp_path / "out")

    assert Path.cwd() == before


def test_csv_export_writes_the_stored_and_the_referenced_files(tmp_path: Path) -> None:
    dbdir = write_database(
        tmp_path / "db", [file_record(b"DATA"), record_with_file_field(file_reference_field("report", "pdf", 1))]
    )

    assert export_csv(dbdir, tmp_path / "out") == 0

    assert (tmp_path / "out" / "Files-FL" / "1").read_bytes() == b"DATA"
    assert (tmp_path / "out" / "Files-Referenced" / "report.pdf").read_bytes() == b"DATA"


def test_files_referenced_is_created_for_a_record_whose_file_field_is_empty(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [record_with_file_field(b"")])

    assert export_csv(dbdir, tmp_path / "out") == 0

    assert names_in(tmp_path / "out" / "Files-Referenced") == []


def test_no_files_leaves_out_both_file_directories(tmp_path: Path) -> None:
    dbdir = write_database(
        tmp_path / "db", [file_record(b"DATA"), record_with_file_field(file_reference_field("report", "pdf", 1))]
    )

    assert export_csv(dbdir, tmp_path / "out", "--no-files") == 0

    assert names_in(tmp_path / "out") == ["erdgeist.csv"]


def test_the_delimiter_separates_the_cells(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [table_record({0: b"a;b"})])

    assert export_csv(dbdir, tmp_path / "out", "--delimiter", ";") == 0

    table = tmp_path / "out" / "erdgeist.csv"
    assert table.read_text(encoding="utf-8").startswith("Системный номер;Entry #1;")
    assert csv_rows(table, delimiter=";")[1][:2] == ["1", "a;b"]


@pytest.mark.parametrize("delimiter", ['"', "\n", "ab", ""], ids=["quote", "line-break", "two-characters", "empty"])
def test_a_delimiter_csv_rejects_is_a_usage_error(
    tmp_path: Path, delimiter: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        export_csv(TEST_DB, tmp_path / "out", f"--delimiter={delimiter}")

    assert stopped.value.code == 2
    assert "cannot be a CSV delimiter" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    ("abbreviation", "expected"),
    [
        (b"Referenced", "Files-Referenced-0"),
        (b"REFERENCED", "Files-REFERENCED-0"),
        ("я".encode("cp1251") * 255, None),
    ],
    ids=["collides-with-referenced", "differs-only-in-case", "510-utf8-bytes"],
)
def test_the_files_directory_name_is_unique_and_short(
    tmp_path: Path, abbreviation: bytes, expected: str | None
) -> None:
    dbdir = database_with_files_abbreviation(
        tmp_path / "db",
        abbreviation,
        [file_record(b"DATA"), record_with_file_field(file_reference_field("a", "txt", 1))],
    )
    outdir = tmp_path / "out"

    assert export_csv(dbdir, outdir) == 0

    (files_directory,) = [path for path in outdir.iterdir() if path.is_dir() and path.name != "Files-Referenced"]
    assert (files_directory / "1").read_bytes() == b"DATA"
    assert (outdir / "Files-Referenced" / "a.txt").read_bytes() == b"DATA"
    assert len(files_directory.name.encode("utf-8")) <= 255
    if expected is not None:
        assert files_directory.name == expected


def test_a_table_defined_twice_with_one_name_and_id_is_exported_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dbdir = database_with_extra_definition_key(
        tmp_path / "db", "Base002", erdgeist_table_definition(), [table_record({0: b"one"})]
    )

    assert export_csv(dbdir, tmp_path / "out") == 0

    assert names_in(tmp_path / "out") == ["Files-FL", "erdgeist.csv"]
    assert [row[1] for row in csv_rows(tmp_path / "out" / "erdgeist.csv")[1:]] == ["one"]
    err = capsys.readouterr().err
    assert 'warning: duplicate_table: table "erdgeist": ' in err
    assert "1 duplicate_table" in err.splitlines()[-1]


def test_a_table_whose_safe_name_and_id_repeat_another_is_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    second = renamed_table_definition(erdgeist_table_definition(), name=b"ERDGEIST")
    dbdir = database_with_extra_definition_key(tmp_path / "db", "Base002", second, [table_record({0: b"one"})])

    assert export_csv(dbdir, tmp_path / "out") == 0

    assert names_in(tmp_path / "out") == ["Files-FL", "erdgeist.csv"]
    assert 'warning: duplicate_table: table "ERDGEIST": ' in capsys.readouterr().err


def test_hostile_names_stay_inside_the_output_directory(tmp_path: Path) -> None:
    hostile = "../../etc/passwd"
    second = renamed_table_definition(patched_table_definition(tableid=2), name=hostile.encode("cp1251"))
    dbdir = database_with_extra_definition_key(
        tmp_path / "db",
        "Base002",
        second,
        [
            file_record(b"DATA"),
            record_with_file_field(file_reference_field(hostile, "", 1)),
            bank_record(2, [b"x"] + [b""] * (TEST_TABLE_FIELD_COUNT - 1)),
        ],
    )
    outdir = tmp_path / "out"

    assert export_csv(dbdir, outdir) == 0

    assert names_in(tmp_path) == ["db", "out"]
    assert all(path.resolve().is_relative_to(outdir.resolve()) for path in outdir.rglob("*"))
    assert names_in(outdir) == [".._.._etc_passwd.csv", "Files-FL", "Files-Referenced", "erdgeist.csv"]
    assert names_in(outdir / "Files-Referenced") == [".._.._etc_passwd"]
```

- [ ] **Step 10: Run them to see them fail**

Run: `uv run pytest -q tests/test_cli_export.py` — Expected: `ImportError: cannot import name 'export'`.

- [ ] **Step 11: Write `_cli/csv_out.py`**

```python
# ABOUTME: The CSV export: a directory holding a CSV file per table, the Files table's files and the referenced files.
# ABOUTME: Every name is safe and unique within the directory; referenced files are written as their records are.
import csv
import os
from _csv import Writer as RowWriter
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from .._api.bank import Bank, Table
from .._api.values import FieldValue, FileReference, Record
from .names import unique_file_name
from .report import DUPLICATE_TABLE, Problem

FIELD_TYPE_FILE = 6
STRU_FILE = "CroStru.dat"
REFERENCED_DIRECTORY = "Files-Referenced"
# The number Files-Referenced is claimed with: no table id is negative, so no other name can be taken for it.
REFERENCED_NUMBER = -1


class CsvWriter:
    """
    Writes an export into `directory`, which exists and is empty.

    Each table goes to <table name>.csv, whose header row holds the field names and whose cells hold each field's
    text as the API decoded it. With `files`, the file a record refers to goes to Files-Referenced/ under its own
    name as the record is written, and every file of the Files table goes to Files-<abbreviation>/, named by its
    CroBank record number, at the end.
    """

    def __init__(
        self,
        directory: Path,
        bank: Bank,
        on_problem: Callable[[Problem], None],
        *,
        delimiter: str,
        files: bool,
    ) -> None:
        self._directory = directory
        self._bank = bank
        self._on_problem = on_problem
        self._delimiter = delimiter
        self._files = files
        self._names = {REFERENCED_DIRECTORY.casefold(): REFERENCED_NUMBER}
        self._files_directory = self._claim_files_directory() if files else None
        self._referenced_names: dict[str, int] = {}
        self._referenced_created = False
        self._stream: TextIO | None = None
        self._rows: RowWriter | None = None

    def table(self, table: Table) -> None:
        self._close_table()
        name = unique_file_name(table.name, "csv", table.id, self._names)
        if name is None:
            self._on_problem(
                Problem(
                    DUPLICATE_TABLE,
                    "its CSV file name and table id are those of a table already written, so it is skipped",
                    file=STRU_FILE,
                    table=table.name,
                )
            )
            return
        self._stream = open(self._directory / name, "x", encoding="utf-8", newline="")
        self._rows = csv.writer(self._stream, delimiter=self._delimiter)
        self._rows.writerow([field.name for field in table.fields])

    def record(self, table: Table, record: Record) -> None:
        if self._rows is None:
            return
        self._rows.writerow([field.text for field in record.fields])
        if self._files:
            for field in record.fields:
                if field.definition.type == FIELD_TYPE_FILE:
                    self._write_referenced(field.value)

    def diagnostic(self, problem: Problem) -> None:
        """CSV output holds no diagnostics; they are on stderr."""

    def finish(self) -> None:
        self._close_table()
        if self._files_directory is None:
            return
        os.mkdir(self._files_directory)
        for file in self._bank.files():
            with open(self._files_directory / str(file.record), "xb") as output:
                output.write(file.data)

    def close(self) -> None:
        self._close_table()

    def _claim_files_directory(self) -> Path | None:
        """
        The path of Files-<abbreviation>, claimed before any table's name, or None when there is no Files table.

        The Files table's id numbers the name, as a table's id numbers its CSV file's; the id is not public API.
        """
        abbreviation = self._bank.files_abbreviation
        files_table_id = self._bank._files_table_id
        if abbreviation is None or files_table_id is None:
            return None
        name = unique_file_name(f"Files-{abbreviation}", "", files_table_id, self._names)
        assert name is not None, "only Files-Referenced is claimed before it, with a number no table has"
        return self._directory / name

    def _close_table(self) -> None:
        if self._stream is not None:
            self._stream.close()
        self._stream = None
        self._rows = None

    def _write_referenced(self, value: FieldValue) -> None:
        """
        Write the file that the file field `value` refers to into Files-Referenced.

        The directory is created at the first file field met, empty or not, and a reference that cannot be read is
        left out; the API has reported it as unresolved_file_reference.
        """
        referenced = self._directory / REFERENCED_DIRECTORY
        if not self._referenced_created:
            os.mkdir(referenced)
            self._referenced_created = True
        if not isinstance(value, FileReference):
            return
        file = self._bank.read_file(value)
        if file is None:
            return
        name = unique_file_name(value.name, value.extension, file.record, self._referenced_names)
        if name is None:
            # This record's file is already written, under the name of its first reference.
            return
        with open(referenced / name, "xb") as output:
            output.write(file.data)
```

- [ ] **Step 12: Write `_cli/export.py`**

```python
# ABOUTME: The export subcommand: opens a database through the cronos_extract API and walks its tables once.
# ABOUTME: It checks and creates the -o target, skips a repeated table, routes diagnostics and prints the summary.
import argparse
import csv
import io
import os
from collections.abc import Callable
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from typing import NoReturn, Protocol

from .._api.bank import Bank, Table
from .._api.bank import open as open_bank
from .._api.diagnostics import Diagnostic
from .._api.errors import CronosError
from .._api.values import Record
from .csv_out import CsvWriter
from .options import Subcommands, kod_options, selected_kod
from .report import DUPLICATE_TABLE, Failure, Problem, Report, error_message

STRU_FILE = "CroStru.dat"
# The exit status of a command stopped by Ctrl-C, as a shell reports it: 128 plus SIGINT's number.
INTERRUPTED_STATUS = 130


class Writer(Protocol):
    """
    An output format. The export calls table() before each table's records, record() for each record, diagnostic()
    for each problem, finish() once every table is written, and close() at the end, finished or not.
    """

    def table(self, table: Table) -> None: ...

    def record(self, table: Table, record: Record) -> None: ...

    def diagnostic(self, problem: Problem) -> None: ...

    def finish(self) -> None: ...

    def close(self) -> None: ...


class Problems:
    """
    Routes each problem to the report, and to the writer once there is one.

    The writer is made after the database is open, so the problems found while opening it wait, and the writer is
    given them first.
    """

    def __init__(self, report: Report) -> None:
        self._report = report
        self._writer: Writer | None = None
        self._waiting: list[Problem] = []

    def problem(self, problem: Problem) -> None:
        self._report.problem(problem)
        if self._writer is None:
            self._waiting.append(problem)
        else:
            self._writer.diagnostic(problem)

    def diagnostic(self, diagnostic: Diagnostic) -> None:
        """Route an API diagnostic; this is what the export passes to cronos_extract.open as on_diagnostic."""
        self.problem(Problem.from_diagnostic(diagnostic))

    def start(self, writer: Writer) -> None:
        """Give `writer` the problems found so far, and each later one as it is found."""
        self._writer = writer
        for problem in self._waiting:
            writer.diagnostic(problem)
        self._waiting.clear()


def delimiter_argument(text: str) -> str:
    """Parse a --delimiter value: one character that the csv module accepts as a delimiter."""
    try:
        csv.writer(io.StringIO(), delimiter=text)
    except (TypeError, ValueError) as e:
        raise argparse.ArgumentTypeError(f"{text!r} cannot be a CSV delimiter: {e}") from e
    return text


def add_parser(subcommands: Subcommands) -> None:
    """Add the export subcommand to `subcommands`."""
    parser = subcommands.add_parser(
        "export",
        parents=[kod_options()],
        help="export every table of a database",
        description="Export every table of the CronosPro database in DBDIR. Each diagnostic is printed on stderr as "
        "it happens, and a count of them at the end.",
    )
    output_format = parser.add_mutually_exclusive_group(required=True)
    output_format.add_argument(
        "--csv", action="store_true", help="create a directory holding a CSV file per table and the stored files"
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="the directory or file to create, which must not exist; by default --csv creates "
        "cronos-extract-<date and time> in the current directory, and the other formats write to stdout",
    )
    parser.add_argument("--delimiter", type=delimiter_argument, help="the CSV field delimiter; a comma by default")
    parser.add_argument("--no-files", action="store_true", help="with --csv, do not write the stored files")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit with status 1 when any diagnostic was reported; the output is written all the same",
    )
    parser.add_argument("dbdir", help="the database directory, holding the Cro*.dat and Cro*.tad files")
    parser.set_defaults(handler=run_export, command_parser=parser)


def output_target(args: argparse.Namespace) -> Path | None:
    """The directory or file the export creates, or None when it writes to stdout."""
    if args.output is not None:
        return args.output
    if args.csv:
        return Path(datetime.now().strftime("cronos-extract-%Y-%m-%d-%H-%M-%S-%f"))
    return None


def exists_error(parser: argparse.ArgumentParser, target: Path) -> NoReturn:
    parser.error(f"{target} already exists; export never overwrites, so name an output that does not exist")


def create_directory(directory: Path, parser: argparse.ArgumentParser) -> None:
    """Create `directory`, as a usage error when something has appeared there since the check."""
    try:
        os.mkdir(directory)
    except FileExistsError:
        exists_error(parser, directory)


def run_export(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Export the database in args.dbdir in the format the options choose, returning the exit status."""
    target = output_target(args)
    if target is not None and os.path.lexists(target):
        exists_error(parser, target)
    report = Report()
    try:
        export(args, parser, target, Problems(report))
    finally:
        report.print_summary()
    return 1 if args.strict and report.total else 0


def export(args: argparse.Namespace, parser: argparse.ArgumentParser, target: Path | None, problems: Problems) -> None:
    """
    Open the database, create the output and write every table to it.

    Once the output exists, a failure or an interruption is raised as a Failure that says where the output is.
    """
    created: Path | None = None
    try:
        with ExitStack() as stack:
            bank = stack.enter_context(
                open_bank(args.dbdir, kod=selected_kod(args), compact=args.compact, on_diagnostic=problems.diagnostic)
            )
            writer, created = make_writer(args, parser, bank, target, problems)
            stack.callback(writer.close)
            problems.start(writer)
            walk(bank, writer, problems.problem)
            writer.finish()
    except BrokenPipeError:
        raise
    except (CronosError, OSError, KeyboardInterrupt) as e:
        if created is None:
            raise
        if isinstance(e, KeyboardInterrupt):
            raise Failure(f"interrupted; the output written so far is in {created}", INTERRUPTED_STATUS) from e
        raise Failure(f"{error_message(e)}; the output written so far is in {created}") from e


def make_writer(
    args: argparse.Namespace, parser: argparse.ArgumentParser, bank: Bank, target: Path | None, problems: Problems
) -> tuple[Writer, Path]:
    """Create the output of the chosen format, returning its writer and the path created."""
    assert target is not None, "--csv always has a target"
    create_directory(target, parser)
    writer = CsvWriter(target, bank, problems.problem, delimiter=args.delimiter or ",", files=not args.no_files)
    return writer, target


def walk(bank: Bank, writer: Writer, on_problem: Callable[[Problem], None]) -> None:
    """Give `writer` each table of `bank` and its records, skipping a table whose name and id repeat an earlier one."""
    written: set[tuple[str, int]] = set()
    for table in bank.tables:
        if (table.name, table.id) in written:
            on_problem(
                Problem(
                    DUPLICATE_TABLE,
                    "a table with this name and table id is defined before it, so it is skipped",
                    file=STRU_FILE,
                    table=table.name,
                )
            )
            continue
        written.add((table.name, table.id))
        writer.table(table)
        for record in table.records():
            writer.record(table, record)
```

- [ ] **Step 13: Run the export tests to see them pass**

Run: `uv run pytest -q tests/test_cli_export.py` — Expected: all pass.

- [ ] **Step 14: Run every check**

Run: `uv run ruff format && uv run ruff check && uv run ty check && uv run pytest -q` — Expected: all clean, and
`git diff master -- tests/golden` empty.

- [ ] **Step 15: Commit**

```bash
git add src/cronos_extract/_cli src/cronos_extract/croconvert.py tests/cronos_builder.py tests/test_cronos_builder.py tests/test_croconvert.py tests/test_cli_names.py tests/test_cli_export.py
git commit -m "Add the export walk and the CSV writer" -m "export opens the database through the API, checks that -o does not exist before reading and creates it after the database opens, skips a repeated table as duplicate_table, and prints every diagnostic and a summary. The CSV writer keeps croconvert's layout, writes referenced files as their records are read, and gives Files-<abbreviation> a unique name within the file name limit. The name helpers move to _cli/names.py.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The PostgreSQL writer

**Files:**
- Create: `src/cronos_extract/_cli/sql_out.py`
- Modify: `src/cronos_extract/_cli/export.py`
- Test: `tests/test_cli_export.py`

**Interfaces:**
- Consumes: Task 3's `Writer`, `Problems`, `make_writer`, `exists_error`, `names.unique_name`,
  `names.POSTGRES_IDENTIFIER_BYTES`; Task 2's `Problem`, `DUPLICATE_TABLE`, `REPLACED_NUL`.
- Produces:
  - `sql_out.unique_sql_table_name(table: Table, used_names: dict[str, int]) -> str | None`
  - `sql_out.unique_sql_column_names(fields: Sequence[FieldDefinition]) -> list[str]`
  - `sql_out.sql_value(table: Table, record: Record, field: Field, on_problem: Callable[[Problem], None]) -> str`
  - `sql_out.SqlWriter(stream: TextIO, on_problem: Callable[[Problem], None])`, a `Writer`.
  - `export.open_stream(target: Path | None, parser, stack: ExitStack) -> TextIO`,
    `export.check_format_options(args, parser) -> None`; `make_writer` gains a `stack: ExitStack` parameter and
    returns `tuple[Writer, Path | None]`.

The SQL layout (D9) is exactly: `SET standard_conforming_strings = on;`, then for each table a blank line, the
`CREATE TABLE` statement with one column per line indented by four spaces, and one `INSERT` line per record. No other
blank lines and no trailing spaces.

- [ ] **Step 1: Write the failing PostgreSQL tests**

Append to `tests/test_cli_export.py` (add `import argparse`, `from cronos_builder import duplicate_table_name_database`,
`from cronos_extract import FieldDefinition, open as open_bank` and
`from cronos_extract._cli.sql_out import unique_sql_column_names, unique_sql_table_name` to the imports):

```python
def export_to_stdout(dbdir: str | Path, *options: str) -> int:
    return run_in_process(export.add_parser, ["export", *options, str(dbdir)])


def insert_statements(sql: str) -> list[str]:
    return [line for line in sql.splitlines() if line.startswith("INSERT")]


TEST_DB_SQL = (
    "SET standard_conforming_strings = on;\n"
    "\n"
    'CREATE TABLE "erdgeist" (\n' + ",\n".join(f'    "{name}" TEXT' for name in HEADER) + "\n);\n"
)


def test_postgres_export_writes_the_layout_d9_describes(capsys: pytest.CaptureFixture[str]) -> None:
    assert export_to_stdout(TEST_DB, "--postgres") == 0

    captured = capsys.readouterr()
    assert captured.out == TEST_DB_SQL
    assert captured.err.splitlines()[-1] == TEST_DB_SUMMARY


def test_postgres_export_writes_one_insert_per_record_with_null_for_empty_values(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dbdir = write_database(
        tmp_path / "db",
        [table_record({0: b"O'Brien", 1: b"C:\\x"}), table_record({3: b"1240315", 4: b"0930"})],
    )

    assert export_to_stdout(dbdir, "--postgres") == 0

    assert insert_statements(capsys.readouterr().out) == [
        'INSERT INTO "erdgeist" VALUES '
        "('1', 'O''Brien', 'C:\\x', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);",
        'INSERT INTO "erdgeist" VALUES '
        "('2', NULL, NULL, NULL, '2024-03-15', '09:30', NULL, NULL, NULL, NULL, NULL, NULL);",
    ]


def test_postgres_export_replaces_nul_with_u_fffd_and_reports_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dbdir = write_database(tmp_path / "db", [table_record({1: b"a\x00b"})])

    assert export_to_stdout(dbdir, "--postgres") == 0

    captured = capsys.readouterr()
    (insert,) = insert_statements(captured.out)
    assert "'a\ufffdb'" in insert
    assert "\x00" not in captured.out
    assert (
        'warning: replaced_nul: table "erdgeist", record 1, field "Entry #2": the value holds NUL characters, which '
        "PostgreSQL text cannot hold; they are written as U+FFFD" in captured.err
    )
    assert captured.err.splitlines()[-1] == "3 diagnostics: 2 unexpected_structure, 1 replaced_nul"


def test_postgres_export_writes_a_file_that_o_names(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "out.sql"

    assert export_to_stdout(TEST_DB, "--postgres", "-o", str(output)) == 0

    assert output.read_text(encoding="utf-8") == TEST_DB_SQL
    assert capsys.readouterr().out == ""


def test_postgres_export_refuses_a_file_that_exists(tmp_path: Path) -> None:
    output = tmp_path / "out.sql"
    output.write_text("kept")

    with pytest.raises(SystemExit) as stopped:
        export_to_stdout(TEST_DB, "--postgres", "-o", str(output))

    assert stopped.value.code == 2
    assert output.read_text() == "kept"


@pytest.mark.parametrize(
    ("options", "message"),
    [(["--no-files"], "--no-files applies only to --csv"), (["--delimiter", ";"], "--delimiter applies only to --csv")],
    ids=["no-files", "delimiter"],
)
def test_csv_options_with_another_format_are_usage_errors(
    options: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        export_to_stdout(TEST_DB, "--postgres", *options)

    assert stopped.value.code == 2
    assert message in capsys.readouterr().err


def test_sql_column_names_are_unique_and_fit_postgres_identifiers() -> None:
    fields = [
        FieldDefinition("Системный номер", 0),
        FieldDefinition("я" * 40, 1),
        FieldDefinition("я" * 40 + "ж", 1),
        FieldDefinition("same", 1),
        FieldDefinition("SAME", 1),
        FieldDefinition("", 1),
        FieldDefinition('say "hi"', 1),
    ]

    names = unique_sql_column_names(fields)

    assert len({name.casefold() for name in names}) == len(fields), names
    assert all(len(name.encode("utf-8")) <= 63 for name in names), names
    assert names[3:] == ["same", "SAME-4", "5", "say _hi_"]


def test_sql_table_names_are_unique_and_fit_postgres_identifiers(tmp_path: Path) -> None:
    dbdir = duplicate_table_name_database(tmp_path / "db", second_table_name=("я" * 100).encode("cp1251"))
    used_names: dict[str, int] = {}

    with open_bank(dbdir) as bank:
        names = [unique_sql_table_name(table, used_names) for table in bank.tables]

    assert names[0] == "erdgeist"
    assert names[1] is not None
    assert len(names[1].encode("utf-8")) <= 63


def test_a_table_whose_sql_name_and_id_repeat_another_is_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    second = renamed_table_definition(erdgeist_table_definition(), name=b"ERDGEIST")
    dbdir = database_with_extra_definition_key(tmp_path / "db", "Base002", second, [table_record({0: b"one"})])

    assert export_to_stdout(dbdir, "--postgres") == 0

    captured = capsys.readouterr()
    assert [line for line in captured.out.splitlines() if line.startswith("CREATE")] == ['CREATE TABLE "erdgeist" (']
    assert len(insert_statements(captured.out)) == 1
    assert 'warning: duplicate_table: table "ERDGEIST": ' in captured.err
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest -q tests/test_cli_export.py -k "postgres or sql or csv_options"`
Expected: `ModuleNotFoundError: No module named 'cronos_extract._cli.sql_out'`.

- [ ] **Step 3: Write `_cli/sql_out.py`**

```python
# ABOUTME: The PostgreSQL export: a CREATE TABLE per table, every column TEXT, and one INSERT per record.
# ABOUTME: Names are quoted, unique and at most 63 bytes; values are standard SQL literals, with NULL when empty.
from collections.abc import Callable, Sequence
from typing import TextIO

from .._api.bank import Table
from .._api.values import Field, FieldDefinition, Record
from .names import POSTGRES_IDENTIFIER_BYTES, unique_name
from .report import DUPLICATE_TABLE, REPLACED_NUL, Problem

BANK_FILE = "CroBank.dat"
STRU_FILE = "CroStru.dat"


def unique_sql_table_name(table: Table, used_names: dict[str, int]) -> str | None:
    """
    Return the name to give `table` in SQL output, or None when a table with the same name and table id
    is already written. Double quotes become underscores, an empty name becomes the table id, and the name
    fits in POSTGRES_IDENTIFIER_BYTES. See unique_name for how names are kept unique.
    """
    name = table.name.replace('"', "_") or str(table.id)
    return unique_name(name, "", table.id, used_names, POSTGRES_IDENTIFIER_BYTES)


def unique_sql_column_names(fields: Sequence[FieldDefinition]) -> list[str]:
    """
    Return the names to give the columns of a table with `fields` in SQL output, in the order of the fields.
    Double quotes become underscores, an empty name becomes the column number, counting the system number
    as column 0, and every name is unique within the table and fits in POSTGRES_IDENTIFIER_BYTES.
    See unique_name for how names are kept unique.
    """
    used_names: dict[str, int] = {}
    names = []
    for number, field in enumerate(fields):
        name = unique_name(
            field.name.replace('"', "_") or str(number), "", number, used_names, POSTGRES_IDENTIFIER_BYTES
        )
        assert name is not None, "each column has its own number, so its name is never taken to be its own"
        names.append(name)
    return names


def sql_value(table: Table, record: Record, field: Field, on_problem: Callable[[Problem], None]) -> str:
    """
    Return the text of `field` as a PostgreSQL literal for its TEXT column, or NULL when the field is empty.
    Single quotes are doubled, which is correct with standard_conforming_strings on.
    PostgreSQL text cannot hold NUL, so each NUL becomes U+FFFD, reported as replaced_nul.
    """
    if not field.text:
        return "NULL"
    text = field.text
    if "\x00" in text:
        on_problem(
            Problem(
                REPLACED_NUL,
                "the value holds NUL characters, which PostgreSQL text cannot hold; they are written as U+FFFD",
                file=BANK_FILE,
                table=table.name,
                record=record.number,
                field=field.definition.name,
            )
        )
        text = text.replace("\x00", "\ufffd")
    return "'" + text.replace("'", "''") + "'"


class SqlWriter:
    """Writes the PostgreSQL export to `stream`, starting with SET standard_conforming_strings = on."""

    def __init__(self, stream: TextIO, on_problem: Callable[[Problem], None]) -> None:
        self._stream = stream
        self._on_problem = on_problem
        self._table_names: dict[str, int] = {}
        self._current: str | None = None
        stream.write("SET standard_conforming_strings = on;\n")

    def table(self, table: Table) -> None:
        self._current = unique_sql_table_name(table, self._table_names)
        if self._current is None:
            self._on_problem(
                Problem(
                    DUPLICATE_TABLE,
                    "its SQL table name and table id are those of a table already written, so it is skipped",
                    file=STRU_FILE,
                    table=table.name,
                )
            )
            return
        columns = ",\n".join(f'    "{column}" TEXT' for column in unique_sql_column_names(table.fields))
        self._stream.write(f'\nCREATE TABLE "{self._current}" (\n{columns}\n);\n')

    def record(self, table: Table, record: Record) -> None:
        if self._current is None:
            return
        values = ", ".join(sql_value(table, record, field, self._on_problem) for field in record.fields)
        self._stream.write(f'INSERT INTO "{self._current}" VALUES ({values});\n')

    def diagnostic(self, problem: Problem) -> None:
        """SQL output holds no diagnostics; they are on stderr."""

    def finish(self) -> None:
        self._stream.flush()

    def close(self) -> None:
        """The stream belongs to the export, which closes it."""
```

- [ ] **Step 4: Add `--postgres`, stream output and the format checks to `_cli/export.py`**

Add the imports `import sys` and `from typing import TextIO`, and `from .sql_out import SqlWriter`.

In `add_parser`, after the `--csv` argument:

```python
output_format.add_argument(
    "--postgres", action="store_true", help="write PostgreSQL CREATE TABLE and INSERT statements"
)
```

Add after `create_directory`:

```python
def open_stream(target: Path | None, parser: argparse.ArgumentParser, stack: ExitStack) -> TextIO:
    """
    The text stream the export writes to: the new file `target`, or stdout, set to UTF-8, when there is no target.

    Unencodable characters are written as backslash escapes. A file that appeared since the check is a usage error.
    """
    if target is None:
        if isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
        return sys.stdout
    try:
        stream = open(target, "x", encoding="utf-8", errors="backslashreplace", newline="\n")
    except FileExistsError:
        exists_error(parser, target)
    return stack.enter_context(stream)


def check_format_options(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """Refuse the options that only --csv reads when another format is chosen, so nobody believes they applied."""
    if args.csv:
        return
    if args.no_files:
        parser.error("--no-files applies only to --csv, the one format that writes the stored files")
    if args.delimiter is not None:
        parser.error("--delimiter applies only to --csv")
```

In `run_export`, call `check_format_options(args, parser)` as its first line.

Replace `make_writer` and the line in `export` that calls it:

```python
def make_writer(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    bank: Bank,
    target: Path | None,
    problems: Problems,
    stack: ExitStack,
) -> tuple[Writer, Path | None]:
    """Create the output of the chosen format, returning its writer and the path created, None for stdout."""
    if args.csv:
        assert target is not None, "--csv always has a target"
        create_directory(target, parser)
        writer = CsvWriter(target, bank, problems.problem, delimiter=args.delimiter or ",", files=not args.no_files)
        return writer, target
    stream = open_stream(target, parser, stack)
    return SqlWriter(stream, problems.problem), target
```

```python
            writer, created = make_writer(args, parser, bank, target, problems, stack)
```

- [ ] **Step 5: Run the export tests**

Run: `uv run pytest -q tests/test_cli_export.py` — Expected: all pass.

- [ ] **Step 6: Run every check**

Run: `uv run ruff format && uv run ruff check && uv run ty check && uv run pytest -q` — Expected: all clean, and
`git diff master -- tests/golden` empty.

- [ ] **Step 7: Commit**

```bash
git add src/cronos_extract/_cli tests/test_cli_export.py
git commit -m "Add the PostgreSQL export" -m "sql_out.py writes the SQL that postgres.j2 wrote, starting with SET standard_conforming_strings = on and without stray blank lines or trailing spaces. A NUL in a value becomes U+FFFD and is reported as replaced_nul. The export writes to stdout as UTF-8 or to the file -o names, which must not exist, and refuses --no-files and --delimiter with a format other than --csv.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The JSON Lines writer

**Files:**
- Create: `src/cronos_extract/_cli/jsonl_out.py`
- Modify: `src/cronos_extract/_cli/export.py`
- Test: `tests/test_cli_export.py`

**Interfaces:**
- Consumes: Task 4's `open_stream`, `make_writer`; Task 2's `Problem`; the API's `FieldValue`, `FileReference`.
- Produces: `jsonl_out.json_value(value: FieldValue) -> object`, `jsonl_out.JsonlWriter(stream: TextIO)`, a `Writer`.

Line shapes (D3, D4), one JSON object per line, `ensure_ascii=False`, `\n`-terminated, keys in this order:

- `{"type": "table", "table": NAME, "table_id": ID, "abbreviation": ABBR, "fields": [{"name": N, "type": T}, …]}`
- `{"type": "record", "table": NAME, "table_id": ID, "record": NUMBER, "fields": [{"name": N, "value": V}, …]}`
- `{"type": "diagnostic", "kind": K, "message": M, "file": F, "table": T, "record": R, "field": F}`, with `null` for
  what does not apply.

- [ ] **Step 1: Write the failing JSON Lines tests**

Append to `tests/test_cli_export.py` (add `import json` to the imports):

```python
def jsonl_lines(output: str) -> list[dict[str, object]]:
    assert output.endswith("\n")
    return [json.loads(line) for line in output.split("\n")[:-1]]


SECTION_2_DIAGNOSTICS = [
    {
        "type": "diagnostic",
        "kind": "unexpected_structure",
        "message": f"{key}: FieldDefinition Section 2 not marked with a 2",
        "file": "CroStru.dat",
        "table": None,
        "record": None,
        "field": None,
    }
    for key in ("Base000", "Base001")
]
TEST_TABLE_LINE = {
    "type": "table",
    "table": "erdgeist",
    "table_id": 1,
    "abbreviation": "ER",
    "fields": [
        {"name": name, "type": field_type}
        for name, field_type in zip(HEADER, [0, 1, 2, 3, 4, 5, 6, 29, 7, 8, 9, 17], strict=True)
    ],
}


def record_line(number: int, values: dict[str, object]) -> dict[str, object]:
    """The JSON Lines record line of the test table's record `number`, whose fields are `values` or null."""
    return {
        "type": "record",
        "table": "erdgeist",
        "table_id": 1,
        "record": number,
        "fields": [{"name": name, "value": str(number) if name == HEADER[0] else values.get(name)} for name in HEADER],
    }


def test_jsonl_writes_the_table_line_for_a_table_without_records(capsys: pytest.CaptureFixture[str]) -> None:
    assert export_to_stdout(TEST_DB, "--jsonl") == 0

    assert jsonl_lines(capsys.readouterr().out) == [*SECTION_2_DIAGNOSTICS, TEST_TABLE_LINE]


def test_jsonl_writes_each_value_as_d4_describes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dbdir = write_database(
        tmp_path / "db",
        [
            table_record({0: b"42", 3: b"1240315", 4: b"0930", 5: file_reference_field("scan", "jpg", 40)}),
            table_record({3: b"850000", 5: file_reference_field("scan", "jpg", "abc")}),
        ],
    )

    assert export_to_stdout(dbdir, "--jsonl") == 0

    assert jsonl_lines(capsys.readouterr().out)[3:] == [
        record_line(
            1,
            {
                "Entry #1": "42",
                "Entry #4": "2024-03-15",
                "Entry #5": "09:30",
                "Entry #6": {"name": "scan", "extension": "jpg", "record": 40},
            },
        ),
        record_line(2, {"Entry #4": "1985-00-00", "Entry #6": {"name": "scan", "extension": "jpg", "record": None}}),
    ]


@pytest.mark.parametrize(
    ("date", "value", "message"),
    [
        (b"\x00" * 6, "", "the value is not a date; it is kept as text"),
        (b"12x", "12x", "the value is not a date; it is kept as text"),
    ],
    ids=["nul-only", "not-a-date"],
)
def test_jsonl_writes_a_record_s_diagnostics_before_it_and_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], date: bytes, value: str, message: str
) -> None:
    dbdir = write_database(tmp_path / "db", [table_record({3: date})])

    assert export_to_stdout(dbdir, "--jsonl") == 0

    captured = capsys.readouterr()
    assert jsonl_lines(captured.out)[3:] == [
        {
            "type": "diagnostic",
            "kind": "invalid_value",
            "message": message,
            "file": "CroBank.dat",
            "table": "erdgeist",
            "record": 1,
            "field": "Entry #4",
        },
        record_line(1, {"Entry #4": value}),
    ]
    assert f'warning: invalid_value: table "erdgeist", record 1, field "Entry #4": {message}' in captured.err


def test_jsonl_is_utf8_text_not_ascii_escapes(capsys: pytest.CaptureFixture[str]) -> None:
    assert export_to_stdout(TEST_DB, "--jsonl") == 0

    assert '"Системный номер"' in capsys.readouterr().out


def test_jsonl_writes_a_repeated_table_once_and_says_so_in_the_stream(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dbdir = database_with_extra_definition_key(
        tmp_path / "db", "Base002", erdgeist_table_definition(), [table_record({0: b"one"})]
    )

    assert export_to_stdout(dbdir, "--jsonl") == 0

    lines = jsonl_lines(capsys.readouterr().out)
    assert [line["type"] for line in lines if line["type"] != "diagnostic"] == ["table", "record"]
    assert {"kind": "duplicate_table", "table": "erdgeist"}.items() <= lines[-1].items()


def test_jsonl_writes_both_tables_whose_names_differ_only_in_case(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    second = renamed_table_definition(erdgeist_table_definition(), name=b"ERDGEIST")
    dbdir = database_with_extra_definition_key(tmp_path / "db", "Base002", second, [table_record({0: b"one"})])

    assert export_to_stdout(dbdir, "--jsonl") == 0

    lines = jsonl_lines(capsys.readouterr().out)
    assert [(line["type"], line["table"]) for line in lines if line["type"] != "diagnostic"] == [
        ("table", "erdgeist"),
        ("record", "erdgeist"),
        ("table", "ERDGEIST"),
        ("record", "ERDGEIST"),
    ]


def test_jsonl_writes_to_the_file_o_names(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "out.jsonl"

    assert export_to_stdout(TEST_DB, "--jsonl", "-o", str(output)) == 0

    assert jsonl_lines(output.read_text(encoding="utf-8")) == [*SECTION_2_DIAGNOSTICS, TEST_TABLE_LINE]
    assert capsys.readouterr().out == ""
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest -q tests/test_cli_export.py -k jsonl` — Expected: exit 2 usage errors
(`unrecognized arguments: --jsonl`) surfacing as `SystemExit: 2`.

- [ ] **Step 3: Write `_cli/jsonl_out.py`**

```python
# ABOUTME: The JSON Lines export: one self-contained JSON object per table, record and diagnostic, in order.
# ABOUTME: Each field carries its value only: a string, null, or an object for a file reference.
import datetime
import json
from typing import TextIO

from .._api.bank import Table
from .._api.values import FieldValue, FileReference, Record
from .report import Problem


def json_value(value: FieldValue) -> object:
    """
    The JSON value of a field whose API value is `value`: null when empty, a date or time in ISO format, an object
    for a file reference, and otherwise the text.
    """
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, datetime.time):
        return value.isoformat(timespec="minutes")
    if isinstance(value, FileReference):
        return {"name": value.name, "extension": value.extension, "record": value.record}
    return value


class JsonlWriter:
    """Writes the JSON Lines export to `stream`: a line per table before its records, per record and per problem."""

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream

    def table(self, table: Table) -> None:
        self._write(
            {
                "type": "table",
                "table": table.name,
                "table_id": table.id,
                "abbreviation": table.abbreviation,
                "fields": [{"name": field.name, "type": field.type} for field in table.fields],
            }
        )

    def record(self, table: Table, record: Record) -> None:
        self._write(
            {
                "type": "record",
                "table": table.name,
                "table_id": table.id,
                "record": record.number,
                "fields": [
                    {"name": field.definition.name, "value": json_value(field.value)} for field in record.fields
                ],
            }
        )

    def diagnostic(self, problem: Problem) -> None:
        self._write(
            {
                "type": "diagnostic",
                "kind": problem.kind,
                "message": problem.message,
                "file": problem.file,
                "table": problem.table,
                "record": problem.record,
                "field": problem.field,
            }
        )

    def finish(self) -> None:
        self._stream.flush()

    def close(self) -> None:
        """The stream belongs to the export, which closes it."""

    def _write(self, line: dict[str, object]) -> None:
        self._stream.write(json.dumps(line, ensure_ascii=False) + "\n")
```

- [ ] **Step 4: Add `--jsonl` to `_cli/export.py`**

Add `from .jsonl_out import JsonlWriter`. In `add_parser`, after `--postgres`:

```python
    output_format.add_argument(
        "--jsonl", action="store_true", help="write JSON Lines: one object per table, record and diagnostic"
    )
```

In `make_writer`, replace its last line with:

```python
    writer: Writer = SqlWriter(stream, problems.problem) if args.postgres else JsonlWriter(stream)
    return writer, target
```

- [ ] **Step 5: Run the export tests**

Run: `uv run pytest -q tests/test_cli_export.py` — Expected: all pass.

- [ ] **Step 6: Run every check**

Run: `uv run ruff format && uv run ruff check && uv run ty check && uv run pytest -q` — Expected: all clean, and
`git diff master -- tests/golden` empty.

- [ ] **Step 7: Commit**

```bash
git add src/cronos_extract/_cli tests/test_cli_export.py
git commit -m "Add the JSON Lines export" -m "Each table, record and diagnostic is one self-contained JSON object. A record line names its table and its fields in definition order, each with its value only: a string, null, or an object for a file reference. A record's diagnostics come before it, and problems found while opening the database come first.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: `inspect`

**Files:**
- Create: `src/cronos_extract/_cli/inspect.py`
- Modify: `src/cronos_extract/crodump.py` (imports the CroSys `destruct` helpers), `src/cronos_extract/Database.py`
  (deletes `strudump`)
- Test: `tests/test_cli_inspect.py`

**Interfaces:**
- Consumes: Task 2's `kod_options`, `selected_kod`, `Subcommands`, `Report`, `Problem`, `Failure`; `kod_coder`
  (`_api/kod.py`); `Database(dbdir, compact, kod, files=())`, `Database.getname(name, ext)`,
  `Database.opendatafile(name, datname, tadname)`, `Database.dump_db_table_defs(args)`, `.dump(args)`,
  `.recdump(args)`, `.decode_db_definition(data)`, `.dump_db_definition(args, d)`, `.missing_stru_message()`,
  `ALL_FILES`, `KOD_HINT` (`Database.py`); `TableDefinition(data).dump(args)`, `describe_error` (`Datamodel.py`);
  `kod_hexdump(kod, args)` (`kodump.py`); `unhex` (`hexdump.py`).
- Produces: `inspect.add_parser(subcommands)`; handlers `run_strudump`, `run_recdump`, `run_crodump`,
  `run_destruct`, `run_kodump`, each `(args, parser) -> int`; `inspect.open_database(args, required:
  Collection[str]) -> Database`; `inspect.destruct_sys_definition(args, data)` and its two helpers, moved from
  `crodump.py`.

Which files each subcommand reads, and so which one failing to open is exit 1 (D11); every other Cro file present is
opened too, and one that cannot be read is a `warning: unreadable_file:` line and left out:

| Subcommand | Reads |
|---|---|
| `strudump` | CroStru |
| `recdump` | the file chosen by `--stru`, `--index`, `--sys`, else CroBank |
| `crodump` | every Cro file present |
| `destruct -t 1` | none required; CroStru is used when present, for keys stored by reference |
| `kodump` | no database |

- [ ] **Step 1: Write the failing inspect tests**

Create `tests/test_cli_inspect.py`:

```python
# ABOUTME: Tests for the inspect subcommands: their output is crodump's, and they open only the files they read.
# ABOUTME: They run inspect on test_data and on crafted or damaged copies, in this process or as a subprocess.
import io
import shutil
from pathlib import Path

import pytest
from cli import run_in_process
from cronos_builder import TEST_DB, write_database

from cronos_extract import NotACronosFile
from cronos_extract._cli import inspect
from cronos_extract._cli.report import Failure
from cronos_extract.Database import KOD_HINT, Database
from cronos_extract.koddecoder import INITIAL_KOD, KODcoding

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
RELATIVE_TEST_DB = "test_data/all_field_types"


def golden_stdout(name: str) -> str:
    return (GOLDEN_DIR / f"{name}.stdout").read_bytes().decode("utf-8")


def run_inspect(*args: str) -> int:
    return run_in_process(inspect.add_parser, ["inspect", *args])


@pytest.mark.parametrize(
    ("args", "golden"),
    [
        (["strudump", "-v", "-a", RELATIVE_TEST_DB], "crodump-strudump"),
        (["crodump", "-v", RELATIVE_TEST_DB], "crodump-crodump"),
        (["recdump", RELATIVE_TEST_DB], "crodump-recdump"),
        (["recdump", "--stats", "--stru", RELATIVE_TEST_DB], "crodump-recdump-stats-stru"),
        (["kodump", "-s", "1", "-l", "64", f"{RELATIVE_TEST_DB}/CroStru.dat"], "crodump-kodump-shift1"),
    ],
    ids=["strudump", "crodump", "recdump", "recdump-stats-stru", "kodump"],
)
def test_inspect_prints_what_crodump_printed(
    args: list[str], golden: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(REPO_ROOT)

    assert run_inspect(*args) == 0

    assert capsys.readouterr().out == golden_stdout(golden)


@pytest.fixture
def damaged_index_db(tmp_path: Path) -> Path:
    """A copy of TEST_DB whose CroIndex.dat is ten bytes long, too short for a file header."""
    dbdir = tmp_path / "db"
    shutil.copytree(TEST_DB, dbdir)
    (dbdir / "CroIndex.dat").write_bytes(bytes(10))
    return dbdir


def test_a_damaged_file_the_subcommand_does_not_read_is_one_warning(
    damaged_index_db: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(REPO_ROOT)

    assert run_inspect("strudump", "-v", "-a", str(damaged_index_db)) == 0

    captured = capsys.readouterr()
    assert captured.out == golden_stdout("crodump-strudump")
    warnings = [line for line in captured.err.splitlines() if line.startswith("warning: ")]
    assert len(warnings) == 1
    assert warnings[0].startswith("warning: unreadable_file: CroIndex.dat: the file cannot be read and is left out: ")


@pytest.mark.parametrize("args", [["recdump", "--index"], ["crodump"]], ids=["recdump-index", "crodump"])
def test_a_damaged_file_the_subcommand_reads_stops_it(damaged_index_db: Path, args: list[str]) -> None:
    with pytest.raises(NotACronosFile) as failed:
        run_inspect(*args, str(damaged_index_db))

    assert "CroIndex.dat" in str(failed.value)
    assert str(damaged_index_db) in str(failed.value)


def test_strudump_needs_crostru(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [])
    (Path(dbdir) / "CroStru.dat").unlink()
    (Path(dbdir) / "CroStru.tad").unlink()

    with pytest.raises(NotACronosFile) as failed:
        run_inspect("strudump", dbdir)

    assert "CroStru.dat" in str(failed.value)
    assert dbdir in str(failed.value)


def test_strudump_of_an_undecodable_definition_fails_with_the_kod_hint(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(Failure) as failed:
        run_inspect("strudump", "--nokod", str(TEST_DB))

    assert str(failed.value) == f"the database definition is cut off after 0 keys\n{KOD_HINT}"
    assert "WARN: expected dbinfo to start with 0x03" in capsys.readouterr().err


def definition_hex() -> str:
    with Database(str(TEST_DB), False, KODcoding(INITIAL_KOD)) as db:
        record = db.stru.readrec(1)
    return record[1:].hex()


@pytest.mark.parametrize("where", ["argument", "working-directory"])
def test_destruct_type_1_reads_keys_stored_by_reference_from_the_database(
    where: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(definition_hex().encode())))
    if where == "argument":
        args = ["destruct", "-t", "1", str(TEST_DB)]
    else:
        monkeypatch.chdir(TEST_DB)
        args = ["destruct", "-t", "1"]

    assert run_inspect(*args) == 0

    assert 'BankName             - "nowa"' in capsys.readouterr().out


def test_recdump_debug_stops_at_the_last_record(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_inspect("recdump", "--debug", str(TEST_DB)) == 0

    assert "unpack" not in capsys.readouterr().out


def test_kodump_nokod_dumps_the_bytes_undecoded(capsys: pytest.CaptureFixture[str]) -> None:
    datafile = str(TEST_DB / "CroStru.dat")

    run_inspect("kodump", "-s", "1", "-l", "16", datafile)
    decoded = capsys.readouterr().out
    run_inspect("kodump", "--nokod", "-s", "1", "-l", "16", datafile)
    long_option = capsys.readouterr().out
    run_inspect("kodump", "-n", "-s", "1", "-l", "16", datafile)

    assert capsys.readouterr().out == long_option
    assert long_option != decoded


@pytest.mark.parametrize(
    "args", [["sysdump", str(TEST_DB)], ["kodump", "--crack", "strucrack"], ["kodump", "--compact"]]
)
def test_options_and_subcommands_inspect_does_not_have_are_usage_errors(args: list[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        run_inspect(*args)

    assert stopped.value.code == 2
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest -q tests/test_cli_inspect.py` — Expected: `ImportError: cannot import name 'inspect'` from
`cronos_extract._cli`.

- [ ] **Step 3: Write `_cli/inspect.py`**

Move `destruct_sys3_def`, `destruct_sys4_def` and `destruct_sys_definition` from `crodump.py` into this module
unchanged, apart from annotations (`rd: ByteReader`, `args: argparse.Namespace`, `data: bytes`, `-> None`), and make
`crodump.py` import them with `from ._cli.inspect import destruct_sys_definition`.

```python
# ABOUTME: The inspect subcommands, strudump, recdump, crodump, destruct and kodump, over the internal readers.
# ABOUTME: They show what the API hides, keep crodump's output, and stop only for a file they read that cannot be read.
import argparse
import sys
from collections.abc import Collection
from typing import cast

from .._api.errors import NotACronosFile
from .._api.kod import kod_coder
from ..Database import ALL_FILES, KOD_HINT, Database
from ..Datafile import Datafile
from ..Datamodel import TableDefinition, describe_error
from ..hexdump import unhex
from ..kodump import kod_hexdump
from ..readers import ByteReader
from .options import Subcommands, kod_options, selected_kod
from .report import Failure, Problem, Report

# The number of records dumped when --maxrecs is not given: all of them.
ALL_RECORDS = 0xFFFFFFFF


# destruct_sys3_def, destruct_sys4_def and destruct_sys_definition, moved from crodump.py, go here.


def add_parser(subcommands: Subcommands) -> None:
    """Add the inspect subcommand and its own subcommands to `subcommands`."""
    inspect_parser = subcommands.add_parser(
        "inspect", help="dump a database's internal structures, for studying the file format"
    )
    commands = inspect_parser.add_subparsers(dest="inspect_command", required=True, metavar="SUBCOMMAND")

    p = commands.add_parser("strudump", parents=[kod_options()], help="dump the database and table definitions")
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--ascdump", "-a", action="store_true")
    p.add_argument("dbdir", type=str)
    p.set_defaults(handler=run_strudump, command_parser=p)

    p = commands.add_parser("recdump", parents=[kod_options()], help="dump the records of one Cro file")
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--ascdump", "-a", action="store_true")
    p.add_argument("--maxrecs", "-m", type=str, help="max nr or recots to output")
    p.add_argument("--find1d", action="store_true", help="Find records with 0x1d in it")
    p.add_argument("--stats", action="store_true", help="calc table stats from the first byte of each record")
    p.add_argument("--index", action="store_true", help="dump CroIndex")
    p.add_argument("--stru", action="store_true", help="dump CroStru")
    p.add_argument("--bank", action="store_true", help="dump CroBank")
    p.add_argument("--sys", action="store_true", help="dump CroSys")
    p.add_argument("--debug", action="store_true", help="stop with the traceback of a record that cannot be read")
    p.add_argument("dbdir", type=str)
    p.set_defaults(handler=run_recdump, command_parser=p)

    p = commands.add_parser("crodump", parents=[kod_options()], help="dump every Cro file byte range by byte range")
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--ascdump", "-a", action="store_true")
    p.add_argument("--maxrecs", "-m", type=str, help="max nr or recots to output")
    p.add_argument("--nodecompress", action="store_false", dest="decompress", default="true")
    p.add_argument("dbdir", type=str)
    p.set_defaults(handler=run_crodump, command_parser=p)

    p = commands.add_parser(
        "destruct", parents=[kod_options(crack=False)], help="decode a definition given as hex on stdin"
    )
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--ascdump", "-a", action="store_true")
    p.add_argument("--type", "-t", type=int, help="what type of record to destruct")
    p.add_argument(
        "dbdir", nargs="?", default=".", help="the database whose CroStru holds keys stored by reference (-t 1)"
    )
    p.set_defaults(handler=run_destruct, command_parser=p)

    p = commands.add_parser(
        "kodump", parents=[kod_options(crack=False, compact=False)], help="KOD-decode and hexdump a file or stdin"
    )
    p.add_argument("--offset", "-o", type=str, default="0")
    p.add_argument("--length", "-l", type=str)
    p.add_argument("--width", "-w", type=str)
    p.add_argument("--endofs", "-e", type=str)
    p.add_argument("--unhex", "-x", action="store_true", help="assume the input contains hex data")
    p.add_argument("--shift", "-s", type=str, help="KOD decode with the specified shift")
    p.add_argument(
        "--increment",
        "-i",
        action="store_true",
        help="assume data is already KOD decoded, but with wrong shift -> dump alternatives.",
    )
    p.add_argument("--ascdump", "-a", action="store_true", help="CP1251 asc dump of the data")
    p.add_argument("--invkod", "-I", action="store_true", help="KOD encode")
    p.add_argument("filename", type=str, nargs="?", help="dump either stdin, or the specified file")
    p.set_defaults(handler=run_kodump, command_parser=p)


def open_component(db: Database, base: str, *, required: bool) -> Datafile | None:
    """
    Cro<base> of `db` as a Datafile, or None when its .dat or its .tad is absent.

    A file that cannot be read raises NotACronosFile naming it when `required`, and otherwise is reported as an
    unreadable_file warning and left out. OSError from listing the directory propagates.
    """
    datname = db.getname(base, "dat")
    tadname = db.getname(base, "tad")
    if not datname or not tadname:
        return None
    try:
        return cast(Datafile, db.opendatafile(base, datname, tadname))
    except Exception as e:
        # Datafile raises OSError, ValueError, struct.error and a bare Exception for a file it cannot read.
        if required:
            raise NotACronosFile(f"Cro{base}.dat in {db.dbdir} cannot be read: {describe_error(e)}") from e
        Report().problem(
            Problem(
                "unreadable_file",
                f"the file cannot be read and is left out: {describe_error(e)}",
                file=f"Cro{base}.dat",
            )
        )
        return None


def open_database(args: argparse.Namespace, required: Collection[str]) -> Database:
    """
    The database in args.dbdir with the KOD the options select, its Cro files opened through open_component.

    The files named in `required` stop the command when they cannot be read.
    """
    db = Database(args.dbdir, args.compact, kod_coder(selected_kod(args)), files=())
    try:
        for base in ALL_FILES:
            # Database keeps each file in the attribute named after it: stru, index, bank and sys.
            setattr(db, base.lower(), open_component(db, base, required=base in required))
    except BaseException:
        db.close()
        raise
    return db


def max_records(text: str | None) -> int:
    """The number of records --maxrecs asks for, in any base Python reads, or all of them."""
    return int(text, 0) if text else ALL_RECORDS


def run_strudump(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Print the database definition and every table definition in CroStru."""
    with open_database(args, required=("Stru",)) as db:
        if db.stru is None:
            raise NotACronosFile(db.missing_stru_message())
        try:
            db.dump_db_table_defs(args)
        except ValueError as e:
            raise Failure(f"{e}\n{KOD_HINT}") from e
    return 0


def recdump_file(args: argparse.Namespace) -> str:
    """The Cro file recdump dumps, as Database.recdump chooses it."""
    if args.index:
        return "Index"
    if args.sys:
        return "Sys"
    if args.stru:
        return "Stru"
    return "Bank"


def run_recdump(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Hexdump the records of one Cro file."""
    args.maxrecs = max_records(args.maxrecs)
    with open_database(args, required=(recdump_file(args),)) as db:
        db.recdump(args)
    return 0


def run_crodump(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Dump every Cro file present, byte range by byte range."""
    args.maxrecs = max_records(args.maxrecs)
    with open_database(args, required=ALL_FILES) as db:
        db.dump(args)
    return 0


def run_destruct(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Decode the definition given as hex on stdin: a database (-t 1), table (-t 2) or CroSys (-t 3) definition."""
    data = unhex(sys.stdin.buffer.read())
    if args.type == 1:
        with open_database(args, required=()) as db:
            db.dump_db_definition(args, db.decode_db_definition(data))
    elif args.type == 2:
        TableDefinition(data).dump(args)
    elif args.type == 3:
        destruct_sys_definition(args, data)
    return 0


def run_kodump(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """KOD-decode and hexdump a byte range of a file, or of stdin."""
    kod_hexdump(kod_coder(selected_kod(args)), args)
    return 0
```

`args.dbdir` does not exist for `kodump`; `selected_kod` reads it only for `--crack`, which `kodump` does not have.

- [ ] **Step 4: Delete `Database.strudump`**

Delete the `strudump` method from `src/cronos_extract/Database.py` (D11): `inspect strudump` maps its errors itself.
Make `crodump.py`'s `stru_dump` do what the method did, so `crodump strudump` and its golden file are unchanged until
Task 11:

```python
def stru_dump(kod, args):
    """handle 'strudump' subcommand"""
    db = Database(args.dbdir, args.compact, kod)
    if not db.stru:
        sys.exit(f"Error: {db.missing_stru_message()}")
    try:
        db.dump_db_table_defs(args)
    except ValueError as e:
        sys.exit(f"Error: {e}\n{KOD_HINT}")
```

and add `KOD_HINT` to `crodump.py`'s import from `.Database`.

- [ ] **Step 5: Run the inspect tests and the old command tests**

Run: `uv run pytest -q tests/test_cli_inspect.py tests/test_crodump.py tests/test_cli_characterisation.py`
Expected: all pass.

- [ ] **Step 6: Run every check**

Run: `uv run ruff format && uv run ruff check && uv run ty check && uv run pytest -q` — Expected: all clean, and
`git diff master -- tests/golden` empty.

- [ ] **Step 7: Commit**

```bash
git add src/cronos_extract/_cli/inspect.py src/cronos_extract/crodump.py src/cronos_extract/Database.py tests/test_cli_inspect.py
git commit -m "Add the inspect subcommands" -m "strudump, recdump, crodump, destruct and kodump keep crodump's options and stdout. Each opens the Cro files itself: a file the subcommand reads that cannot be read stops it with NotACronosFile, and any other is one unreadable_file warning. destruct takes an optional database for keys stored by reference; recdump takes --debug. Database.strudump, which called sys.exit, is removed.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: `crack`

**Files:**
- Create: `src/cronos_extract/_cli/crack.py`
- Modify: `src/cronos_extract/crodump.py` (imports the parsing helpers and `CrackInputError`)
- Test: `tests/test_cli_crack.py`

**Interfaces:**
- Consumes: `_api/crack.py`'s `readable_records(datafile, limit=None)` (yields 1-based `(recno, data)`),
  `stru_xref`, `bank_and_index_xref`, `kod_from_xref`, `fill_single_gap`, `kod_is_resolved`; `_api/datafiles.py`'s
  `database_directory`, `list_directory`, `open_datafile(directory, names, base, *, compact, kod, log)`;
  `DiagnosticLog(on_diagnostic)`; Task 2's `Report`, `Subcommands`; `koddecoder.new(kod, confidence)`,
  `match_with_mismatches`; `hexdump.as1251`, `asambigoushex`, `asasc`, `tohex`, `unhex`.
- Produces:
  - `crack.add_parser(subcommands)`; `crack.run_strucrack(args, parser) -> int`, `crack.run_dbcrack(args, parser)
    -> int`.
  - `crack.raw_datafile(dbdir: str, base: str) -> AbstractContextManager[Datafile]` — Cro<base> opened without KOD
    decoding, its warnings reported on stderr.
  - `crack.derive_kod_from_stru(table: Datafile, args) -> list[int] | None`,
    `crack.derive_kod_from_bank_and_index(bank: Datafile, index: Datafile, args) -> list[int] | None`.
  - `crack.CrackInputError`, `crack.parse_fix`, `crack.parse_text`, `crack.positive_int`, `crack.color_code`,
    `crack.FIX_FORMAT`, `crack.TEXT_FORMAT` (moved from `crodump.py`).

What goes where (D12 and choice 9):

| Output | Stream | With `--silent` |
|---|---|---|
| "Processing record number …", suggestions, the dump, "Duplicates found" | stdout | not printed |
| the KOD hex when resolved | stdout | printed |
| "Pass the following database key to cronos-extract export --kod …" | stderr | not printed |
| "Automatic cracking failed …", the unresolved block (plain, no colour) | stderr | not printed |
| a file that cannot be opened | `Error:` line on stderr (main, Task 8) | printed |

- [ ] **Step 1: Write the failing crack tests**

Create `tests/test_cli_crack.py`:

```python
# ABOUTME: Tests for the crack subcommands, strucrack and dbcrack, which recover a database's KOD table.
# ABOUTME: They crack encrypted databases from tests/cronos_builder.py whose KOD is known, here or as a subprocess.
import argparse
from pathlib import Path

import pytest
from cli import run_in_process
from cronos_builder import (
    TEST_TABLE_ID,
    UNUSED_TABLE_ID,
    bank_record,
    corrupt_compressed_record,
    crackable_database,
    random_kod,
    write_database,
    write_datafile,
)

from cronos_extract import NotACronosFile
from cronos_extract._cli import crack
from cronos_extract.koddecoder import KODcoding

KOD = random_kod(seed=7)
KOD_LINE = bytes(KOD).hex() + "\n"
PERSON_FIELDS = [b"42", b"Hammersley", b"", b"1240315", b"0930", b"", b"", b"", b"", b"", b""]


@pytest.fixture
def encrypted_db(tmp_path: Path) -> str:
    return crackable_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, PERSON_FIELDS)], KOD)


@pytest.fixture
def uncrackable_db(tmp_path: Path) -> str:
    """A database with too few records for either crack method to resolve every KOD entry."""
    return write_database(
        tmp_path / "db", [bank_record(TEST_TABLE_ID, PERSON_FIELDS)], KOD, index_records=[bytes(12)] * 3
    )


def run_crack(*args: str) -> int:
    return run_in_process(crack.add_parser, ["crack", *args])


def crack_args(*args: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="cronos-extract")
    crack.add_parser(parser.add_subparsers(required=True))
    return parser.parse_args(["crack", *args])


def derive_from_stru(dbdir: str, *options: str) -> list[int] | None:
    """Run derive_kod_from_stru on `dbdir` with strucrack's `options`, returning the KOD table or None."""
    args = crack_args("strucrack", *options, dbdir)
    with crack.raw_datafile(dbdir, "Sys" if args.sys else "Stru") as table:
        return crack.derive_kod_from_stru(table, args)


def fix_switch(entry: int, shift: int, plain: int) -> str:
    """Return a -f value that forces KOD[entry] so that `entry` decodes to `plain` at `shift`."""
    return f"{entry:02x}{shift:02x}{plain:02x}"


def test_strucrack_prints_the_dump_and_kod_on_stdout_and_the_key_message_on_stderr(
    encrypted_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_crack("strucrack", "--noninteractive", encrypted_db) == 0

    captured = capsys.readouterr()
    assert "Processing record number" in captured.out
    assert captured.out.endswith(KOD_LINE)
    assert captured.err == (
        "Pass the following database key to cronos-extract export --kod or inspect --kod to decrypt the database:\n"
    )


@pytest.mark.parametrize("method", ["strucrack", "dbcrack"])
def test_silent_prints_only_the_kod(encrypted_db: str, method: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_crack(method, "--silent", encrypted_db) == 0

    assert capsys.readouterr() == (KOD_LINE, "")


def test_an_unresolved_interactive_strucrack_prints_the_estimate_on_stderr_and_exits_0(
    uncrackable_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_crack("strucrack", "--color", uncrackable_db) == 0

    captured = capsys.readouterr()
    assert "Processing record number" in captured.out
    assert "Ambiguous result when cracking." in captured.err
    assert "KOD estimate:" in captured.err
    assert "cronos-extract crack strucrack -f f103=B  -f f10342" in captured.err
    assert "\x1b" not in captured.err
    assert "Ambiguous" not in captured.out


def test_an_unresolved_noninteractive_strucrack_exits_1(
    uncrackable_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_crack("strucrack", "--noninteractive", uncrackable_db) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Automatic cracking failed" in captured.err
    assert "cronos-extract crack strucrack without --noninteractive" in captured.err


def test_an_unresolved_silent_noninteractive_strucrack_prints_nothing(
    uncrackable_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_crack("strucrack", "--noninteractive", "--silent", uncrackable_db) == 1

    assert capsys.readouterr() == ("", "")


def test_an_unresolved_dbcrack_exits_1_with_the_message_on_stderr(
    uncrackable_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_crack("dbcrack", uncrackable_db) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Ambiguous result when cracking." in captured.err
    assert "too few CroBank/CroIndex records" in captured.err


def test_strucrack_reads_only_crostru(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dbdir = tmp_path / "db"
    write_datafile(dbdir, "Stru", [bytes(256)] * 8, KOD)
    (dbdir / "CroIndex.dat").write_bytes(bytes(10))
    (dbdir / "CroIndex.tad").write_bytes(bytes(8))

    assert run_crack("strucrack", "--silent", str(dbdir)) == 0

    assert capsys.readouterr().out == KOD_LINE


def test_dbcrack_needs_croindex(tmp_path: Path) -> None:
    write_datafile(tmp_path / "db", "Bank", [bank_record(TEST_TABLE_ID, PERSON_FIELDS)], KOD)

    with pytest.raises(NotACronosFile) as failed:
        run_crack("dbcrack", str(tmp_path / "db"))

    assert "CroIndex" in str(failed.value)


def test_strucrack_sys_needs_crosys(encrypted_db: str) -> None:
    with pytest.raises(NotACronosFile) as failed:
        run_crack("strucrack", "--sys", encrypted_db)

    assert "CroSys" in str(failed.value)


def test_the_interactive_dump_skips_a_record_it_cannot_read(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    zero_byte_records = [bytes([UNUSED_TABLE_ID]) + bytes(11)] * 300
    looks_compressed = KODcoding(KOD).decode(4 + 8 + 1, corrupt_compressed_record())
    dbdir = write_database(
        tmp_path / "db",
        [bank_record(TEST_TABLE_ID, PERSON_FIELDS), *zero_byte_records],
        KOD,
        extra_stru_records=[*[bytes(256)] * 8, looks_compressed],
        index_records=zero_byte_records,
    )

    assert run_crack("strucrack", dbdir) == 0

    captured = capsys.readouterr()
    assert "Processing record number" in captured.out
    assert captured.out.endswith(KOD_LINE)


def test_text_that_does_not_fit_the_database_raises_crack_input_error(tmp_path: Path) -> None:
    write_datafile(tmp_path / "db", "Stru", [bytes(256)] * 8, KOD)

    with pytest.raises(crack.CrackInputError) as failed:
        derive_from_stru(str(tmp_path / "db"), "--text=99:0:0:a")

    assert "record 99 doesn't exist" in str(failed.value)


def test_a_fix_that_cannot_be_parsed_is_a_usage_error(encrypted_db: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        run_crack("strucrack", "-f", "0000zz", encrypted_db)

    assert stopped.value.code == 2
    assert "Non-hexadecimal digit" in capsys.readouterr().err
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest -q tests/test_cli_crack.py` — Expected: `ImportError: cannot import name 'crack'` from
`cronos_extract._cli`.

- [ ] **Step 3: Write `_cli/crack.py`**

Move `color_code`, `FIX_FORMAT`, `parse_fix`, `positive_int`, `TEXT_FORMAT`, `parse_text` and `CrackInputError` from
`crodump.py` into this module unchanged apart from annotations, and make `crodump.py` import them from
`._cli.crack`. Annotations: `color_code(c: str, confidence: int, forced: bool, force: bool) -> str`,
`parse_fix(value: str) -> tuple[int, int, int]`, `positive_int(value: str) -> int`,
`parse_text(value: str) -> tuple[int, int, bytes]`.

```python
# ABOUTME: The crack subcommands: strucrack and dbcrack recover a database's KOD table from its encrypted records.
# ABOUTME: stdout holds the dump and the KOD; messages go to stderr. Each opens only the files its method reads.
import argparse
import sys
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager

from .. import koddecoder
from .._api.crack import (
    bank_and_index_xref,
    fill_single_gap,
    kod_from_xref,
    kod_is_resolved,
    readable_records,
    stru_xref,
)
from .._api.datafiles import database_directory, list_directory, open_datafile
from .._api.diagnostics import DiagnosticLog
from ..Datafile import Datafile
from ..hexdump import as1251, asambigoushex, asasc, tohex, unhex
from ..koddecoder import match_with_mismatches
from .options import Subcommands
from .report import Report

# color_code, FIX_FORMAT, parse_fix, positive_int, TEXT_FORMAT, parse_text and CrackInputError, moved from
# crodump.py, go here.

KEY_MESSAGE = "Pass the following database key to cronos-extract export --kod or inspect --kod to decrypt the database:"


def add_parser(subcommands: Subcommands) -> None:
    """Add the crack subcommand and its two methods to `subcommands`."""
    crack_parser = subcommands.add_parser(
        "crack", help="recover the KOD table of a database encrypted with its own, without its password"
    )
    methods = crack_parser.add_subparsers(dest="crack_method", required=True, metavar="METHOD")

    p = methods.add_parser(
        "strucrack",
        help="recover the KOD from CroStru, showing the records so that unresolved entries can be fixed by hand",
    )
    p.add_argument("--sys", action="store_true", help="Use CroSys for cracking")
    p.add_argument("--silent", action="store_true", help="print only the KOD, without the dump or messages")
    p.add_argument("--noninteractive", action="store_true", help="Stop if automatic cracking fails")
    p.add_argument("--color", action="store_true", help="force color output even on non-ttys")
    p.add_argument(
        "--fix", "-f", action="append", dest="fix", type=parse_fix, help="force KOD entries after identification"
    )
    p.add_argument(
        "--text",
        "-t",
        action="append",
        dest="text",
        type=parse_text,
        help="add fixed bytes to decoder box by providing whole strings for a position in a record, "
        "format is record:line:offset:plaintext",
    )
    p.add_argument("--width", "-w", type=positive_int, help="max number of decoded characters on screen", default=24)
    p.add_argument("dbdir", type=str)
    p.set_defaults(handler=run_strucrack, command_parser=p)

    p = methods.add_parser("dbcrack", help="recover the KOD from the fourth byte of CroBank and CroIndex records")
    p.add_argument("--silent", action="store_true", help="print only the KOD, without messages")
    p.add_argument("dbdir", type=str)
    p.set_defaults(handler=run_dbcrack, command_parser=p)


@contextmanager
def raw_datafile(dbdir: str, base: str) -> Iterator[Datafile]:
    """
    Cro<base> in `dbdir`, opened without KOD decoding and reading its index from disk, with its warnings on stderr.

    Raises NotACronosFile or UnsupportedVersion when it cannot be read, and OSError when `dbdir` cannot be listed.
    """
    directory = database_directory(dbdir)
    log = DiagnosticLog(Report().diagnostic)
    datafile, _ = open_datafile(directory, list_directory(directory), base, compact=True, kod=None, log=log)
    try:
        yield datafile
    finally:
        datafile.close()


def run_strucrack(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Recover the KOD from CroStru, or CroSys with --sys. A --noninteractive crack that fails exits 1."""
    with raw_datafile(args.dbdir, "Sys" if args.sys else "Stru") as table:
        kod = derive_kod_from_stru(table, args)
    return 1 if kod is None and args.noninteractive else 0


def run_dbcrack(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Recover the KOD from CroBank and CroIndex, exiting 1 when it cannot."""
    with ExitStack() as stack:
        bank = stack.enter_context(raw_datafile(args.dbdir, "Bank"))
        index = stack.enter_context(raw_datafile(args.dbdir, "Index"))
        kod = derive_kod_from_bank_and_index(bank, index, args)
    return 0 if kod is not None else 1
```

Then `derive_kod_from_stru(table: Datafile, args: argparse.Namespace) -> list[int] | None`: copy
`crodump.derive_kod_from_stru`'s body from `xref = stru_xref(table)` to the end, with exactly these changes:

1. Its docstring: "Derive the KOD table from the encrypted records of `table`, CroStru or CroSys, as strucrack's help
   describes. Prints the record dump for finding known text in it, and the KOD when it is resolved; --silent prints
   only the KOD. Returns None when entries stay unresolved. Raises CrackInputError for a --text that does not fit
   `table`."
2. The "no CroSys.dat / no CroStru.dat file found" branch at the top goes; `raw_datafile` raised already.
3. The noninteractive failure message ends `Run cronos-extract crack strucrack without --noninteractive to resolve
   them.` and stays on stderr.
4. The dump loop reads through `readable_records`, which yields 1-based record numbers where `enumrecords`' index was
   0-based:

```python
    w = args.width
    records = () if args.silent else readable_records(table)
    for recno, data in records:
        if not data:
            continue
        i = recno - 1
```

   The rest of the loop body is unchanged.
5. The unresolved block is replaced by a call, `print_unresolved(KOD, KOD_CONFIDENCE, unset_count)`, under
   `if not args.silent:`, followed by `return None`.
6. The end becomes:

```python
    if not args.silent:
        print(KEY_MESSAGE, file=sys.stderr)
    print(tohex(bytes(KOD)))

    return KOD
```

Add `print_unresolved` above it:

```python
def print_unresolved(kod: list[int], confidence: list[int], unset_count: int) -> None:
    """
    Print on stderr which KOD entries are unresolved, the KOD estimate and how to fix entries by hand.

    It is printed without colour: the stderr escaping would show colour codes as text.
    """
    kod_set = {value for entry, value in enumerate(kod) if confidence[entry] > 0}
    unset_entries = ", ".join(f"{entry:02x}" for entry in range(256) if confidence[entry] <= 0)
    unused_values = ", ".join(f"{value:02x}" for value in sorted(set(range(256)).difference(kod_set)))
    lines = [
        f"\nAmbiguous result when cracking. {unset_count:d} entries unsolved. Missing mappings:",
        f"[{unset_entries}] => [{unused_values}]\n",
    ]
    if unset_count == 0:
        lines.append("The forced KOD entries map several entries to the same value, see the duplicates above.\n")
    lines += [
        "KOD estimate:",
        "".join(f"{value:02x}" if confidence[entry] > 0 else "??" for entry, value in enumerate(kod)),
        "\nIf you can provide clues for unresolved KOD entries by looking at the output, pass them via",
        "cronos-extract crack strucrack -f f103=B  -f f10342",
    ]
    print("\n".join(lines), file=sys.stderr)
```

And `derive_kod_from_bank_and_index`:

```python
def derive_kod_from_bank_and_index(bank: Datafile, index: Datafile, args: argparse.Namespace) -> list[int] | None:
    """
    Derive the KOD table from the encrypted CroBank and CroIndex records, as dbcrack's help describes.

    Most records of both are compressed and start with a uint16 size, 0x08 and 0x00, so the fourth byte of each
    decodes to zero, which gives the KOD entry for that byte at the record's shift. Prints the KOD when it is
    resolved; returns None, printing why on stderr unless --silent, when it is not.
    """
    KOD, KOD_CONFIDENCE = kod_from_xref(bank_and_index_xref(bank, index))

    # Rows that found no data, or lost their byte to another row, leave entries unresolved.
    unset_count = len([o for o in KOD_CONFIDENCE if o <= 0])
    if not kod_is_resolved(KOD, KOD_CONFIDENCE):
        if not args.silent:
            print(
                f"Ambiguous result when cracking. {unset_count:d} entries unsolved: too few CroBank/CroIndex records",
                file=sys.stderr,
            )
        return None

    print(tohex(bytes(KOD)))
    return KOD
```

- [ ] **Step 4: Run the crack tests and the old ones**

Run: `uv run pytest -q tests/test_cli_crack.py tests/test_crack.py tests/test_cli_characterisation.py`
Expected: all pass (`crodump`'s own `derive_kod_*` are unchanged, so its golden output is too).

- [ ] **Step 5: Run every check**

Run: `uv run ruff format && uv run ruff check && uv run ty check && uv run pytest -q` — Expected: all clean, and
`git diff master -- tests/golden` empty.

- [ ] **Step 6: Commit**

```bash
git add src/cronos_extract/_cli/crack.py src/cronos_extract/crodump.py tests/test_cli_crack.py
git commit -m "Add the crack subcommands" -m "strucrack opens only CroStru, or CroSys with --sys, and dbcrack only CroBank and CroIndex, so a damaged file the method does not read no longer stops it. stdout holds the dump and the KOD; the key message and every failure message go to stderr, and --silent prints the KOD alone. The interactive dump skips a record it cannot read. dbcrack exits 1 when it cannot recover the KOD, and Ambiguous is spelled correctly.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: The parser, dispatch and exit statuses

**Files:**
- Modify: `src/cronos_extract/cli.py`
- Test: `tests/test_cli.py` (create), `tests/test_cli_export.py`, `tests/test_cli_inspect.py`,
  `tests/test_cli_crack.py`

**Interfaces:**
- Consumes: every `add_parser` and `run_*` of Tasks 3–7; `Failure`, `error_message`, `print_error`,
  `EscapingStream` (Task 2); `CrackInputError` (Task 7); `CronosError`.
- Produces: `cli.build_parser() -> argparse.ArgumentParser` with `survey`, `export`, `inspect` and `crack`;
  `cli.main(argv=None) -> int`; `cli.run(argv) -> int`. Every subparser sets `handler` and `command_parser`.

Exit statuses (D15): 0 finished; 1 for `Failure` (its own status), `CronosError`, `OSError`, `BrokenPipeError`
(no message); 2 for argparse errors and `CrackInputError`; 130 for `KeyboardInterrupt` with no message, or a
`Failure` of status 130 when an export's output exists.

- [ ] **Step 1: Write the failing command tests**

Create `tests/test_cli.py`:

```python
# ABOUTME: Tests for the cronos-extract command as a whole: dispatch, usage errors, exit statuses and stream handling.
# ABOUTME: They run the real command in a subprocess.
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from cli import run_command
from cronos_builder import TEST_DB, TEST_TABLE_FIELD_COUNT, TEST_TABLE_ID, bank_record, write_database


@pytest.mark.parametrize("args", [[], ["inspect"], ["crack"]], ids=["no-subcommand", "inspect", "crack"])
def test_a_missing_subcommand_is_a_usage_error(args: list[str]) -> None:
    result = run_command("cli", args)

    assert result.returncode == 2
    assert "usage: cronos-extract" in result.stderr
    assert "Traceback" not in result.stderr


def test_survey_usage_errors_name_the_survey_subcommand() -> None:
    result = run_command("cli", ["survey"])

    assert result.returncode == 2
    assert result.stderr.startswith("usage: cronos-extract survey")


def test_a_closed_stdout_exits_1_without_a_message() -> None:
    process = subprocess.Popen(
        [sys.executable, "-m", "cronos_extract.cli", "inspect", "kodump", str(TEST_DB / "CroStru.dat")],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None and process.stderr is not None
    process.stdout.readline()
    process.stdout.close()
    stderr = process.stderr.read()
    process.stderr.close()

    assert process.wait(timeout=60) == 1
    assert stderr == b""


def test_an_interrupted_export_says_where_its_output_is(tmp_path: Path) -> None:
    fields = [b"x" * 40] + [b""] * (TEST_TABLE_FIELD_COUNT - 1)
    dbdir = write_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, fields)] * 50_000)
    output = tmp_path / "out.jsonl"
    process = subprocess.Popen(
        [sys.executable, "-m", "cronos_extract.cli", "export", "--jsonl", "-o", str(output), dbdir],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    deadline = time.monotonic() + 60
    while not output.exists() and time.monotonic() < deadline and process.poll() is None:
        time.sleep(0.01)
    process.send_signal(signal.SIGINT)
    _, stderr = process.communicate(timeout=60)

    assert process.returncode == 130
    assert "Traceback" not in stderr
    assert stderr.splitlines()[-1] == f"Error: interrupted; the output written so far is in {output}"


def test_a_path_that_is_not_utf8_is_escaped_in_the_error(tmp_path: Path) -> None:
    dbdir = tmp_path / os.fsdecode(b"db\xff")
    dbdir.mkdir()

    result = run_command("cli", ["export", "--jsonl", str(dbdir)])

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert result.stderr.splitlines()[-1].startswith("Error: ")
    assert "db\\xff" in result.stderr.splitlines()[-1]


def test_export_writes_utf8_whatever_the_locale(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "cronos_extract.cli", "export", "--postgres", str(TEST_DB)],
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONIOENCODING": "latin-1"},
    )

    assert result.returncode == 0
    assert '"Системный номер" TEXT' in result.stdout.decode("utf-8")
```

Append to `tests/test_cli_export.py` (add `from cli import run_command`, `random_kod` from `cronos_builder` and
`from cronos_extract.Database import KOD_HINT` to the imports):

```python
def last_line(stderr: str) -> str:
    return stderr.splitlines()[-1]


def test_export_exits_0_when_it_finishes(tmp_path: Path) -> None:
    result = run_command("cli", ["export", "--csv", "-o", str(tmp_path / "out"), str(TEST_DB)])

    assert result.returncode == 0, result.stderr
    assert last_line(result.stderr) == TEST_DB_SUMMARY


def test_export_of_an_undecodable_definition_exits_1_naming_the_crack_command() -> None:
    result = run_command("cli", ["export", "--postgres", "--nokod", str(TEST_DB)])

    assert result.returncode == 1
    assert result.stdout == ""
    lines = result.stderr.splitlines()
    assert lines[-2] == "1 diagnostic: 1 unexpected_structure"
    assert lines[-1].startswith("Error: the database definition in CroStru.dat of ")
    assert lines[-1].endswith(KOD_HINT)
    assert "cronos_extract.crack_kod" not in result.stderr


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--postgres", "--no-files"], "--no-files applies only to --csv"),
        (["--jsonl", "--delimiter", ";"], "--delimiter applies only to --csv"),
        (["--csv", "--delimiter", "ab"], "cannot be a CSV delimiter"),
        (["--jsonl", "--kod", "00" * 256], "each number from 0 to 255 exactly once"),
        (["--csv", "--jsonl"], "not allowed with"),
        (["--nokod"], "one of the arguments --csv --postgres --jsonl is required"),
    ],
    ids=["no-files", "delimiter-format", "delimiter-length", "kod", "two-formats", "no-format"],
)
def test_export_usage_errors_exit_2(args: list[str], message: str) -> None:
    result = run_command("cli", ["export", *args, str(TEST_DB)])

    assert result.returncode == 2
    assert message in result.stderr
    assert "invalid kod_argument value" not in result.stderr


def test_export_to_an_existing_target_exits_2(tmp_path: Path) -> None:
    (tmp_path / "out").mkdir()

    result = run_command("cli", ["export", "--csv", "-o", str(tmp_path / "out"), str(TEST_DB)])

    assert result.returncode == 2
    assert "already exists" in result.stderr


@pytest.mark.parametrize("problem", ["missing", "file"])
def test_a_database_directory_that_cannot_be_listed_exits_1(tmp_path: Path, problem: str) -> None:
    dbdir = tmp_path / "db"
    if problem == "file":
        dbdir.write_text("not a directory")

    result = run_command("cli", ["export", "--jsonl", str(dbdir)])

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert last_line(result.stderr).startswith("Error: ")


def test_an_output_in_a_missing_directory_exits_1(tmp_path: Path) -> None:
    result = run_command("cli", ["export", "--csv", "-o", str(tmp_path / "missing" / "out"), str(TEST_DB)])

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert last_line(result.stderr).startswith("Error: [Errno 2]")


@pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="needs a POSIX user that permissions apply to")
def test_an_output_in_a_directory_that_is_not_writable_exits_1(tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        result = run_command("cli", ["export", "--csv", "-o", str(locked / "out"), str(TEST_DB)])
    finally:
        locked.chmod(0o700)

    assert result.returncode == 1
    assert last_line(result.stderr).startswith("Error: [Errno 13]")


def test_a_crack_that_recovers_nothing_exits_1(tmp_path: Path) -> None:
    dbdir = write_database(
        tmp_path / "db", [table_record({0: b"x"})], random_kod(seed=7), index_records=[bytes(12)] * 3
    )

    result = run_command("cli", ["export", "--jsonl", "--crack", "dbcrack", dbdir])

    assert result.returncode == 1
    assert "cronos-extract crack strucrack" in last_line(result.stderr)


def test_strict_exits_1_after_writing_the_output(tmp_path: Path) -> None:
    # Every crafted database reports unexpected_structure for its table definitions (D17), so --strict exits 1.
    outdir = tmp_path / "out"

    result = run_command("cli", ["export", "--csv", "--strict", "-o", str(outdir), str(TEST_DB)])

    assert result.returncode == 1
    assert (outdir / "erdgeist.csv").is_file()
    assert last_line(result.stderr) == TEST_DB_SUMMARY


def test_strict_does_not_lower_a_usage_error(tmp_path: Path) -> None:
    (tmp_path / "out").mkdir()

    result = run_command("cli", ["export", "--csv", "--strict", "-o", str(tmp_path / "out"), str(TEST_DB)])

    assert result.returncode == 2
```

Append to `tests/test_cli_inspect.py` (add `from cli import run_command`):

```python
def test_a_damaged_file_the_subcommand_reads_exits_1_without_a_traceback(damaged_index_db: Path) -> None:
    result = run_command("cli", ["inspect", "recdump", "--index", str(damaged_index_db)])

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert result.stderr.splitlines()[-1].startswith("Error: CroIndex.dat in ")


def test_a_damaged_file_the_subcommand_does_not_read_exits_0(damaged_index_db: Path) -> None:
    result = run_command("cli", ["inspect", "strudump", str(damaged_index_db)])

    assert result.returncode == 0, result.stderr


def test_strudump_of_an_undecodable_definition_exits_1_with_two_lines() -> None:
    result = run_command("cli", ["inspect", "strudump", "--nokod", str(TEST_DB)])

    assert result.returncode == 1
    assert result.stderr.splitlines() == [
        "WARN: expected dbinfo to start with 0x03",
        "Error: the database definition is cut off after 0 keys",
        KOD_HINT,
    ]
```

Append to `tests/test_cli_crack.py` (add `from cli import run_command`):

```python
def test_a_resolved_crack_exits_0_with_only_the_kod_on_stdout(encrypted_db: str) -> None:
    result = run_command("cli", ["crack", "dbcrack", "--silent", encrypted_db])

    assert result.returncode == 0
    assert (result.stdout, result.stderr) == (KOD_LINE, "")


@pytest.mark.parametrize(
    "args",
    [["strucrack", "--noninteractive"], ["dbcrack"], ["dbcrack", "--silent"]],
    ids=["strucrack", "dbcrack", "silent"],
)
def test_a_crack_that_fails_exits_1(uncrackable_db: str, args: list[str]) -> None:
    result = run_command("cli", ["crack", *args, uncrackable_db])

    assert result.returncode == 1
    assert result.stdout == ""


def test_a_crack_missing_its_file_exits_1_with_an_error_line(tmp_path: Path) -> None:
    write_datafile(tmp_path / "db", "Bank", [bank_record(TEST_TABLE_ID, PERSON_FIELDS)], KOD)

    result = run_command("cli", ["crack", "dbcrack", "--silent", str(tmp_path / "db")])

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith("Error: ")
    assert "CroIndex" in result.stderr


@pytest.mark.parametrize(
    "args", [["-f", "0000zz"], ["--text=99:0:0:a"], ["--width", "0"]], ids=["fix", "text", "width"]
)
def test_crack_input_that_does_not_fit_exits_2(encrypted_db: str, args: list[str]) -> None:
    result = run_command("cli", ["crack", "strucrack", *args, encrypted_db])

    assert result.returncode == 2
    assert "Traceback" not in result.stderr
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest -q tests/test_cli.py tests/test_cli_export.py tests/test_cli_inspect.py tests/test_cli_crack.py`
Expected: the subprocess tests fail with exit 2 and `invalid choice: 'export'` (and `'inspect'`, `'crack'`) in
stderr; the in-process tests pass.

- [ ] **Step 3: Rewrite `cli.py`**

Keep `collect_roots`, `warn_unlistable` and `run_survey` unchanged. Replace the ABOUTME lines, the imports,
`build_parser` and `main`:

```python
# ABOUTME: The cronos-extract command: the parser for survey, export, inspect and crack, and running one of them.
# ABOUTME: main() is the one place that turns an exception into an Error line and an exit status.
import argparse
import io
import os
import sys
from pathlib import Path

from . import survey
from ._api.errors import CronosError
from ._cli import crack, export, inspect
from ._cli.crack import CrackInputError
from ._cli.options import Subcommands
from ._cli.report import EscapingStream, Failure, error_message, print_error


def add_survey_parser(subcommands: Subcommands) -> None:
    """Add the survey subcommand to `subcommands`."""
    survey_parser = subcommands.add_parser("survey", help="report the CronosPro version of every database found")
    # ... the survey options exactly as build_parser adds them today ...
    survey_parser.set_defaults(handler=run_survey, command_parser=survey_parser)


def build_parser() -> argparse.ArgumentParser:
    """Return the cronos-extract argument parser."""
    parser = argparse.ArgumentParser(prog="cronos-extract", description="Read CronosPro databases.")
    subcommands = parser.add_subparsers(dest="subcommand", required=True)
    add_survey_parser(subcommands)
    export.add_parser(subcommands)
    inspect.add_parser(subcommands)
    crack.add_parser(subcommands)
    return parser
```

(The `# ... survey options ...` line stands for the four `add_argument` calls and the mutually exclusive group that
`build_parser` holds today, moved into `add_survey_parser` unchanged.)

```python
def main(argv: list[str] | None = None) -> int:
    """Run the cronos-extract command, returning its exit status."""
    for stream in (sys.stdout, sys.stderr):
        # A path that is not valid UTF-8 reaches here surrogate-escaped, which printing cannot encode. Showing
        # it as escapes keeps the name visible and lets the rest of the survey finish.
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="backslashreplace")
    stderr = sys.stderr
    # Everything written to stderr is escaped, by the internal readers too, so that a database's names cannot reach
    # the terminal as control sequences.
    sys.stderr = EscapingStream(stderr)
    try:
        return run(argv)
    finally:
        sys.stderr = stderr


def run(argv: list[str] | None) -> int:
    """Parse `argv` and run the subcommand, turning the exception it ends with into an Error line and a status."""
    args = build_parser().parse_args(argv)
    try:
        status = int(args.handler(args, args.command_parser))
        # Flushing here lets a closed stdout show up as BrokenPipeError instead of at exit.
        sys.stdout.flush()
    except BrokenPipeError:
        # Whoever read stdout has gone. Pointing stdout at the null device stops the flush at exit failing again.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        os.close(devnull)
        return 1
    except Failure as e:
        print_error(str(e))
        return e.status
    except CrackInputError as e:
        print_error(str(e))
        return 2
    except (CronosError, OSError) as e:
        print_error(error_message(e))
        return 1
    except KeyboardInterrupt:
        return 130
    return status
```

- [ ] **Step 4: Run the command tests**

Run: `uv run pytest -q tests/test_cli.py tests/test_cli_export.py tests/test_cli_inspect.py tests/test_cli_crack.py tests/test_survey.py`
Expected: all pass. If `test_an_interrupted_export_says_where_its_output_is` finds the export already finished,
raise the record count; do not weaken its assertions.

- [ ] **Step 5: Run every check**

Run: `uv run ruff format && uv run ruff check && uv run ty check && uv run pytest -q` — Expected: all clean, and
`git diff master -- tests/golden` empty.

- [ ] **Step 6: Commit**

```bash
git add src/cronos_extract/cli.py tests/test_cli.py tests/test_cli_export.py tests/test_cli_inspect.py tests/test_cli_crack.py
git commit -m "Dispatch every cronos-extract subcommand and map exit statuses" -m "The parser holds survey, export, inspect and crack, each subparser naming its handler, and a missing subcommand is a usage error. main escapes everything written to stderr and turns the exception a subcommand ends with into one Error line and a status: 1 for a database or file that cannot be read, a failed crack or a closed stdout, 2 for input that does not fit, 130 for Ctrl-C. survey's usage errors name the survey subcommand.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Rename the golden files

**Files:**
- Modify: `tests/golden/` (renames only), `tests/test_cli_characterisation.py`, `tests/test_cli_inspect.py`

This commit only renames, so that Task 10's diff shows only the real changes. The harness keeps running the old
commands under the new names, so every test stays green.

- [ ] **Step 1: Rename with `git mv`**

```bash
cd tests/golden
for suffix in stdout stderr; do
  for name in strudump crodump recdump recdump-stats-stru kodump-shift1; do
    git mv "crodump-$name.$suffix" "inspect-$name.$suffix"
  done
  git mv "crodump-strucrack.$suffix" "crack-strucrack.$suffix"
  git mv "crodump-dbcrack.$suffix" "crack-dbcrack.$suffix"
  git mv "croconvert-postgres.$suffix" "export-postgres.$suffix"
  git mv "croconvert-postgres-nokod.$suffix" "export-postgres-nokod.$suffix"
  git mv "croconvert-csv.$suffix" "export-csv.$suffix"
done
git mv croconvert-csv export-csv
cd ../..
```

`crodump-sysdump.*` and `croconvert-html.*` keep their names; Task 10 deletes them with their cases.

- [ ] **Step 2: Rename the cases, not the commands**

In `tests/test_cli_characterisation.py`, change only the first element of each `CASES` entry that was renamed
(`"crodump-strudump"` → `"inspect-strudump"`, … , `"croconvert-postgres-nokod"` → `"export-postgres-nokod"`), keeping
each entry's module and arguments, and in `test_croconvert_csv_output_matches_golden` change every `croconvert-csv`
golden name to `export-csv`. In `tests/test_cli_inspect.py`, change the five golden names in
`test_inspect_prints_what_crodump_printed`'s parameters and the two `golden_stdout("crodump-strudump")` calls from
`crodump-*` to `inspect-*`.

- [ ] **Step 3: Check that nothing but names changed**

Run: `uv run pytest -q tests/test_cli_characterisation.py tests/test_cli_inspect.py` — Expected: all pass.
Run: `git diff --cached -M --stat master -- tests/golden` after `git add -A tests/golden` — Expected: every entry is
a rename with no line changes.

- [ ] **Step 4: Run every check and commit**

Run: `uv run ruff format && uv run ruff check && uv run ty check && uv run pytest -q` — Expected: all clean.

```bash
git add -A tests/golden tests/test_cli_characterisation.py tests/test_cli_inspect.py
git commit -m "Rename the golden files after the cronos-extract subcommands" -m "crodump-* become inspect-* and crack-*, croconvert-* become export-*. The files and the commands that produce them are unchanged, so the next commit's diff shows only the output that the new commands change.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Regenerate the golden files from `cronos-extract`

**Files:**
- Modify: `tests/test_cli_characterisation.py`, `tests/golden/`, `src/cronos_extract/Database.py` (`KOD_HINT`)
- Delete: `tests/golden/crodump-sysdump.*`, `tests/golden/croconvert-html.*`

- [ ] **Step 1: Point the harness at `cronos-extract`, with an expected status per case**

Replace `tests/test_cli_characterisation.py` with:

```python
# ABOUTME: Characterisation tests that pin the full output of the cronos-extract subcommands.
# ABOUTME: They run the real command as a subprocess against test_data and compare with the golden files.
from collections.abc import Callable
from pathlib import Path

import pytest
from cli import run_command

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_DB = "test_data/all_field_types"

# (golden file name, arguments, exit status)
CASES = [
    ("inspect-strudump", ["inspect", "strudump", "-v", "-a", TEST_DB], 0),
    ("inspect-crodump", ["inspect", "crodump", "-v", TEST_DB], 0),
    ("inspect-recdump", ["inspect", "recdump", TEST_DB], 0),
    ("inspect-recdump-stats-stru", ["inspect", "recdump", "--stats", "--stru", TEST_DB], 0),
    ("inspect-kodump-shift1", ["inspect", "kodump", "-s", "1", "-l", "64", f"{TEST_DB}/CroStru.dat"], 0),
    ("crack-strucrack", ["crack", "strucrack", TEST_DB], 0),
    ("crack-dbcrack", ["crack", "dbcrack", TEST_DB], 1),
    ("export-postgres", ["export", "--postgres", TEST_DB], 0),
    ("export-postgres-nokod", ["export", "--postgres", "--nokod", TEST_DB], 1),
    ("export-jsonl", ["export", "--jsonl", TEST_DB], 0),
]


@pytest.mark.parametrize(("name", "args", "status"), CASES, ids=[case[0] for case in CASES])
def test_command_output_matches_golden(
    name: str, args: list[str], status: int, golden: Callable[[str, str], None]
) -> None:
    result = run_command("cli", args, cwd=REPO_ROOT)

    assert result.returncode == status, result.stderr
    golden(f"{name}.stdout", result.stdout)
    golden(f"{name}.stderr", result.stderr)


def test_export_csv_output_matches_golden(tmp_path: Path, golden: Callable[[str, str], None]) -> None:
    outdir = tmp_path / "out"

    result = run_command("cli", ["export", "--csv", "-o", str(outdir), TEST_DB], cwd=REPO_ROOT)

    assert result.returncode == 0, result.stderr
    golden("export-csv.stdout", result.stdout)
    golden("export-csv.stderr", result.stderr)
    entries = sorted(path.relative_to(outdir).as_posix() for path in outdir.rglob("*"))
    golden("export-csv/_tree.txt", "\n".join(entries) + "\n")
    for path in sorted(outdir.rglob("*.csv")):
        golden(f"export-csv/{path.relative_to(outdir).as_posix()}", path.read_text(encoding="utf-8"))
```

- [ ] **Step 2: Make `KOD_HINT` name the new command**

In `src/cronos_extract/Database.py`:

```python
# Printed after a database definition error: a KOD that isn't the database's own decodes the definition as garbage.
KOD_HINT = (
    "If the KOD used to read this database is not its own, the definition decodes as garbage; "
    "cronos-extract crack strucrack can derive the database's KOD."
)
```

- [ ] **Step 3: Regenerate and delete the goldens of what is gone**

```bash
git rm -q tests/golden/crodump-sysdump.stdout tests/golden/crodump-sysdump.stderr tests/golden/croconvert-html.stdout tests/golden/croconvert-html.stderr
uv run pytest -q tests/test_cli_characterisation.py --update-golden
uv run pytest -q tests/test_cli_characterisation.py
```

Expected: the second run passes.

- [ ] **Step 4: Review the golden diff against D16**

Run: `git diff master -M -- tests/golden` and check each file against this list. Anything else is a bug to fix, not
a golden file to accept:

| Golden file | The only differences |
|---|---|
| `inspect-*.stdout`, `inspect-*.stderr` | none (the renames only) |
| `crack-strucrack.stdout` | loses its last block, from the blank lines before `Ambigous result when cracking.` to `crodump strucrack -f f103=B  -f f10342` |
| `crack-strucrack.stderr` | that block, with `Ambiguous` spelled correctly and `cronos-extract crack strucrack -f f103=B  -f f10342` |
| `crack-dbcrack.stdout` | empty |
| `crack-dbcrack.stderr` | `Ambiguous result when cracking. 255 entries unsolved: too few CroBank/CroIndex records` |
| `export-postgres.stdout` | starts `SET standard_conforming_strings = on;`, then one blank line, then the `CREATE TABLE` with four-space indents and no trailing spaces, and no other blank lines |
| `export-postgres.stderr` | two `warning: unexpected_structure: CroStru.dat: Base000:` / `Base001: FieldDefinition Section 2 not marked with a 2` lines, a blank line, `2 diagnostics: 2 unexpected_structure` |
| `export-postgres-nokod.stdout` | empty, as before |
| `export-postgres-nokod.stderr` | `warning: unexpected_structure: CroStru.dat: expected dbinfo to start with 0x03`, a blank line, `1 diagnostic: 1 unexpected_structure`, and one `Error: the database definition in CroStru.dat of test_data/all_field_types cannot be decoded: …` line ending with the new `KOD_HINT` |
| `export-csv/` | the tree and `erdgeist.csv` unchanged |
| `export-csv.stderr` | the same two warning lines, a blank line, `2 diagnostics: 2 unexpected_structure` |
| `export-jsonl.stdout`, `export-jsonl.stderr` | new: two diagnostic lines and the table line; stderr as `export-csv.stderr` |

Note in the commit body anything in this table that turned out different and why.

- [ ] **Step 5: Run every check and commit**

Run: `uv run ruff format && uv run ruff check && uv run ty check && uv run pytest -q` — Expected: all clean. The old
command tests still pass: they compare with `KOD_HINT` itself.

```bash
git add -A tests/golden tests/test_cli_characterisation.py src/cronos_extract/Database.py
git commit -m "Pin the output of the cronos-extract subcommands" -m "The characterisation tests run cronos-extract instead of crodump and croconvert, with an expected exit status per case. inspect's output is unchanged. crack's failure messages move to stderr and dbcrack's failure exits 1. The PostgreSQL export starts with SET standard_conforming_strings = on and loses its stray blank lines, the CSV tree is unchanged, and stderr holds the new diagnostic lines and summary. The JSON Lines export is new; the HTML export and sysdump go.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Delete `crodump`, `croconvert`, `dumpdbfields` and the templates, moving their tests

**Files:**
- Delete: `src/cronos_extract/crodump.py`, `src/cronos_extract/croconvert.py`, `src/cronos_extract/dumpdbfields.py`,
  `src/cronos_extract/templates/html.j2`, `src/cronos_extract/templates/postgres.j2`, `tests/test_croconvert.py`,
  `tests/test_crodump.py`, `tests/test_crack.py`, `tests/test_dumpdbfields.py`
- Modify: `pyproject.toml`, `uv.lock`, `src/cronos_extract/_api/crack.py` (ABOUTME), `src/cronos_extract/kodump.py`
  (docstring), `tests/test_cli_export.py`, `tests/test_cli_inspect.py`, `tests/test_cli_crack.py`,
  `tests/test_api_crack.py`, `tests/test_datafile.py`, `tests/test_database.py`

No case is dropped because it fails. The cases that go are the HTML ones, with the export they test (D14), and those
that test deleted internals which Tasks 4 and 7 already test in their new form; each is listed below.

- [ ] **Step 1: Move the cases of `tests/test_croconvert.py` into `tests/test_cli_export.py`**

Move each helper the cases use (`unreadable_file_references_database`, `partly_broken_records_database`,
`corrupt_bank_record_database`, `corrupt_compressed_bank_record_database`, `reference_to_a_data_record_database`,
`name_with_undefined_cp1251_byte_database`) unchanged. Translate the arguments with these rules, and keep every
assertion not listed in the table below:

| `croconvert` arguments | `cronos-extract` arguments |
|---|---|
| `["-t", "postgres", DB]` | `["export", "--postgres", DB]` |
| `["--csv", "-o", OUT, DB]` | `["export", "--csv", "-o", OUT, DB]` |
| `["--nokod", "-t", "postgres", DB]` | `["export", "--postgres", "--nokod", DB]` |
| `["--kod", HEX, "-t", "postgres", DB]` | `["export", "--postgres", "--kod", HEX, DB]` |
| `["--csv", "-o", "out", DB]` with `cwd=tmp_path` | `["export", "--csv", "-o", "out", DB]` with `cwd=tmp_path` |

`run_command("croconvert", …)` becomes `run_command("cli", …)`. A database whose definition cannot be decoded now
exits 1 with the `Error:` line last (D15); `returncode != 0` becomes `returncode == 1`.

| Case | What changes |
|---|---|
| `test_table_definition_warnings_go_to_stderr_not_into_the_sql` | stdout holds no `FieldDefinition`; stderr holds `warning: unexpected_structure: CroStru.dat: Base001: FieldDefinition Section 2 not marked with a 2` |
| `test_db_definition_errors_go_to_stderr_not_into_the_sql` | exit 1; stdout `""`; stderr holds `warning: unexpected_structure: CroStru.dat: expected dbinfo to start with 0x03`; its last line starts `Error: the database definition in CroStru.dat of ` |
| `test_html_escapes_a_hostile_file_name_in_the_download_attribute`, `test_html_export_skips_unreadable_file_references`, `test_html_tables_are_well_formed`, the `html` parameter of `test_template_export_keeps_the_decoded_fields_of_broken_records`, `test_a_corrupt_referenced_file_gets_one_accurate_warning` and `test_a_file_reference_to_a_record_of_another_table_is_skipped` | deleted with the HTML export, with `TagCollector`, `start_tags` and `TableShapes` |
| `test_csv_export_skips_unreadable_file_references` | `assert_skipped_file_warnings` becomes the three API diagnostics (choice 10): `warning: unresolved_file_reference: CroBank.dat: a file reference cannot be read: its record number is not a number`, `warning: unresolved_file_reference: CroBank.dat record 2: a file reference cannot be read: CroBank record 2 is deleted or corrupt` and `warning: unresolved_file_reference: CroBank.dat record 99: a file reference cannot be read: CroBank has no record 99`, each once in stderr |
| `test_tad_leftover_warning_goes_to_stderr_not_into_the_sql` | stdout holds no `leftover`; stderr holds `warning: unexpected_structure: CroBank.dat: leftover data in .tad` |
| `test_csv_export_keeps_the_decoded_fields_of_broken_records`, `test_template_export_keeps_the_decoded_fields_of_broken_records` (postgres only, renamed `test_postgres_export_keeps_the_decoded_fields_of_broken_records`) | `assert_partly_broken_record_warnings` checks for a line starting `warning: undecodable_field: table "erdgeist", record 2, field "Entry #2": the field could not be decoded (` and one starting `warning: undecodable_field: table "erdgeist", record 3, field "Entry #6": the field could not be decoded (`, and that the last line contains `2 undecodable_field` |
| `test_croconvert_reports_a_key_referencing_a_deleted_record` → `test_export_reports_a_key_referencing_a_deleted_record` | exit 1; stdout `""`; last stderr line is `f'Error: the database definition in CroStru.dat of {dbdir} cannot be decoded: ValueError: key "DanglingKey" refers to CroStru record 5, which is deleted. {KOD_HINT}'` |
| `test_croconvert_reports_a_record_out_of_range_with_a_wrong_kod` → `test_export_reports_a_record_out_of_range_with_a_wrong_kod` | exit 1; stdout `""`; stderr is exactly two lines: `no diagnostics` and one matching `r'Error: the database definition in CroStru\.dat of .* cannot be decoded: ValueError: key ".*" refers to CroStru record \d+, which CroStru does not hold \(4 records\)\. ' + re.escape(KOD_HINT)` |
| `test_croconvert_reports_a_deleted_definition_record`, `test_croconvert_reports_no_definition_record` → `test_export_reports_…` | exit 1; last stderr line is `f"Error: the database definition in CroStru.dat of {dbdir} cannot be decoded: ValueError: CroStru record 1, which holds the database definition, is deleted. {KOD_HINT}"`, and for no records `…: ValueError: CroStru holds no records, so it has no database definition. {KOD_HINT}` |
| `test_croconvert_stops_with_a_clear_message_without_crostru` → `test_export_stops_with_a_clear_message_without_crostru` | exit 1 |
| `test_postgres_output_declares_every_column_text_and_writes_values_as_decoded` | column lines are those starting with four spaces and a double quote (`'    "'`) |
| `test_csv_export_skips_a_corrupt_bank_record` | the warning is a line starting `warning: corrupt_record: CroBank.dat record 2: CroBank record 2 is corrupt and is skipped: ` |
| `test_csv_export_skips_a_corrupt_compressed_bank_record` | the warning is a line starting `warning: corrupt_record: CroBank.dat record 2: CroBank record 2 is corrupt and is skipped: ValueError: corrupt compressed data: ` |
| `test_exports_close_the_database_files` | runs `run_in_process(export.add_parser, …)` for `--csv -o out`, `--postgres` and `--jsonl` (with `monkeypatch.chdir(tmp_path)`) in place of `template_convert` and `csv_output`, then `gc.collect()`; the `Files-Referenced/report.pdf` assertion stays |
| `test_a_corrupt_referenced_file_gets_one_accurate_warning` (csv only) | exactly one stderr line starts `warning: corrupt_record: CroBank.dat record 2: `, and exactly one is `warning: unresolved_file_reference: CroBank.dat record 2: a file reference cannot be read: CroBank record 2 is deleted or corrupt` (choice 10) |
| `test_a_file_reference_to_a_record_of_another_table_is_skipped` (csv only) | exactly one stderr line is `warning: unresolved_file_reference: CroBank.dat record 1: a file reference cannot be read: CroBank record 1 is not a record of the Files table`; `Files-Referenced` exists and is empty |
| `test_sql_column_names_are_unique_and_fit_postgres_identifiers`, `test_sql_table_names_are_unique_and_fit_postgres_identifiers` and `decoded_test_table` | deleted: Task 4's tests of the same names test `sql_out`'s functions, which replace these |
| `test_postgres_output_replaces_nul_characters_and_warns` | the one stderr line with `replaced_nul` is `warning: replaced_nul: table "erdgeist", record 1, field "Entry #2": the value holds NUL characters, which PostgreSQL text cannot hold; they are written as U+FFFD`; the CSV run's stderr holds no `replaced_nul` |
| `test_croconvert_replaces_an_undefined_cp1251_byte_in_a_name` → `test_jsonl_replaces_an_undefined_cp1251_byte_in_a_name` | runs `["export", "--jsonl", dbdir]`; the table line has `"table": "�rdgeist"` and its fields hold `{"name": "�ntry #6", "type": 6}` |

Every other case moves with only the argument translation: `test_postgres_output_is_not_html_escaped`,
`test_csv_export_gives_referenced_files_safe_unique_names`, `test_postgres_output_has_no_insert_for_an_empty_table`,
`test_postgres_output_has_one_insert_per_record`, `test_csv_export_writes_tables_with_the_same_name_to_different_files`,
`test_postgres_output_gives_tables_with_the_same_name_different_names`,
`test_postgres_output_writes_null_for_every_empty_value`, `test_csv_export_round_trips_a_backslash`,
`test_csv_export_shortens_over_long_file_and_table_names`, `test_postgres_output_shortens_a_long_table_name`.
`insert_statements` already exists in `tests/test_cli_export.py` (Task 4).

- [ ] **Step 2: Move the cases of `tests/test_crodump.py` into `tests/test_cli_inspect.py`**

| `crodump` arguments | `cronos-extract` arguments |
|---|---|
| `["--debug", "recdump", DB]` | `["inspect", "recdump", "--debug", DB]` |
| `["destruct", "-t", "1"]` | `["inspect", "destruct", "-t", "1"]` |
| `["strudump", DB]` | `["inspect", "strudump", DB]` |
| `["--nokod", "strudump", DB]` | `["inspect", "strudump", "--nokod", DB]` |
| `["--kod", HEX, "strudump", DB]` | `["inspect", "strudump", "--kod", HEX, DB]` |
| `["crodump", "--ascdump", DB]` | `["inspect", "crodump", "--ascdump", DB]` |

Every case keeps its assertions, with `returncode != 0` becoming `returncode == 1`, except
`test_global_nokod_applies_to_kodump`, which becomes `test_kodump_nokod_and_n_are_the_same_option`: it runs
`["inspect", "kodump", "--nokod", "-s", "1", "-l", "16", FILE]` and `["inspect", "kodump", "-n", …]` and asserts both
exit 0 with the same stdout. The strudump error cases keep their exact stderr lines, since `KOD_HINT` is imported.

- [ ] **Step 3: Move the cases of `tests/test_crack.py` into `tests/test_cli_crack.py`**

`derive_from_stru` and `fix_switch` exist already (Task 7). Add:

```python
def derive_from_bank_and_index(dbdir: str, *options: str) -> list[int] | None:
    """Run derive_kod_from_bank_and_index on `dbdir` with dbcrack's `options`, returning the KOD table or None."""
    args = crack_args("dbcrack", *options, dbdir)
    with crack.raw_datafile(dbdir, "Bank") as bank, crack.raw_datafile(dbdir, "Index") as index:
        return crack.derive_kod_from_bank_and_index(bank, index, args)


def kod_estimate(output: str) -> str:
    """Return the hex KOD estimate that strucrack prints on stderr when entries stay unresolved."""
    lines = output.splitlines()
    return lines[lines.index("KOD estimate:") + 1]
```

and the fixture `db_with_counts_of_255` unchanged. Subprocess cases translate `run_command("crodump", ["strucrack",
…])` to `run_command("cli", ["crack", "strucrack", …])`.

| Case | What changes |
|---|---|
| `test_strucrack_rejects_a_kod_with_duplicate_values` | reads `captured = capsys.readouterr()`; `"Pass the following database key" not in captured.err`; `"entries unsolved" in captured.err` |
| `test_strucrack_does_not_treat_a_count_of_255_as_forced` | `"Ambiguous result when cracking. 1 entries unsolved"` and `"[01] =>"` in `capsys.readouterr().err` |
| `test_strucrack_keeps_entries_that_shift_rows_without_data_do_not_claim`, `test_strucrack_keeps_the_stronger_of_two_shift_rows_claiming_one_entry` | `kod_estimate(capsys.readouterr().err)` |
| `test_strucrack_noninteractive_prints_nothing_when_silent` | `capsys.readouterr() == ("", "")` |
| `test_dbcrack_returns_none_when_the_kod_is_not_a_permutation` | `"entries unsolved" in capsys.readouterr().err` |
| `test_strucrack_prints_nothing_when_silent` → `test_silent_strucrack_prints_only_a_resolved_kod` | `cracked`: `capsys.readouterr() == (KOD_LINE, "")`; `duplicate-fix`: `capsys.readouterr() == ("", "")` |
| `test_strucrack_prints_nothing_about_a_missing_stru_file_when_silent`, `test_dbcrack_prints_nothing_about_a_missing_index_file_when_silent` | become `…_missing_…_file_raises_even_when_silent`: `pytest.raises(NotACronosFile)` around the derive helper, and `capsys.readouterr().out == ""` (choice 7) |
| `test_croconvert_output_holds_no_cracking_dump` → `test_export_output_holds_no_cracking_dump` | `["export", "--postgres", "--crack", "strucrack", DB]` |
| `test_crack_kod_recovers_the_database_kod` | `cronos_extract.crack_kod(encrypted_db, method) == Kod.from_table(KOD)` |
| `test_croconvert_decodes_with_a_cracked_kod` → `test_export_decodes_with_a_cracked_kod` | parametrised over `method` in `("strucrack", "dbcrack")`: `["export", "--postgres", "--crack", method, DB]` |
| `test_crodump_decodes_with_a_cracked_kod` → `test_inspect_decodes_with_a_cracked_kod` | `["inspect", "strudump", "--crack", method, DB]` |
| `test_strucrack_rejects_an_invalid_fix`, `test_strucrack_rejects_text_that_does_not_fit_the_database`, `test_strucrack_rejects_a_width_that_is_not_positive` | `returncode == 2` in place of `!= 0` |
| `test_crodump_crack_flag_needs_a_database_subcommand` → `test_kodump_has_no_crack_option` | `["inspect", "kodump", "--crack", "strucrack"]`: exit 2, no `Traceback` |
| `test_dumpdbfields_decodes_with_a_cracked_kod` → `test_jsonl_export_decodes_with_a_cracked_kod` | `["export", "--jsonl", "--crack", method, DB]`: exit 0, and some record line has a field whose `value` is `"Hammersley"` |
| `test_crodump_strucrack_skips_a_stru_record_it_cannot_read` → `test_noninteractive_strucrack_skips_a_stru_record_it_cannot_read` | runs `["crack", "strucrack", "--noninteractive", "--silent", DB]`: exit 0, stdout `KOD_LINE` |

Every other case moves unchanged: `test_strucrack_colours_only_forced_entries_as_forced`,
`test_strucrack_returns_none_when_entries_stay_unresolved`,
`test_strucrack_noninteractive_stops_with_a_message_when_cracking_fails`, `test_dbcrack_reads_the_last_record_of_each_file`,
`test_strucrack_text_plaintext_may_contain_colons`, `test_strucrack_suggests_switches_only_for_bytes_inside_the_record`,
`test_strucrack_applies_a_fix_given_as_a_character`.

- [ ] **Step 4: Repoint the other tests that use the old commands**

In `tests/test_api_crack.py`, replace `test_crack_kod_agrees_with_crodump`, drop `crodump` from the import, add
`from cli import run_command`, and change the second ABOUTME line to end "and checks the crack command agrees.":

```python
@pytest.mark.parametrize("method", METHODS)
def test_crack_kod_agrees_with_the_crack_command(encrypted_db: str, method: str) -> None:
    options = ["--noninteractive"] if method == "strucrack" else []
    result = run_command("cli", ["crack", method, "--silent", *options, encrypted_db])

    kod = crack_kod(Path(encrypted_db), cast(Any, method))

    assert result.returncode == 0
    assert kod is not None
    assert result.stdout == kod.hex() + "\n"
```

In `tests/test_datafile.py`, rename `test_crodump_reports_a_corrupt_record_and_dumps_the_next` to
`test_inspect_crodump_reports_a_corrupt_record_and_dumps_the_next` and run `run_command("cli", ["inspect",
"crodump", str(tmp_path)])`.

In `tests/test_database.py`, rename `test_croconvert_passes_over_a_fifo_named_like_the_index_instead_of_blocking` to
`test_export_passes_over_a_fifo_named_like_the_index_instead_of_blocking`, run `run_command("cli", ["export",
"--csv", "-o", str(tmp_path / "out"), str(dbdir)], timeout=60)`, and also assert
`"warning: unreadable_file: CroIndex.dat" in result.stderr`.

- [ ] **Step 5: Delete the old commands and their packaging**

```bash
git rm -q src/cronos_extract/crodump.py src/cronos_extract/croconvert.py src/cronos_extract/dumpdbfields.py
git rm -q -r src/cronos_extract/templates
git rm -q tests/test_croconvert.py tests/test_crodump.py tests/test_crack.py tests/test_dumpdbfields.py
```

In `pyproject.toml`, delete the `crodump` and `croconvert` lines under `[project.scripts]` and set
`dependencies = []`. Then run `uv lock` and `uv sync`.

In `src/cronos_extract/_api/crack.py`, change the second ABOUTME line to
`# ABOUTME: crack_kod uses these steps, and so do the cronos-extract crack subcommands.` In
`src/cronos_extract/kodump.py`, change the module docstring to
`This module has the functions for the 'inspect kodump' subcommand of cronos-extract.`

- [ ] **Step 6: Check that nothing names the old commands**

Run: `rg -n 'crodump|croconvert|dumpdbfields|jinja|Jinja' src tests pyproject.toml --glob '!tests/golden/**'`
Expected: only `inspect crodump` subcommand names (`"crodump"` arguments, `run_crodump`, the golden name
`inspect-crodump`, `test_inspect_crodump_…`) and `test_inspect_prints_what_crodump_printed`. Any other hit is a
leftover to fix.

Run: `uv sync --locked` — Expected: exit 0 (CI runs it).

- [ ] **Step 7: Run every check and commit**

Run: `uv run ruff format && uv run ruff check && uv run ty check && uv run pytest -q && uv run pip-audit --skip-editable`
Expected: all clean. The test count is lower only by the cases the Step 1–3 tables delete.

```bash
git add -A src tests pyproject.toml uv.lock
git commit -m "Remove crodump, croconvert, dumpdbfields and the templates" -m "cronos-extract export, inspect and crack replace them. Their tests move to the new commands' test files, keeping their assertions except where the Phase 2 design changes the output; the HTML cases go with the HTML export. The package no longer depends on Jinja2.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: The command over the real databases

**Files:**
- Modify: `tests/test_realdata.py`

**Interfaces:**
- Consumes: `found_databases()`, `bank_is_small(dbdir)`, `named(directory, filename)`, `pytest_generate_tests`
  (which parametrises every test taking `dbdir`), `run_command`.

The realdata tests run only with `-m realdata` and read `local/mash_datasets_with_CroIndex_dat.txt`. Report counts
only; never paste a path or dataset name from them anywhere.

- [ ] **Step 1: Write the tests**

Add `import json`, `import subprocess` and `from cli import run_command` to `tests/test_realdata.py`, and append:

```python
# A command run over one real database is killed after this many seconds.
EXPORT_TIMEOUT = 1800
# The CSV export, which also writes every stored file, runs on this many of the smallest databases.
CSV_DATABASES = 3


def export_command(dbdir: Path, output: Path, *options: str) -> subprocess.CompletedProcess[str]:
    return run_command("cli", ["export", *options, "--compact", "-o", str(output), str(dbdir)], timeout=EXPORT_TIMEOUT)


def finished_or_failed_cleanly(result: subprocess.CompletedProcess[str]) -> bool:
    """Assert that the command exited 0, or 1 with one Error line last; return whether it finished."""
    assert "Traceback" not in result.stderr
    if result.returncode == 0:
        return True
    lines = result.stderr.splitlines()
    assert result.returncode == 1
    assert [line for line in lines if line.startswith("Error: ")] == [lines[-1]]
    return False


def api_record_count(dbdir: Path) -> int:
    """The number of records the API reads from the tables of `dbdir`, counting a repeated table once."""
    with open_or_skip(dbdir, compact=True) as bank:
        written: set[tuple[str, int]] = set()
        count = 0
        for table in bank.tables:
            if (table.name, table.id) not in written:
                written.add((table.name, table.id))
                count += sum(1 for _ in table.records())
        return count


@functools.cache
def smallest_databases() -> set[Path]:
    sized = []
    for surveyed in found_databases():
        tad = named(surveyed.directory, "CroBank.tad")
        if tad is not None:
            sized.append((tad.stat().st_size, surveyed.directory))
    return {directory for _, directory in sorted(sized)[:CSV_DATABASES]}


def test_export_jsonl_holds_every_record_the_api_reads(dbdir: Path, tmp_path: Path) -> None:
    if not bank_is_small(dbdir):
        pytest.skip("CroBank is too large to walk once per table")
    output = tmp_path / "out.jsonl"

    result = export_command(dbdir, output, "--jsonl")

    if finished_or_failed_cleanly(result):
        lines = [json.loads(line) for line in output.read_bytes().decode("utf-8").split("\n")[:-1]]
        assert sum(line["type"] == "record" for line in lines) == api_record_count(dbdir)


def test_export_postgres_writes_one_insert_per_record(dbdir: Path, tmp_path: Path) -> None:
    if not bank_is_small(dbdir):
        pytest.skip("CroBank is too large to walk once per table")
    output = tmp_path / "out.sql"

    result = export_command(dbdir, output, "--postgres")

    if finished_or_failed_cleanly(result):
        sql = output.read_bytes().decode("utf-8")
        assert sum(line.startswith('INSERT INTO "') for line in sql.split("\n")) == api_record_count(dbdir)


def test_export_csv_writes_the_smallest_databases_with_their_files(dbdir: Path, tmp_path: Path) -> None:
    if dbdir not in smallest_databases():
        pytest.skip(f"the CSV export runs on the {CSV_DATABASES} smallest databases")

    result = export_command(dbdir, tmp_path / "out", "--csv")

    finished_or_failed_cleanly(result)
```

A database that `open_or_skip` cannot open is skipped by `api_record_count` only after the command has been checked,
which is what the spec asks for: the command must end cleanly on every database.

- [ ] **Step 2: Run them over the real databases**

Run: `uv run pytest -q -m realdata tests/test_realdata.py -k export -rs > /tmp/t12-realdata.txt 2>&1; echo $?`
Expected: exit 0. Read the file; report only counts (passed, skipped, failed), never a path or a database name. A
failure is a bug in the export: stop and report it with its test id (`dbNN`) and the kind of failure.

- [ ] **Step 3: Run every check and commit**

Run: `uv run ruff format && uv run ruff check && uv run ty check && uv run pytest -q` — Expected: all clean.

```bash
git add tests/test_realdata.py
git commit -m "Run the export over the real databases in the realdata tests" -m "Each listed database is exported as JSON Lines and as PostgreSQL with --compact: the command exits 0, or 1 with one Error line, never with a traceback, and the record count matches the API's. The three smallest are also exported as CSV with their files.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: The README and `CLAUDE.md`

**Files:**
- Modify: `README.md`, `CLAUDE.md`

The README keeps its introduction and its Terminology, License and References sections word for word. Everything
from `# Quick start` to the end of `# Development` is replaced by the sections below, in this order. The Python API
section is today's, moved unchanged.

- [ ] **Step 1: Rewrite the README's command sections**

````markdown
# Quick start

```bash
uv tool install git+https://github.com/hammersleyfutures/cronos-extract
cronos-extract export --csv test_data/all_field_types
```

This creates a `cronos-extract-YYYY-mm-dd-HH-MM-SS-ffffff/` directory holding a CSV file for each table, a
`Files-FL/` directory holding every file stored in the database, whether or not a record still refers to it, and a
`Files-Referenced/` directory holding the files the records refer to, under their own names. `-o DIR` names the
directory instead; it must not exist, because an export never overwrites anything.

If the export stops with an error about the database definition, or its output is unreadable, the database is
probably encrypted with its own KOD; see [Recovering the KOD](#recovering-the-kod-of-an-encrypted-database).


# Exporting

`cronos-extract export` writes every table of a database in one of three formats: `--csv`, `--postgres` or
`--jsonl`. Every problem it meets while reading, such as a corrupt record, is printed on stderr as it happens, one
line each, and the export carries on. The last line of stderr counts them by kind:

```
warning: corrupt_record: CroBank.dat record 88: CroBank record 88 is corrupt and is skipped: EOFError

1 diagnostic: 1 corrupt_record
```

The export exits with status 0 when it finished, whatever it reported; with 1 when the database cannot be read at
all, with one `Error:` line last on stderr; and with 2 for a mistake in the command. `--strict` makes it exit 1 when
anything was reported, after writing the whole export. The databases in `test_data` report that their table
definitions are laid out unexpectedly, so `--strict` exits 1 for them.

Write the PostgreSQL and JSON Lines exports to a file with `-o FILE`, which must not exist, rather than to a
terminal: a database's names and values can hold characters that a terminal interprets. stderr is safe: everything
the command prints there is escaped.

## CSV

`--csv` creates a directory holding `<table name>.csv` for each table, UTF-8 without a byte order mark. The first row
holds the field names, starting with the system number. `--delimiter ';'` changes the delimiter, and `--no-files`
leaves out the two file directories. Names are made safe for Linux, macOS and Windows, unique within the directory,
and at most 255 bytes long.

The cells hold exactly what the database holds, including text that a spreadsheet reads as a formula. Open a CSV
file through the spreadsheet's CSV import, as UTF-8, never by double-clicking it.

## PostgreSQL

`--postgres` writes a `CREATE TABLE` statement per table and an `INSERT` statement per record. Every column is
declared `TEXT`, the system number included, so every record loads even when a value does not match its field type.
Values are written exactly as they are decoded: dates as `YYYY-MM-DD`, times as `HH:MM`, and empty values as `NULL`.
Cast columns in SQL when you need types, for example `"Entry #4"::date`. The output starts with
`SET standard_conforming_strings = on;`, so its string literals load correctly whatever the server's setting.
PostgreSQL text cannot hold a NUL character, so a NUL in a value is written as U+FFFD and reported as `replaced_nul`.
Stored files are not included; use `--csv` for them.

## JSON Lines

`--jsonl` writes one JSON object per line: a `table` line before the table's records, a `record` line per record,
and a `diagnostic` line for each problem, where it happened, so a script can tell which records had problems
without reading stderr.

```json
{"type": "table", "table": "Люди", "table_id": 1, "abbreviation": "ЛЮ", "fields": [{"name": "Системный номер", "type": 0}, {"name": "ФИО", "type": 2}]}
{"type": "record", "table": "Люди", "table_id": 1, "record": 12, "fields": [{"name": "Системный номер", "value": "3"}, {"name": "ФИО", "value": "Иванов"}]}
{"type": "diagnostic", "kind": "invalid_value", "message": "the value is not a date; it is kept as text", "file": "CroBank.dat", "table": "Люди", "record": 13, "field": "Дата"}
```

Each record line names its table and its fields, in the order the table defines them, so it can be read on its own.
A field's `value` is `null` when the field is empty, a date as `"1985-04-02"` (or `"1985-00-00"` when only the year is
stored), a time as `"14:30"`, `{"name": …, "extension": …, "record": …}` for a stored file, and otherwise the text.
Stored files are not included; use `--csv` for them.

```bash
cronos-extract export --jsonl -o people.jsonl test_data/all_field_types
jq -r 'select(.type == "record") | .fields[] | select(.name == "Entry #1") | .value' people.jsonl
```

## Large databases

`--compact` reads the indexes from disk instead of memory. Use it for a very large database, whose CroBank index can
take gigabytes of memory; it is about 15% slower.


# Surveying databases

(today's section, unchanged)


# Inspection

`cronos-extract inspect` shows what the export hides, for studying the file format. Some experience with binary
dumps helps: not all of the format is understood yet.

```bash
cronos-extract inspect strudump -v -a test_data/all_field_types   # the database and table definitions, as text
cronos-extract inspect crodump -v test_data/all_field_types        # every Cro file, byte range by byte range
cronos-extract inspect recdump test_data/all_field_types           # a hexdump of every CroBank record
```

`recdump --stru`, `--index` or `--sys` dumps that file's records instead. `destruct` decodes a definition given as
hex on stdin, and `kodump` KOD-decodes a byte range of any file. Each takes `--help`.


# Recovering the KOD of an encrypted database

CronosPro can protect a database with a password, which encrypts it with its own KOD table in place of the default
one. `cronos-extract crack` recovers that KOD from the encrypted records without the password. Both methods are
statistical and may not find every entry.

`crack dbcrack` reads the fourth byte of the CroBank and CroIndex records, which decodes to zero when a record is
compressed:

```bash
KOD=$(cronos-extract crack dbcrack --silent /path/to/database)
cronos-extract export --csv --kod "$KOD" /path/to/database
```

`crack strucrack` reads CroStru, most of whose bytes are zero. When it cannot resolve every entry, it shows the
records as far as it can decode them, suggests `-f` switches where it recognises known text, and prints the missing
entries and its estimate on stderr. Add the switches, or `--text record:line:offset:plaintext` for text you can read,
and run it again until it prints the KOD:

```bash
cronos-extract crack strucrack /path/to/database
cronos-extract crack strucrack -f f103=B -f f10342 /path/to/database
```

`export --crack dbcrack` or `--crack strucrack` recovers the KOD first and exports with it in one step, and exits 1
when the method cannot.


# Python API

(today's section, unchanged)


# Installing

cronos-extract requires Python 3.12 or later and has no other dependencies.

 * Install the `cronos-extract` command with `uv tool install git+https://github.com/hammersleyfutures/cronos-extract`.
 * Or run it from a clone of this repository with `uv run cronos-extract ...`.


# Development

(today's section, unchanged)
````

The three `(today's section, unchanged)` lines stand for the current text of those sections, copied in, not for
literal text.

- [ ] **Step 2: Update `CLAUDE.md`**

- In **Commands**, replace the `croconvert` and `crodump` lines and the `dumpdbfields` line with:

```bash
uv run cronos-extract export --csv -o out test_data/all_field_types
uv run cronos-extract export --postgres test_data/all_field_types
uv run cronos-extract export --jsonl test_data/all_field_types
uv run cronos-extract inspect strudump -v -a test_data/all_field_types
```

- In **Architecture**, the Public API bullet: replace "never the printing `enumerate_*` generators" with "never the
  printing `enumerate_*` generators, which only the Phase 1 parity tests still call".
- Replace the **Commands** bullet list under Architecture with:
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
- In **KOD cipher**, replace the last paragraph with: "`crack strucrack` and `crack dbcrack` derive a KOD
  statistically and print it; `cronos_extract.crack_kod(path, method)` does the same without printing and returns
  `None` when it can't produce a permutation. `export --crack` and `inspect … --crack` call `crack_kod`." Replace
  "`--kod` has no effect on `test_data/all_field_types`" with the same sentence naming `export --kod`.
- In **Error-handling conventions**, replace the first and last bullets with: "Diagnostics go to **stderr**, escaped,
  one line each, through `_cli/report.py`; `export` writes SQL and JSON Lines to stdout, so a stray `print` corrupts
  the export." and "A database definition that can't be decoded is `DatabaseDefinitionError`: `export` exits 1 with
  one `Error:` line naming `cronos-extract crack strucrack`; `inspect strudump` prints the error and `KOD_HINT`."
- In **Tests**, add after the command-tests bullet: "Before a subcommand is wired into `cli.py`, or to read its output
  in this process, `tests/cli.py::run_in_process(add_parser, args)` parses real arguments and runs the handler."

- [ ] **Step 3: Check the Markdown**

Run: `uv run ruff format --check README.md CLAUDE.md` — Expected: exit 0.
Run: `rg -n 'crodump|croconvert|dumpdbfields|[Jj]inja|--strucrack|--dbcrack|Templates' README.md CLAUDE.md`
Expected: only `inspect crodump` and "the crodump subcommand" mentions.

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "Document the cronos-extract export, inspect and crack subcommands" -m "The README has a section per export format, with the JSON Lines shape and a jq example, the diagnostics and exit statuses, inspection, and KOD recovery. The Templates section and every croconvert and crodump command go. CLAUDE.md describes the new modules.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: The outcome, the roadmap and the open items

**Files:**
- Modify: this plan, `docs/superpowers/specs/2026-09-15-modernisation-roadmap-design.md`

- [ ] **Step 1: Add an Outcome section at the end of this plan**

Record, as facts from the branch: the commits (hash and subject); the number of tests on `master` (collected with
`uv run pytest -q --collect-only` in a scratch worktree, `git worktree add /tmp/t14-master master`) and on the
branch; the realdata result from Task
12 as counts only; every place where the code turned out different from this plan and what was done; and every
finding of the final review with how it was settled.

- [ ] **Step 2: Update the roadmap**

In `docs/superpowers/specs/2026-09-15-modernisation-roadmap-design.md`:

- The status line: Phase 2 is complete, implemented on `phase2-implementation` (the PR number once Ben has approved
  opening it).
- Rename the heading "Command line (Phase 2 builds to this)" to "Command line", and correct the file list's
  `cli.py` and `pyproject.toml` bullets (`cli.py` holds all four subcommands; the `crodump` and `croconvert`
  scripts are gone).
- In "Open items carried forward": mark the two "Phase 2 (designed)" items done, each naming the decision that closed
  it; add the spec's three "Open items this phase records"; and add, for Phase 3, "an `unresolved_file_reference`
  diagnostic names the referenced record and the reason, but not the file name or the record holding the reference,
  which `croconvert` named; the CSV export could add them, or the API could carry the referring record". Keep the
  existing item that `Database.enumerate_*` are used only by the Phase 1 parity tests.

- [ ] **Step 3: Run the checks and commit**

Run: `uv run ruff format --check && uv run pytest -q` — Expected: all clean.

```bash
git add docs/superpowers
git commit -m "Record the Phase 2 outcome and carry its open items forward" -m "The plan's outcome section lists the commits, test counts and the differences from the plan; the roadmap marks Phase 2 complete and adds the items it leaves for Phase 3 and after 1.0.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Then stop and ask Ben before opening the pull request.

## Outcome (2026-09-25)

Tasks 1–13 are implemented on branch `phase2-implementation` in 15 commits after the spec and plan (`a72c10b`..`d3eec7b`), with subagent-driven development: a sonnet implementer per task, a task review after each. The plan above is kept as written; where it and the code differ, the divergences below record what was done. Default suite on the branch: 571 passed, 9 deselected; on `master` (`a72c10b`, collected in a scratch worktree): 423 collected, 6 deselected. `uv run ruff format --check` and `uv run pytest -q` are both clean; `tests/golden` was renamed (Task 9) and regenerated (Task 10) as the plan intends.

**Commits:**

- `0e01def` Plan Phase 2: the cronos-extract command line
- `75e5007` Add the command line's problem reporting and KOD options
- `962bb9b` Add the export walk and the CSV writer
- `6243849` Skip a refused table's records instead of reading them twice
- `97629ef` Add the PostgreSQL export
- `40d2e62` Add the JSON Lines export
- `3b92f19` Add the inspect subcommands
- `1bf525d` Add the crack subcommands
- `b9f7a64` Dispatch every cronos-extract subcommand and map exit statuses
- `31ab087` Rename the golden files after the cronos-extract subcommands
- `d643f45` Pin the output of the cronos-extract subcommands
- `b1bc29d` Remove crodump, croconvert, dumpdbfields and the templates
- `af6fe54` Run the export over the real databases in the realdata tests
- `5594219` Match api_record_count's SQL count to SqlWriter's table skipping
- `d3eec7b` Document the cronos-extract export, inspect and crack subcommands

**Divergences and fixes during execution:**

- Task 2: `options.py`'s KOD narrowing needed `typing.cast(Kod, args.kod)` to satisfy `ty check` — `argparse.Namespace` attributes are `Any`, so `args.kod` narrowed by `is not None` does not narrow to `Kod | None` on its own. The only change from the brief's given code.
- Task 3: `Writer.table()` was changed to return `bool` — whether the writer accepted the table — and `walk()` reads a table's records only when it did, so a table a writer refuses (a colliding safe name or id) does not have its records decoded and its diagnostics reported twice. `SqlWriter` (Task 4) and `JsonlWriter` (Task 5) follow this protocol rather than the plan's `-> None`. Two export tests' expected directory listings were widened to include `Files-Referenced`, which is created for `table_record()`'s empty type-6 field too, per the plan's own choice 5.
- Task 6: a test helper needed `cast(bytes, db.stru.readrec(1))` for `ty check`, since `Database.stru.readrec` is unannotated. No other divergence.
- Task 7: `FIX_FORMAT` and `TEXT_FORMAT` were not imported into `crodump.py`, because it never references them directly — only `parse_fix`/`parse_text`, which live entirely in `_cli/crack.py`, use them — matching global-constraints.md's own list of the five names `crodump.py` imports from `_cli/crack.py`.
- Task 8: no divergence — every exact stderr line, exit status and import matched the existing `_cli` module code on first run.
- Task 9: renamed the golden files; no code divergence.
- Task 10: no divergence from the brief's table. `export-postgres-nokod.stderr`'s `Error:` line embeds the Python exception class name (`cannot be decoded: ValueError: ...`), which the brief's table covers with `…`; flagged for Ben as a possible cleanup, outside this task's scope.
- Task 11: `Database.enumerate_files`, `incomplete_records`, `files_tableid` and `get_record` have no production caller left now that `croconvert` and `dumpdbfields` are gone; `enumerate_records` is called only by the Phase 1 parity tests and `tests/test_cronos_builder.py`. Recorded as dead code, not removed, and carried to the roadmap's Phase 3 open items rather than fixed here.
- Task 12: a fix round matched `api_record_count`'s SQL count to `SqlWriter`'s table-skipping (the SQL export omits a table a writer refuses; the test helper counting expected `INSERT` statements did not).
- Task 13: the README's quick-start example was corrected: `Files-Referenced/` is created at the first record of a table that has a file field, even when that field is empty, not only once a record actually refers to a file — `test_data/all_field_types`'s one table has no records at all.

**Real databases** (Task 12, `uv run pytest -m realdata`, the export run over the listed databases): 51 passed, 39 skipped (including 6 databases over the CroBank size limit that the record tests skip), 0 failed.

**Minor findings deferred during task reviews** (not fixed in this phase; each is either cosmetic or carried to the roadmap's Phase 3 open items): `Report.summary` counts only `KIND_ORDER` kinds with no invariant test that the counts sum to the total; `print_error` has no direct test; `STRU_FILE` is defined in both `export.py` and `csv_out.py`; if `make_writer` raised after `create_directory`, the error would omit the output location (unreachable today); `sql_out.py` writes U+FFFD as a literal character; `open_component`'s broad `except Exception` would also report a programming error as an unreadable file; the SIGINT test in Task 8 depends on timing; `from ._cli import inspect` shadows the stdlib module name inside `cli.py`; `test_strudump_without_the_database_kod_stops_with_a_message` duplicates another test after the Task 11 move; `cast(Any, method)` in one crack test; the INSERT-count heuristic in Task 12's realdata test could be inflated by a value holding a line starting `INSERT INTO "` (not observed in the real run); `finished_or_failed_cleanly` raises `IndexError` rather than an assertion on an unexpected exit/stderr combination.

### Final review

The whole-branch review (Fable) found no Critical issues and two Important ones:

1. A NUL in a table or column name reached a PostgreSQL identifier raw, since `unique_sql_table_name` and
   `unique_sql_column_names` replaced only `"`. Fixed: both also replace NUL with U+FFFD, and `SqlWriter` reports
   each replacement as a `replaced_nul` Problem, with tests in `tests/test_cli_export.py`.
2. `inspect kodump FILE` opened its file with plain `open()`, which hangs forever on a FIFO. Fixed: it now opens
   with `_format/files.py`'s `open_regular_file`, the one way Cro files are opened elsewhere, with a test in
   `tests/test_cli_inspect.py`.

Both are fixed in this commit range, with tests. The README corrections (item 3 of the fix brief): the
quick-start's `Files-Referenced/` wording now matches `csv_out.py`'s rule (created at a table's first record once
it has a file field, even an empty one); the CSV names sentence no longer claims Windows device-name safety that
`safepathname` does not provide; and the Inspection section now says `inspect` prints names and bytes to stdout
unescaped. The tidy-ups (item 4): `STRU_FILE` and `BANK_FILE` are now defined once, in `_cli/report.py`, and
imported elsewhere in `_cli`; `Report.problem` now raises `ValueError` for a kind not in `KIND_ORDER`, and
`Report.summary` is tested to include every kind in `KIND_ORDER`. Also removed, at Ben's request:
`test_strudump_of_an_undecodable_definition_exits_1_with_two_lines`, the duplicate this Outcome's own
deferred-findings list already named, keeping `test_strudump_without_the_database_kod_stops_with_a_message`.

Minors the review found that are not fixed here:

- `--maxrecs junk` traceback in inspect recdump/crodump
- `inspect destruct` without `-t` exits 0 silently
- `destruct -t 1` with a by-reference key and no CroStru is an AttributeError
- `--nodecompress` default is the string "true"
- CsvWriter reads a referenced record before checking it is already written
- D15's wording that BrokenPipeError exits "without a message" while export still prints its summary
- a usage error in D2's race window prints the summary after argparse's usage lines
- `destruct_sys3_def` is a stub

The export of the six largest databases is recorded below.

### The six largest databases

The realdata record tests skip the six databases whose CroBank index is over the test suite's 32 MB limit. Each was
exported separately (2026-09-25) with `export --jsonl --compact`, counting the record lines of the output:

| Id | CroBank index | Exit | Time | Records | stderr summary |
|---|---|---|---|---|---|
| db06 | 126 MB | 0 | 7.0 min | 7,922,153 | no diagnostics |
| db12 | 89 MB | 0 | 3.5 min | 5,624,447 | no diagnostics |
| db13 | 2,052 MB | 1 | under 1 s | 0 | one `Error:` line: the definition does not decode with the default KOD |
| db14 | 110 MB | 0 | 8.3 min | 9,217,777 | 410 `invalid_value` |
| db26 | 179 MB | 0 | 11.4 min | 14,964,416 | no diagnostics |
| db28 | 365 MB | 0 | 19.8 min | 28,191 | 17,542: 244 `undecodable_field`, 17,296 `invalid_value`, 2 `unexpected_structure` |

No run printed a traceback. db13 is one of the databases that Phase 1 found do not open with the default KOD, and it
stops as D15 describes. db28's time against its record count shows the Phase 3 open item on reading CroBank once per
table: its index holds about 22.8 million entries (365 MB at 16 bytes each) for 28,191 exported records, and each
table's walk reads every entry again, whether it is deleted, a stored file or a record of another table.
