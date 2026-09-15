# Phase 0: version survey Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `cronos-extract survey`, which reports the CronosPro version of every database under a directory by reading only file headers, so Ben can survey his own databases and tell us whether v7 support can be confirmed against real files.

**Architecture:** One new internal module parses the 19-byte `.dat` header (`_format/header.py`) and `Datafile` starts using it, so the header is parsed in one place. `survey.py` finds databases and formats the results. `cli.py` is the new `cronos-extract` entry point, with `survey` as its only subcommand for now; Phase 2 adds the rest. `crodump` and `croconvert` keep working unchanged.

**Tech Stack:** Python 3.12+, uv, ruff (line length 120), ty (all rules as errors), pytest (`filterwarnings = error`), argparse, `tests/cronos_builder.py` for real crafted databases.

**Spec:** `docs/superpowers/specs/2026-09-15-modernisation-roadmap-design.md` (sections "Phase 0 design: `cronos-extract survey`" and "Decisions").

## Global Constraints

- Address the user as "Ben". Ben's global rules in `~/.claude/CLAUDE.md` override skills. The repository's own rules are in `CLAUDE.md`.
- Repository `/data/Development/Code/cronodump`, GitHub `hammersleyfutures/cronos-extract` (a fork). Always pass `-R hammersleyfutures/cronos-extract` to `gh pr` commands. Never push to `master`. Never open anything against `alephdata/cronodump`.
- Merge with a merge commit only (`gh pr merge --merge`): `.git-blame-ignore-revs` lists exact commit hashes.
- Every change is test-first: write the test, run it, confirm it fails for the stated reason, write the code, run it green. Real crafted databases (`tests/cronos_builder.py`) and real files only, never mocks.
- One logical change per commit. Subject in imperative mood, ≤ 72 characters. Body says what and why. Every commit message ends with exactly `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` — subagents use this line verbatim, not their own model name.
- Every new code file starts with two comment lines beginning `# ABOUTME: `.
- New code is fully type-annotated. Names and comments describe what code is, never its history. Never delete a comment unless it is false.
- Before every commit, all clean, each checked by exit code: `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check`, `uv run ty check`.
- Bash tool: `set -e` does not stop a multi-line command. Guard commits and pushes with explicit checks, e.g. `fail() { echo "STOPPED: $*"; exit 1; }` and `cmd > out.txt 2>&1 || fail "cmd"`. Never pipe a checked command through `tail`.
- Golden files in `tests/golden/` must not change in this phase. If one does, stop and report.
- The survey reads only the 19 bytes of each `.dat` header: never a `.tad` file, never a record, never file content.
- Plain, factual language in commits and PRs. Avoid: critical, crucial, essential, significant, comprehensive, robust, elegant.
- Scratch files get unique names, prefixed with the task number.

## File Structure

- `src/cronos_extract/_format/__init__.py` — new internal package (Phase 3 fills it).
- `src/cronos_extract/_format/header.py` — `DatHeader` and `read_dat_header`; the only place the `.dat` header is parsed.
- `src/cronos_extract/Datafile.py` — `readdathdr` uses `read_dat_header`.
- `src/cronos_extract/survey.py` — finds databases under a directory and formats the three outputs.
- `src/cronos_extract/cli.py` — the `cronos-extract` entry point and the `survey` subcommand.
- `pyproject.toml` — adds the `cronos-extract` console script.
- `tests/cronos_builder.py` — a helper that writes a `.dat` file with only a header.
- `tests/test_header.py`, `tests/test_survey.py` — new tests.
- `README.md` — a short section on the survey.

---

### Task 1: Parse the .dat header in one place

**Files:**
- Create: `src/cronos_extract/_format/__init__.py`, `src/cronos_extract/_format/header.py`
- Create: `tests/test_header.py`
- Modify: `src/cronos_extract/Datafile.py` (`readdathdr`, around lines 71-100)

**Interfaces:**
- Produces: `cronos_extract._format.header.DatHeader` (frozen dataclass) with `version: bytes`, `unknown: int`, `encoding: int`, `blocksize: int`, and properties `version_text: str`, `generation: str` (`"v3"`, `"v4"`, `"v7"`, `"unknown"`), `use64bit: bool`, `kod_encoded: bool`, `compressed: bool`, `own_kod: bool`; and `read_dat_header(file: BinaryIO, *, where: str) -> DatHeader`, which raises `ValueError` naming `where`.

- [ ] **Step 1: Create the branch**

```bash
cd /data/Development/Code/cronodump
git fetch origin --prune
git switch master && git merge --ff-only origin/master
git switch -c phase0-survey
```

- [ ] **Step 2: Write the failing tests** in `tests/test_header.py`:

```python
# ABOUTME: Tests for cronos_extract._format.header, which parses the 19-byte Cro*.dat file header.
# ABOUTME: Builds headers as raw bytes, including versions this package cannot otherwise produce.
import io
import struct

import pytest

from cronos_extract._format.header import DatHeader, read_dat_header

DAT_HEADER = struct.Struct("<8sH5sHH")


def header_bytes(version: bytes = b"01.04", encoding: int = 1, blocksize: int = 0x40) -> bytes:
    return DAT_HEADER.pack(b"CroFile\x00", 0, version, encoding, blocksize)


def test_read_dat_header_decodes_the_fields() -> None:
    header = read_dat_header(io.BytesIO(header_bytes()), where="CroBank.dat")

    assert header == DatHeader(version=b"01.04", unknown=0, encoding=1, blocksize=0x40)
    assert header.version_text == "01.04"
    assert header.generation == "v3"
    assert header.use64bit is False
    assert header.kod_encoded is True
    assert header.compressed is False
    assert header.own_kod is True


def test_read_dat_header_describes_every_known_generation() -> None:
    generations = {
        b"01.02": ("v3", False),
        b"01.03": ("v3", True),
        b"01.05": ("v3", True),
        b"01.11": ("v4", True),
        b"01.13": ("v4", False),
        b"01.14": ("v4", False),
        b"01.19": ("v7", False),
        b"09.99": ("unknown", False),
    }
    for version, (generation, use64bit) in generations.items():
        header = read_dat_header(io.BytesIO(header_bytes(version=version)), where="CroStru.dat")
        assert (header.generation, header.use64bit) == (generation, use64bit), version


def test_read_dat_header_reports_a_compressed_file() -> None:
    header = read_dat_header(io.BytesIO(header_bytes(encoding=3)), where="CroBank.dat")

    assert (header.kod_encoded, header.compressed) == (True, True)


def test_read_dat_header_rejects_another_file_format() -> None:
    with pytest.raises(ValueError, match=r"CroStru\.dat is not a Cronos file: unknown magic b'NotACron'"):
        read_dat_header(io.BytesIO(b"NotACronosFile" + bytes(20)), where="CroStru.dat")


def test_read_dat_header_rejects_a_file_shorter_than_the_header() -> None:
    with pytest.raises(ValueError, match=r"CroStru\.dat is shorter than its 19-byte header"):
        read_dat_header(io.BytesIO(b"CroFile\x00" + bytes(5)), where="CroStru.dat")
```

- [ ] **Step 3: Run them and confirm they fail**

Run: `uv run pytest -q tests/test_header.py`
Expected: FAIL, collection error `ModuleNotFoundError: No module named 'cronos_extract._format'`.

- [ ] **Step 4: Write the module.** `src/cronos_extract/_format/__init__.py`:

```python
# ABOUTME: Internal package holding the CronosPro file format readers.
# ABOUTME: Nothing here is public API; use the cronos_extract package's own names.
```

`src/cronos_extract/_format/header.py`:

```python
# ABOUTME: Parses the 19-byte header that starts every Cro*.dat file.
# ABOUTME: Reports the format version, its generation and the encoding flags.
import struct
from dataclasses import dataclass
from typing import BinaryIO

DAT_HEADER = struct.Struct("<8sH5sHH")
MAGIC = b"CroFile\x00"
# Versions with 64-bit file offsets in their .tad entries.
VERSIONS_64BIT = (b"01.03", b"01.05", b"01.11")
# Versions whose records are encoded with the database's own KOD table instead of the default one.
VERSIONS_OWN_KOD = (b"01.04", b"01.05")
V3_VERSIONS = (b"01.02", b"01.03", b"01.04", b"01.05")
V4_VERSIONS = (b"01.11", b"01.13", b"01.14")
V7_VERSIONS = (b"01.19",)


@dataclass(frozen=True)
class DatHeader:
    """The fields of a Cro*.dat file header."""

    version: bytes
    unknown: int
    encoding: int
    blocksize: int

    @property
    def version_text(self) -> str:
        """The version as text, such as "01.19", with undecodable bytes replaced."""
        return self.version.decode("ascii", "replace")

    @property
    def generation(self) -> str:
        """The CronosPro generation of this version: "v3", "v4", "v7", or "unknown"."""
        if self.version in V3_VERSIONS:
            return "v3"
        if self.version in V4_VERSIONS:
            return "v4"
        if self.version in V7_VERSIONS:
            return "v7"
        return "unknown"

    @property
    def use64bit(self) -> bool:
        """Whether the .tad entries hold 64-bit file offsets."""
        return self.version in VERSIONS_64BIT

    @property
    def kod_encoded(self) -> bool:
        """Whether the records are KOD encoded (encoding bit 0)."""
        return bool(self.encoding & 1)

    @property
    def compressed(self) -> bool:
        """Whether the records can be compressed (encoding bit 1)."""
        return bool(self.encoding & 2)

    @property
    def own_kod(self) -> bool:
        """Whether the records are encoded with the database's own KOD table instead of the default one."""
        return self.version in VERSIONS_OWN_KOD or self.generation == "v4"


def read_dat_header(file: BinaryIO, *, where: str) -> DatHeader:
    """
    Read the header from the start of `file`, naming `where` in errors.

    Raises ValueError when the file is shorter than the header or does not start with the Cronos magic.
    """
    file.seek(0)
    data = file.read(DAT_HEADER.size)
    if len(data) < DAT_HEADER.size:
        raise ValueError(f"{where} is shorter than its {DAT_HEADER.size}-byte header")
    magic, unknown, version, encoding, blocksize = DAT_HEADER.unpack(data)
    if magic != MAGIC:
        raise ValueError(f"{where} is not a Cronos file: unknown magic {magic!r}")
    return DatHeader(version=version, unknown=unknown, encoding=encoding, blocksize=blocksize)
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `uv run pytest -q tests/test_header.py`
Expected: PASS (5 tests).

- [ ] **Step 6: Make `Datafile` use it.** In `src/cronos_extract/Datafile.py`, add `from ._format.header import read_dat_header` to the imports and replace the body of `readdathdr` (keeping its docstring and the comments about block size and encoding that follow it):

```python
    def readdathdr(self):
        """
        Read the .dat file header.
        Note that the 19 byte header if followed by 0xE9 random bytes, generated by
        'srand(time())' followed by 0xE9 times obfuscate(rand())
        """
        header = read_dat_header(self.dat, where=f"Cro{self.name}.dat")
        self.hdrunk = header.unknown
        self.version = header.version
        self.encoding = header.encoding
        self.blocksize = header.blocksize
        self.use64bit = header.use64bit
```

`struct` may become unused in `Datafile.py`; let `ruff check` tell you, and only remove the import if it does.

- [ ] **Step 7: Run every check**

Run: `uv run pytest -q` — expected: all pass, including `tests/test_database.py::test_file_without_cronos_magic_is_reported_in_the_error`, which pins the magic message, and the golden tests.
Run: `uv run ruff check`, `uv run ruff format --check`, `uv run ty check` — expected: clean.
Run: `git status --short tests/golden` — expected: empty.

Note: a `.dat` file shorter than 19 bytes now raises `ValueError` where it raised `struct.error`. That is the intended direction (`CLAUDE.md`: corrupt structures raise `ValueError` naming the file). If any existing test asserted `struct.error` here, stop and report instead of changing that test.

- [ ] **Step 8: Commit**

```bash
fail() { echo "STOPPED: $*"; exit 1; }
uv run pytest -q > /tmp/claude-1000/p0-t1-pytest.txt 2>&1 || fail pytest
uv run ruff check || fail ruff
uv run ruff format --check || fail format
uv run ty check || fail ty
git add src/cronos_extract/_format tests/test_header.py src/cronos_extract/Datafile.py
git commit -F /tmp/claude-1000/p0-t1-msg.txt || fail commit
```

Commit message:

```text
Parse the Cro*.dat header in one place

The survey command needs the version and encoding flags of a .dat file
without reading its records, and Datafile parsed the header inline.
DatHeader now holds the header's fields and names each version's
generation, and Datafile reads it through read_dat_header.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### Task 2: Find databases and describe them

**Files:**
- Create: `src/cronos_extract/survey.py`
- Create: `tests/test_survey.py`
- Modify: `tests/cronos_builder.py` (add `write_header_only_datafile`)
- Modify: `tests/test_cronos_builder.py` (test for the new helper)

**Interfaces:**
- Consumes: `read_dat_header`, `DatHeader` from Task 1.
- Produces: `SurveyedFile(name: str, path: Path, header: DatHeader | None, problem: str | None)`, `SurveyedDatabase(directory: Path, files: tuple[SurveyedFile, ...])`, and `survey_databases(root: Path) -> Iterator[SurveyedDatabase]`, which yields databases in sorted path order.
- Produces for tests: `cronos_builder.write_header_only_datafile(directory: Path, name: str, version: bytes = b"01.19", encoding: int = 0) -> None`.

- [ ] **Step 1: Write the builder helper's test** in `tests/test_cronos_builder.py`:

```python
def test_write_header_only_datafile_writes_just_the_header(tmp_path: Path) -> None:
    write_header_only_datafile(tmp_path, "Bank", version=b"01.19", encoding=3)

    data = (tmp_path / "CroBank.dat").read_bytes()
    assert len(data) == 19
    assert read_dat_header(io.BytesIO(data), where="CroBank.dat") == DatHeader(
        version=b"01.19", unknown=0, encoding=3, blocksize=BLOCKSIZE
    )
    assert not (tmp_path / "CroBank.tad").exists()
```

Add the imports it needs: `io`, `write_header_only_datafile` and `BLOCKSIZE` from `cronos_builder`, and `DatHeader`/`read_dat_header` from `cronos_extract._format.header`.

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest -q tests/test_cronos_builder.py::test_write_header_only_datafile_writes_just_the_header`
Expected: FAIL, `ImportError: cannot import name 'write_header_only_datafile'`.

- [ ] **Step 3: Add the helper** to `tests/cronos_builder.py`, next to `write_raw_datafile`:

```python
def write_header_only_datafile(directory: Path, name: str, version: bytes = b"01.19", encoding: int = 0) -> None:
    """Write Cro<name>.dat holding only a file header, for versions this builder cannot write records for."""
    directory.mkdir(parents=True, exist_ok=True)
    header = DAT_HEADER.pack(b"CroFile\x00", 0, version, encoding, BLOCKSIZE)
    (directory / f"Cro{name}.dat").write_bytes(header)
```

- [ ] **Step 4: Run it and confirm it passes**, same command. Expected: PASS.

- [ ] **Step 5: Write the failing tests for the survey** in `tests/test_survey.py`:

```python
# ABOUTME: Tests for cronos_extract.survey, which reports the CronosPro version of every database under a directory.
# ABOUTME: Uses databases from tests/cronos_builder.py and header-only files for v4 and v7.
from pathlib import Path

from cronos_builder import write_database, write_header_only_datafile

from cronos_extract.survey import survey_databases


def test_survey_describes_a_built_database(tmp_path: Path) -> None:
    write_database(tmp_path / "db", [])

    (database,) = survey_databases(tmp_path)

    assert database.directory == tmp_path / "db"
    assert [file.name for file in database.files] == ["Bank", "Stru"]
    stru = database.files[1]
    assert stru.problem is None
    assert stru.header is not None
    assert stru.header.generation == "v3"


def test_survey_finds_databases_in_nested_directories_with_mixed_case_names(tmp_path: Path) -> None:
    write_database(tmp_path / "one" / "inner", [])
    write_header_only_datafile(tmp_path / "two", "Bank", version=b"01.19")
    (tmp_path / "two" / "CroBank.dat").rename(tmp_path / "two" / "crobank.DAT")

    directories = [database.directory for database in survey_databases(tmp_path)]

    assert directories == [tmp_path / "one" / "inner", tmp_path / "two"]


def test_survey_reports_a_v7_header(tmp_path: Path) -> None:
    write_header_only_datafile(tmp_path / "v7", "Bank", version=b"01.19", encoding=2)

    (database,) = survey_databases(tmp_path)

    (bank,) = database.files
    assert bank.header is not None
    assert (bank.header.version_text, bank.header.generation, bank.header.compressed) == ("01.19", "v7", True)


def test_survey_reports_unreadable_files_without_stopping(tmp_path: Path) -> None:
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "CroStru.dat").write_bytes(b"NotACronosFile" + bytes(20))
    (tmp_path / "broken" / "CroBank.dat").write_bytes(b"short")
    write_header_only_datafile(tmp_path / "fine", "Stru")

    databases = list(survey_databases(tmp_path))

    problems = [file.problem for database in databases for file in database.files if file.problem]
    assert len(problems) == 2
    assert any("unknown magic" in problem for problem in problems)
    assert any("shorter than" in problem for problem in problems)
    assert [database.directory for database in databases] == [tmp_path / "broken", tmp_path / "fine"]
```

- [ ] **Step 6: Run them and confirm they fail**

Run: `uv run pytest -q tests/test_survey.py`
Expected: FAIL, `ModuleNotFoundError: No module named 'cronos_extract.survey'`.

- [ ] **Step 7: Write `src/cronos_extract/survey.py`**

```python
# ABOUTME: Finds CronosPro databases under a directory and reports each file's format version.
# ABOUTME: Reads only the 19-byte .dat header of every file, never a .tad file or a record.
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from ._format.header import DatHeader, read_dat_header


@dataclass(frozen=True)
class SurveyedFile:
    """One Cro*.dat file: its header, or the problem that stopped it being read."""

    name: str
    path: Path
    header: DatHeader | None
    problem: str | None


@dataclass(frozen=True)
class SurveyedDatabase:
    """One directory holding Cro*.dat files, with a surveyed file for each of them."""

    directory: Path
    files: tuple[SurveyedFile, ...]


def is_dat_file(filename: str) -> bool:
    """Whether `filename` is a Cro*.dat file, matched case-insensitively as the readers do."""
    lowered = filename.lower()
    return lowered.startswith("cro") and lowered.endswith(".dat")


def survey_file(path: Path) -> SurveyedFile:
    """Read `path`'s header, returning the problem that stopped it instead of raising."""
    name = path.name[3:-4]
    try:
        with path.open("rb") as file:
            return SurveyedFile(name=name, path=path, header=read_dat_header(file, where=path.name), problem=None)
    except (ValueError, OSError) as e:
        return SurveyedFile(name=name, path=path, header=None, problem=str(e))


def survey_databases(root: Path) -> Iterator[SurveyedDatabase]:
    """
    Yield a SurveyedDatabase for every directory under `root` that holds Cro*.dat files, in path order.

    Symbolic links are not followed, so a link loop cannot make this walk forever.
    """
    for directory, subdirectories, filenames in os.walk(root, followlinks=False):
        subdirectories.sort()
        dat_files = sorted(filename for filename in filenames if is_dat_file(filename))
        if dat_files:
            path = Path(directory)
            yield SurveyedDatabase(directory=path, files=tuple(survey_file(path / filename) for filename in dat_files))
```

- [ ] **Step 8: Run the tests and confirm they pass**

Run: `uv run pytest -q tests/test_survey.py tests/test_cronos_builder.py`
Expected: PASS.

- [ ] **Step 9: Run every check, then commit** (guarded exactly as Task 1 Step 8, with `p0-t2-` scratch names, adding `src/cronos_extract/survey.py tests/test_survey.py tests/cronos_builder.py tests/test_cronos_builder.py`).

Commit message:

```text
Find CronosPro databases and read their file headers

survey_databases walks a directory tree, treats every directory with
Cro*.dat files as a database, and reads each file's header. A file it
cannot read keeps its problem message so the walk continues.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### Task 3: The cronos-extract command with its survey subcommand

**Files:**
- Create: `src/cronos_extract/cli.py`
- Modify: `src/cronos_extract/survey.py` (the three output formats)
- Modify: `tests/test_survey.py` (command-level tests)
- Modify: `pyproject.toml` (console script)

**Interfaces:**
- Consumes: `survey_databases`, `SurveyedDatabase` from Task 2.
- Produces: `survey.format_text(databases) -> Iterator[str]`, `survey.format_counts(databases) -> Iterator[str]`, `survey.format_jsonl(databases) -> Iterator[str]`; `cli.main(argv: list[str] | None = None) -> int`.

- [ ] **Step 1: Write the failing command tests** in `tests/test_survey.py`:

```python
import json

from cli import run_command


def test_survey_command_prints_a_line_for_each_file(tmp_path: Path) -> None:
    write_database(tmp_path / "db", [])

    result = run_command("cli", ["survey", str(tmp_path)])

    assert result.returncode == 0, result.stderr
    assert str(tmp_path / "db") in result.stdout
    assert "Stru  01.04  v3  32-bit  kod-encoded  own-kod" in result.stdout


def test_survey_command_counts_without_naming_directories(tmp_path: Path) -> None:
    write_database(tmp_path / "db", [])
    write_header_only_datafile(tmp_path / "v7", "Bank", version=b"01.19")

    result = run_command("cli", ["survey", "--counts", str(tmp_path)])

    assert result.returncode == 0, result.stderr
    assert str(tmp_path) not in result.stdout
    assert "01.04  v3  2" in result.stdout
    assert "01.19  v7  1" in result.stdout


def test_survey_command_writes_one_json_object_per_database(tmp_path: Path) -> None:
    write_header_only_datafile(tmp_path / "v7", "Bank", version=b"01.19", encoding=2)

    result = run_command("cli", ["survey", "--jsonl", str(tmp_path)])

    assert result.returncode == 0, result.stderr
    (line,) = result.stdout.splitlines()
    assert json.loads(line) == {
        "directory": str(tmp_path / "v7"),
        "files": [
            {
                "name": "Bank",
                "version": "01.19",
                "generation": "v7",
                "use64bit": False,
                "kod_encoded": False,
                "compressed": True,
                "own_kod": False,
                "problem": None,
            }
        ],
    }


def test_survey_command_reports_a_problem_file_and_still_exits_zero(tmp_path: Path) -> None:
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "CroStru.dat").write_bytes(b"NotACronosFile" + bytes(20))

    result = run_command("cli", ["survey", str(tmp_path)])

    assert result.returncode == 0, result.stderr
    assert "unknown magic" in result.stdout
    assert "Traceback" not in result.stderr


def test_survey_command_rejects_a_missing_directory(tmp_path: Path) -> None:
    result = run_command("cli", ["survey", str(tmp_path / "nowhere")])

    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert "nowhere" in result.stderr
```

Run the exact text assertions against the real output once the code exists: keep the columns as written here, and if the formatter produces different spacing, change the formatter, not the test.

- [ ] **Step 2: Run them and confirm they fail**

Run: `uv run pytest -q tests/test_survey.py -k command`
Expected: FAIL, `No module named cronos_extract.cli`.

- [ ] **Step 3: Add the formatters** to `src/cronos_extract/survey.py`. They need three more imports: `import json`, `from collections import Counter`, and `Iterable` added to the existing `from collections.abc import Iterator` line.

```python
def describe_file(file: SurveyedFile) -> str:
    """Return the survey line for one file, without its database's directory."""
    if file.header is None:
        return f"{file.name:<6}{file.problem}"
    header = file.header
    flags = [
        f"{'64' if header.use64bit else '32'}-bit",
        "kod-encoded" if header.kod_encoded else "plain",
        "compressed" if header.compressed else "uncompressed",
    ]
    if header.own_kod:
        flags.append("own-kod")
    return f"{file.name:<6}{header.version_text}  {header.generation:<8}" + "  ".join(flags)


def format_text(databases: Iterable[SurveyedDatabase]) -> Iterator[str]:
    """Yield one block of lines per database: its directory, then a line per file."""
    for database in databases:
        yield str(database.directory)
        for file in database.files:
            yield f"  {describe_file(file)}"
        yield ""


def format_counts(databases: Iterable[SurveyedDatabase]) -> Iterator[str]:
    """Yield one line per version with the number of files, naming no directories."""
    counts: Counter[tuple[str, str]] = Counter()
    problems = 0
    for database in databases:
        for file in database.files:
            if file.header is None:
                problems += 1
            else:
                counts[(file.header.version_text, file.header.generation)] += 1
    for (version, generation), count in sorted(counts.items()):
        yield f"{version}  {generation:<8}{count}"
    if problems:
        yield f"unreadable files: {problems}"


def format_jsonl(databases: Iterable[SurveyedDatabase]) -> Iterator[str]:
    """Yield one JSON object per database, with a nested object per file."""
    for database in databases:
        yield json.dumps(
            {
                "directory": str(database.directory),
                "files": [
                    {
                        "name": file.name,
                        "version": file.header.version_text if file.header else None,
                        "generation": file.header.generation if file.header else None,
                        "use64bit": file.header.use64bit if file.header else None,
                        "kod_encoded": file.header.kod_encoded if file.header else None,
                        "compressed": file.header.compressed if file.header else None,
                        "own_kod": file.header.own_kod if file.header else None,
                        "problem": file.problem,
                    }
                    for file in database.files
                ],
            }
        )
```

Note the columns in `describe_file`: the tests above pin `"Stru  01.04  v3  32-bit  kod-encoded  own-kod"`, so keep `name` padded to 6 and `generation` padded to 8. Adjust the code until the test's text matches exactly.

- [ ] **Step 4: Write `src/cronos_extract/cli.py`**

```python
# ABOUTME: The cronos-extract command: an argparse parser whose subcommands read CronosPro databases.
# ABOUTME: Holds only the survey subcommand for now; the export, inspect and crack subcommands follow.
import argparse
import sys
from pathlib import Path

from . import survey


def build_parser() -> argparse.ArgumentParser:
    """Return the cronos-extract argument parser."""
    parser = argparse.ArgumentParser(prog="cronos-extract", description="Read CronosPro databases.")
    subcommands = parser.add_subparsers(dest="subcommand", required=True)
    survey_parser = subcommands.add_parser("survey", help="report the CronosPro version of every database found")
    output = survey_parser.add_mutually_exclusive_group()
    output.add_argument("--counts", action="store_true", help="print only counts per version, naming no directories")
    output.add_argument("--jsonl", action="store_true", help="print one JSON object per database")
    survey_parser.add_argument("directories", nargs="+", type=Path, help="directories to search")
    return parser


def run_survey(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Survey every directory in `args.directories`, printing the format the options ask for."""
    for directory in args.directories:
        if not directory.is_dir():
            parser.error(f"{directory} is not a directory")
    databases = [database for directory in args.directories for database in survey.survey_databases(directory)]
    if args.counts:
        lines = survey.format_counts(databases)
    elif args.jsonl:
        lines = survey.format_jsonl(databases)
    else:
        lines = survey.format_text(databases)
    for line in lines:
        print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the cronos-extract command, returning its exit status."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return run_survey(args, parser)


if __name__ == "__main__":
    sys.exit(main())
```

`parser.error` prints to stderr and exits 2, which is what the missing-directory test expects.

- [ ] **Step 5: Add the console script.** In `pyproject.toml`, under `[project.scripts]`, add above the existing two:

```toml
cronos-extract = "cronos_extract.cli:main"
```

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `uv run pytest -q tests/test_survey.py`
Expected: PASS. Then `uv sync` and `uv run cronos-extract survey test_data` — expected: a block for `test_data/all_field_types` and one for `test_data/all_field_types/Voc`.

- [ ] **Step 7: Run every check, then commit** (guarded as Task 1 Step 8, `p0-t3-` scratch names, adding `src/cronos_extract/cli.py src/cronos_extract/survey.py tests/test_survey.py pyproject.toml uv.lock`).

Commit message:

```text
Add the cronos-extract command with a survey subcommand

cronos-extract survey reports the CronosPro version, generation and
encoding flags of every database under a directory, reading only file
headers. --counts names no directories, for sensitive paths, and
--jsonl prints one object per database for scripts.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### Task 4: Document the survey and hand it to Ben

**Files:**
- Modify: `README.md` (a section after "Quick start")
- Modify: `CLAUDE.md` (the commands section)

- [ ] **Step 1: Add the README section**

````markdown
# Surveying databases

Before exporting anything, `cronos-extract survey` reports which CronosPro version each database uses. It reads only
the 19-byte header of every `Cro*.dat` file: no records, no file contents.

```bash
cronos-extract survey /path/to/databases            # a block per database
cronos-extract survey --counts /path/to/databases   # counts per version, naming no directories
cronos-extract survey --jsonl /path/to/databases    # one JSON object per database, for scripts
```

Versions `01.02`–`01.05` are v3, `01.11`–`01.14` are v4 and `01.19` is v7. cronos-extract reads v3 and v4; v7 is not
supported yet.
````

- [ ] **Step 2: Add one line to `CLAUDE.md`** in the commands block:

```bash
uv run cronos-extract survey test_data    # report each database's format version
```

- [ ] **Step 3: Run every check, then commit** (guarded as Task 1 Step 8, `p0-t4-` scratch names).

Commit message:

```text
Document the survey command

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

- [ ] **Step 4: Push, open the PR, get CI green**

```bash
fail() { echo "STOPPED: $*"; exit 1; }
REPO=hammersleyfutures/cronos-extract
git push -u origin phase0-survey || fail push
[ -z "$(gh pr list -R $REPO --head phase0-survey --state all --json number -q '.[].number')" ] || fail "PR exists"
gh pr create -R $REPO --base master --head phase0-survey \
  --title "Add cronos-extract survey, which reports each database's format version" \
  --body-file /tmp/claude-1000/p0-pr-body.md || fail "pr create"
```

The PR body says what the command does, that it reads only headers, that `Datafile` now parses its header through
`read_dat_header`, and that a `.dat` file shorter than 19 bytes raises `ValueError` instead of `struct.error`. It ends
with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

Wait for the checks, fix any failure test-first, and address the bot review threads: verify each finding before acting
on it, and ask Ben before dismissing any code-scanning alert.

- [ ] **Step 5: Ask Ben to run the survey**

Ask him to run, with the `!` prefix so paths stay in his session:

```bash
uv run cronos-extract survey --counts /path/to/his/databases
```

Ask for the counts output, or the full output if the directory names aren't sensitive. Record the versions found in the
Phase 4 spec when it is written: they decide whether v7 support can be confirmed against real files or must ship as
experimental.
