# Review Minors (after PR 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the five minor findings from the PR 2 task review, plus the wrong-KOD `strudump` traceback found while checking them, on a branch `review-minors`, as PR 3.

**Architecture:** Two small behaviour changes in `src/cronos_extract/Database.py` (database-definition decode errors become `ValueError` with a message, and one conditional KOD hint is shared by `enumerate_tables` and `strudump`), then two test-only changes that tighten assertions and remove duplicated parsing from a fixture test. Each task is test-first and one commit.

**Tech Stack:** Python 3.12+, uv, ruff (line length 120), ty (all rules as errors), pytest (`filterwarnings = error`), golden files in `tests/golden/`, `gh` CLI.

**Spec:** No separate spec. The five findings are recorded in `.superpowers/sdd/2026-09-15-pr2-bug-fixes/progress.md` (lines starting `Task 5: minor (deferred)`); the decisions below are the spec.

## Global Constraints

- Address the user as "Ben". Ben's global rules in `~/.claude/CLAUDE.md` override skills.
- Repository `/data/Development/Code/cronodump`, GitHub `hammersleyfutures/cronos-extract` (a fork). Always pass `-R hammersleyfutures/cronos-extract` to `gh pr` commands. Never push to `master`. Never open anything against `alephdata/cronodump`.
- Merge with a merge commit only (`gh pr merge --merge`): `.git-blame-ignore-revs` lists exact commit hashes.
- Every change is test-first: write the test, run it and confirm it fails for the stated reason, change the code, run it green. Real databases only (`tests/cronos_builder.py`, `test_data/all_field_types`), never mocks.
- One logical change per commit. Subject in imperative mood, ≤ 72 characters. Body says what and why. Every commit message ends with exactly `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` — subagents use this line verbatim, not their own model name. PR descriptions end with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
- Names and comments describe what code is, never its history ("new", "fixed", "improved", "legacy"). Never delete a comment unless it is false.
- Before every commit, all clean, each checked by exit code: `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check`, `uv run ty check`.
- Bash tool: `set -e` does not stop a multi-line command. Guard commits and pushes with explicit checks, e.g. `fail() { echo "STOPPED: $*"; exit 1; }` and `cmd > out.txt 2>&1 || fail "cmd"`. Never pipe a checked command through `tail`.
- Golden files: only after a deliberate output change run `uv run pytest --update-golden`, then `git diff tests/golden` must show exactly the intended lines.
- Plain, factual language. Avoid: critical, crucial, essential, significant, comprehensive, robust, elegant.
- Scratch files get unique names (prefix with the task number).

## Decisions

1. **`strudump` catches every `ValueError` (finding 1).** The reviewer suggested narrowing the `try` in `Database.strudump` to `decode_db_definition`. Declined: the other `ValueError`s reaching it (corrupt extended records from `Datafile.readrec`) already name the record and file, and narrowing would bring back tracebacks on untrusted input. The reviewer's "bare `int()` errors" do not reach `strudump`: `TableDefinition` catches its own parse errors and prints warnings. Checking this found a real gap instead: with a wrong KOD, `decode_db_definition` raises `EOFError`, which `strudump` does not catch (`uv run crodump --nokod strudump test_data/all_field_types` exits 1 with a traceback), and croconvert prints `ERROR decoding db definition: ` with an empty message. Task 1 turns that `EOFError` into `ValueError: the database definition is cut off after <n> keys`.
2. **KOD hint (finding 2).** A wrong KOD can make the definition fail in several ways (truncation, garbage record numbers, even a garbage reference that happens to hit a deleted record), so the cause can't be told from the exception type. Instead of an unconditional "This could possibly mean that you need to try crodump strucrack", both `enumerate_tables` and `strudump` print one conditional hint, `KOD_HINT` (Task 2), after the error. For a readable key name such as `key "DanglingKey"` the reader can see the condition doesn't apply.
3. **Loose assertions (finding 3).** Deleted-key tests assert the exact stderr lines (Task 2, since it changes those lines). Corrupt-compressed tests assert the exact warning or dump line (Task 3). They do not assert "exactly one" warning: a CSV export warns once per table pass, so the warning appears twice today; that is already in the modernisation backlog (Appendix A of `docs/superpowers/plans/2026-09-15-pr2-bug-fixes.md`, "A corrupt record is warned about once per table pass").
4. **Fixture test duplicates the parser (finding 4).** Task 4 compares the written definition bytes with `TEST_DB`'s definition plus the expected key bytes, with no parsing loop.
5. **Characterisation tests in `tests/test_readers.py` (finding 5): no change.** `test_readname_decodes_cp1251_bytes`, `test_readlongstring_decodes_cp1251_bytes` and `test_readname_raises_eoferror_past_the_end_of_the_buffer` pass without the CP-1251 fix, which the reviewer noted "for completeness". They are correct tests of `ByteReader` behaviour that had none before; removing or rewriting them would reduce coverage.

---

### Task 1: Report a cut-off database definition instead of raising EOFError

**Files:**
- Modify: `src/cronos_extract/Database.py:126-148` (`decode_db_definition`)
- Test: `tests/test_crodump.py` (add one test after `test_strudump_stops_with_a_clear_message_for_a_key_referencing_a_deleted_record`)
- Golden: `tests/golden/croconvert-postgres-nokod.stderr`

**Interfaces:**
- Produces: `Database.decode_db_definition(data)` raises `ValueError("the database definition is cut off after <n> keys")` (n = number of keys decoded so far) when the data ends inside a key; it no longer lets `EOFError` escape.

- [ ] **Step 1: Create the branch**

```bash
cd /data/Development/Code/cronodump
git fetch origin --prune
git switch master && git merge --ff-only origin/master
git switch -c review-minors
```

- [ ] **Step 2: Write the failing test** in `tests/test_crodump.py`, after `test_strudump_stops_with_a_clear_message_for_a_key_referencing_a_deleted_record`:

```python
def test_strudump_without_the_database_kod_stops_with_a_message() -> None:
    result = run_command("crodump", ["--nokod", "strudump", str(TEST_DB)])

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert result.stderr.splitlines() == [
        "WARN: expected dbinfo to start with 0x03",
        "Error: the database definition is cut off after 0 keys",
    ]
```

- [ ] **Step 3: Run it and confirm it fails**

Run: `uv run pytest -q tests/test_crodump.py::test_strudump_without_the_database_kod_stops_with_a_message`
Expected: FAIL; stderr contains `Traceback` and ends with `EOFError`.

- [ ] **Step 4: Implement.** In `decode_db_definition`, wrap the existing `while` loop in `try` and convert `EOFError`. The method becomes:

```python
def decode_db_definition(self, data):
    """
    decode the 'bank' / database definition
    """
    rd = ByteReader(data)

    d = dict()
    try:
        while not rd.eof():
            keyname = rd.readname()
            if keyname in d:
                print(f"WARN: duplicate key: {keyname}", file=sys.stderr)

            index_or_length = rd.readdword()
            if index_or_length >> 31:
                d[keyname] = rd.readbytes(index_or_length & 0x7FFFFFFF)
            else:
                refdata = self.stru.readrec(index_or_length)
                if refdata is None:
                    raise ValueError(f'key "{keyname}" refers to CroStru record {index_or_length}, which is deleted')
                if refdata[:1] != b"\x04":
                    print("WARN: expected refdata to start with 0x04", file=sys.stderr)
                d[keyname] = refdata[1:]
    except EOFError as e:
        raise ValueError(f"the database definition is cut off after {len(d)} keys") from e
    return d
```

Let `uv run ruff format` decide the line breaks.

- [ ] **Step 5: Run the test and confirm it passes**

Run: `uv run pytest -q tests/test_crodump.py::test_strudump_without_the_database_kod_stops_with_a_message`
Expected: PASS.

- [ ] **Step 6: Update the golden file and check its diff**

Run: `uv run pytest -q tests/test_cli_characterisation.py` — expected: FAIL for `croconvert-postgres-nokod` only.
Run: `uv run pytest -q --update-golden tests/test_cli_characterisation.py`, then `git diff tests/golden`.
Expected diff, and nothing else:

```diff
-ERROR decoding db definition: 
+ERROR decoding db definition: the database definition is cut off after 0 keys
```

- [ ] **Step 7: Run all checks, then commit**

```bash
fail() { echo "STOPPED: $*"; exit 1; }
uv run pytest -q > /tmp/claude-1000/t1-pytest.txt 2>&1 || fail pytest
uv run ruff check || fail ruff
uv run ruff format --check || fail format
uv run ty check || fail ty
git add src/cronos_extract/Database.py tests/test_crodump.py tests/golden/croconvert-postgres-nokod.stderr
git commit -F /tmp/claude-1000/t1-commit-msg.txt || fail commit
```

Commit message (write to the file above first):

```text
Report a cut-off database definition instead of raising EOFError

With a KOD that isn't the database's own, the CroStru database
definition decodes as garbage and ends inside a key. The EOFError
escaped strudump as a traceback, and croconvert printed an empty
"ERROR decoding db definition:" message. decode_db_definition now
raises ValueError saying how many keys were decoded, which strudump
reports with its existing "Error:" message.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### Task 2: Show one conditional KOD hint in strudump and exports

**Files:**
- Modify: `src/cronos_extract/Database.py` (add `KOD_HINT` near the top, after the imports; `strudump` ~109-118; `enumerate_tables` ~208-226)
- Test: `tests/test_crodump.py` (`test_strudump_stops_with_a_clear_message_for_a_key_referencing_a_deleted_record`, `test_strudump_without_the_database_kod_stops_with_a_message`)
- Test: `tests/test_croconvert.py` (`test_croconvert_reports_a_key_referencing_a_deleted_record`)
- Golden: `tests/golden/croconvert-postgres-nokod.stderr`

**Interfaces:**
- Consumes: Task 1's `ValueError("the database definition is cut off after <n> keys")`.
- Produces: module constant `cronos_extract.Database.KOD_HINT: str`, printed on its own stderr line after a database definition error by `Database.enumerate_tables` and `Database.strudump`.

- [ ] **Step 1: Write the failing tests.** In `tests/test_crodump.py` change the import `from cronos_extract.Database import Database` to `from cronos_extract.Database import KOD_HINT, Database`, and replace the two strudump tests' assertions:

```python
def test_strudump_stops_with_a_clear_message_for_a_key_referencing_a_deleted_record(tmp_path: Path) -> None:
    dbdir = key_referencing_a_deleted_record(tmp_path / "db", "DanglingKey")

    result = run_command("crodump", ["strudump", dbdir])

    assert result.returncode == 1
    assert result.stderr.splitlines() == [
        'Error: key "DanglingKey" refers to CroStru record 5, which is deleted',
        KOD_HINT,
    ]


def test_strudump_without_the_database_kod_stops_with_a_message() -> None:
    result = run_command("crodump", ["--nokod", "strudump", str(TEST_DB)])

    assert result.returncode == 1
    assert result.stderr.splitlines() == [
        "WARN: expected dbinfo to start with 0x03",
        "Error: the database definition is cut off after 0 keys",
        KOD_HINT,
    ]
```

In `tests/test_croconvert.py` change the import `from cronos_extract.Database import Database` to `from cronos_extract.Database import KOD_HINT, Database` and replace the test:

```python
def test_croconvert_reports_a_key_referencing_a_deleted_record(tmp_path: Path) -> None:
    dbdir = key_referencing_a_deleted_record(tmp_path / "db", "DanglingKey")

    result = run_command("croconvert", ["-t", "postgres", dbdir])

    assert result.returncode == 0, result.stderr
    assert result.stderr.splitlines() == [
        'ERROR decoding db definition: key "DanglingKey" refers to CroStru record 5, which is deleted',
        KOD_HINT,
    ]
```

The exact line lists also rule out a `Traceback` or `NoneType` message, so the separate `not in` assertions go.

- [ ] **Step 2: Run them and confirm they fail**

Run: `uv run pytest -q tests/test_crodump.py tests/test_croconvert.py -k "deleted_record or without_the_database_kod"`
Expected: FAIL with `ImportError: cannot import name 'KOD_HINT'` (collection error for both files).

- [ ] **Step 3: Implement.** In `src/cronos_extract/Database.py`, after the imports:

```python
# Printed after a database definition error: a KOD that isn't the database's own decodes the definition as garbage.
KOD_HINT = (
    "If the KOD used to read this database is not its own, the definition decodes as garbage; "
    "crodump strucrack can derive the database's KOD."
)
```

In `strudump`:

```python
        try:
            self.dump_db_table_defs(args)
        except ValueError as e:
            sys.exit(f"Error: {e}\n{KOD_HINT}")
```

In `enumerate_tables`, replace the existing hint `print(...)` call (the one printing "This could possibly mean that you need to try     crodump strucrack     to deduct the database key first") with:

```python
            print(KOD_HINT, file=sys.stderr)
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest -q tests/test_crodump.py tests/test_croconvert.py -k "deleted_record or without_the_database_kod"`
Expected: PASS (3 tests).

- [ ] **Step 5: Update the golden file and check its diff**

Run: `uv run pytest -q --update-golden tests/test_cli_characterisation.py`, then `git diff tests/golden`.
Expected diff, and nothing else:

```diff
-This could possibly mean that you need to try     crodump strucrack     to deduct the database key first
+If the KOD used to read this database is not its own, the definition decodes as garbage; crodump strucrack can derive the database's KOD.
```

Also confirm `uv run pytest -q tests/test_croconvert.py::test_db_definition_errors_go_to_stderr_not_into_the_sql tests/test_cronos_builder.py::test_encrypted_database_decodes_only_with_its_kod` passes (both assert `ERROR decoding db definition` only).

- [ ] **Step 6: Run all checks, then commit** (same guarded commands as Task 1 Step 7, with `t2-` scratch names, adding `tests/test_croconvert.py`).

Commit message:

```text
Show one conditional KOD hint after database definition errors

croconvert always said a definition error "could possibly mean" the
database needs crodump strucrack, including when the error was a key
referring to a deleted record, and strudump gave no hint. Both now
print KOD_HINT, which states the condition under which strucrack
helps, so a readable key name shows the reader it doesn't apply.
The deleted-key tests assert the exact stderr lines.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### Task 3: Assert the exact corrupt compressed record messages

**Files:**
- Test: `tests/test_crodump.py` (`test_crodump_shows_a_corrupt_compressed_record_and_dumps_the_next`)
- Test: `tests/test_croconvert.py` (`test_csv_export_skips_a_corrupt_compressed_bank_record`)

**Interfaces:** none (tests only; messages come from `Datafile.decompress` and `Database.readbankrec`).

- [ ] **Step 1: Tighten the assertions.** In `test_crodump_shows_a_corrupt_compressed_record_and_dumps_the_next` replace `assert "corrupt compressed data" in second` with:

```python
    assert second.endswith(" <corrupt compressed data: Error -3 while decompressing data: invalid block type>")
```

In `test_csv_export_skips_a_corrupt_compressed_bank_record` replace the `assert any(...)` statement with:

```python
    warning = (
        "Warning: CroBank record 2 is corrupt: ValueError: corrupt compressed data: "
        "Error -3 while decompressing data: invalid block type; skipping it"
    )
    assert warning in result.stderr.splitlines(), result.stderr
```

- [ ] **Step 2: Show the assertions can fail.** A test-only change has no pre-fix failure, so check each assertion bites: temporarily change `corrupt compressed data` to `corrupt compressed record` in the `raise ValueError(...)` in `src/cronos_extract/Datafile.py` `decompress`, run
`uv run pytest -q tests/test_crodump.py::test_crodump_shows_a_corrupt_compressed_record_and_dumps_the_next tests/test_croconvert.py::test_csv_export_skips_a_corrupt_compressed_bank_record`
Expected: both FAIL. Then `git checkout src/cronos_extract/Datafile.py` and confirm `git status --short src` is empty.

- [ ] **Step 3: Run the two tests green**, same command. Expected: PASS.

- [ ] **Step 4: Run all checks, then commit** (guarded as in Task 1 Step 7, `t3-` scratch names).

Commit message:

```text
Assert the exact messages for corrupt compressed records

The crodump and CSV export tests only checked that a line mentioned
"corrupt". They now compare the dump line's ending and the full
export warning. They don't count warnings: a CSV export warns once
per table pass, which is a known duplicate.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

CI runs these on Python 3.12, 3.13 and 3.14. If a Python's zlib words the error differently, compare up to `corrupt compressed data: ` instead and say so in the PR.

### Task 4: Check the deleted-record fixture by its bytes

**Files:**
- Test: `tests/test_cronos_builder.py` (`test_key_referencing_a_deleted_record_appends_a_dangling_key`, ~lines 73-90; imports)

**Interfaces:**
- Consumes: `cronos_builder.key_referencing_a_deleted_record(directory, keyname)`, which appends key bytes `bytes([len(name)]) + name + struct.pack("<L", deleted_recno)` to CroStru record 1 and writes record `deleted_recno` (5 for `TEST_DB`) as deleted.

- [ ] **Step 1: Replace the test** (no parsing loop):

```python
def test_key_referencing_a_deleted_record_appends_a_dangling_key(tmp_path: Path) -> None:
    with Database(str(TEST_DB), False, KODcoding(INITIAL_KOD)) as original:
        assert original.stru is not None
        original_dbinfo = original.stru.readrec(1)
    assert original_dbinfo is not None

    dbdir = key_referencing_a_deleted_record(tmp_path, "DanglingKey")

    with Database(dbdir, False, KODcoding(INITIAL_KOD)) as db:
        assert db.stru is not None
        assert db.stru.readrec(1) == original_dbinfo + bytes([11]) + b"DanglingKey" + struct.pack("<L", 5)
        assert db.stru.readrec(5) is None
```

In the imports: add `import struct` before `from pathlib import Path`, add `TEST_DB` to the `from cronos_builder import (...)` list, and delete `from cronos_extract.readers import ByteReader` (only the replaced test used it). Keep `import pytest`: `test_encrypted_database_decodes_only_with_its_kod` uses it.

- [ ] **Step 2: Show the test can fail.** Temporarily change `struct.pack("<L", deleted_recno)` in `tests/cronos_builder.py` `key_referencing_a_deleted_record` to `struct.pack("<L", deleted_recno + 1)`, run
`uv run pytest -q tests/test_cronos_builder.py::test_key_referencing_a_deleted_record_appends_a_dangling_key`
Expected: FAIL on the `readrec(1) ==` assertion. Then `git checkout tests/cronos_builder.py`.

- [ ] **Step 3: Run it green**, same command. Expected: PASS.

- [ ] **Step 4: Run all checks, then commit** (guarded as in Task 1 Step 7, `t4-` scratch names).

Commit message:

```text
Check the deleted-record fixture by its bytes

The fixture test re-implemented decode_db_definition's key loop to
find the dangling key, a copy that could drift from the reader. It
now compares CroStru record 1 with TEST_DB's definition followed by
the expected key bytes, and checks the referenced record is deleted.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### Task 5: Open PR 3, get CI green, ask Ben to merge

- [ ] **Step 1: Push and open the PR**

```bash
fail() { echo "STOPPED: $*"; exit 1; }
REPO=hammersleyfutures/cronos-extract
git push -u origin review-minors || fail push
[ -z "$(gh pr list -R $REPO --head review-minors --state all --json number -q '.[].number')" ] || fail "PR exists"
gh pr create -R $REPO --base master --head review-minors \
  --title "Report KOD decode errors clearly and tighten review-minor tests" \
  --body-file /tmp/claude-1000/t5-pr-body.md || fail "pr create"
```

PR body (`/tmp/claude-1000/t5-pr-body.md`):

```markdown
## What this does

Follow-ups to the task review of PR #2.

- `crodump strudump` with a KOD that isn't the database's own stopped with an `EOFError` traceback, and croconvert printed an empty `ERROR decoding db definition:` message. A cut-off database definition now raises `ValueError: the database definition is cut off after <n> keys`.
- `strudump` and the exports print one hint after a database definition error, stating when `crodump strucrack` helps, instead of croconvert's unconditional "This could possibly mean that you need to try crodump strucrack".
- Tests for deleted-record keys and corrupt compressed records assert the exact messages.
- The deleted-record fixture test compares bytes instead of re-implementing the definition parser.

## Test plan

- [x] `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check`, `uv run ty check`: clean
- [x] Golden diff limited to `croconvert-postgres-nokod.stderr` (error message and hint lines)
- [ ] CI (Python 3.12, 3.13, 3.14) and CodeQL

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

- [ ] **Step 2: Wait for checks** (background, bounded):

```bash
REPO=hammersleyfutures/cronos-extract; PR=$(gh pr view -R $REPO review-minors --json number -q .number)
for i in $(seq 1 30); do out=$(gh pr checks $PR -R $REPO 2>&1); if [ -n "$out" ] && ! echo "$out" | rg -q 'pending|no checks reported'; then echo "$out"; exit 0; fi; sleep 60; done; echo "still pending"
```

Expected: all checks pass. List code-scanning alerts on `refs/pull/<PR>/merge` and bot review threads; verify each before acting, fix test-first, ask Ben before dismissing any alert.

- [ ] **Step 3: Ask Ben for approval to merge** (report CI, alerts, threads). Only then: `gh pr merge <PR> -R hammersleyfutures/cronos-extract --merge`, update local `master`, run `uv run pytest -q` on it, and ask Ben before deleting `review-minors`.

---

## Outcome (2026-09-16)

Merged as PR #3 (`ed02fe6`). Beyond Tasks 1 to 4, the final whole-branch review and Copilot led to:

- key record numbers checked against the number of CroStru records. The plan's wrong-KOD analysis had used only `test_data`, whose files ignore `--kod`; on a genuinely encrypted database a wrong KOD still raised `struct.error` for about half of the wrong tables tried;
- one `Database.read_db_definition()`, with clear errors for a deleted or missing CroStru record 1 instead of a `TypeError`;
- exact assertions in the wrong-KOD builder test, and corrupt-compressed-record tests that no longer pin zlib's own wording;
- a corrected header comment in `tests/test_database.py`.

Copilot's suggestion to derive record 5 from `nrofrecords` in the fixture test was declined: the test data is committed, and other tests assert the same record number.
