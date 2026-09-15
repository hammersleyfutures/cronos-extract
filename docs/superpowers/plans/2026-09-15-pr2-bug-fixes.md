# PR 2 (bug-fixes into master) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open, review, fix and merge PR 2 — the `bug-fixes` branch of cronos-extract into `master` — then run `/init` and start the modernisation plan.

**Architecture:** `bug-fixes` already holds 51 tested bug-fix commits (plus 3 merge commits) on top of PR 1, which is merged. The remaining work is process: open the PR, get CI, CodeQL, Copilot and a Fable review, fix every confirmed finding test-first on `bug-fixes`, merge with a merge commit, then document the repo (`/init`) and brainstorm the modernisation.

**Tech Stack:** Python 3.12+, uv (`uv_build` backend), ruff, ty (all rules as errors), pytest (`filterwarnings = error`), pre-commit, GitHub Actions (CI + CodeQL), `gh` CLI.

**Spec:** No separate spec. The decisions made so far are recorded in the "Decisions already made" section below; treat them as the spec.

## Global Constraints

- Address the user as "Ben". Ben's global rules are in `~/.claude/CLAUDE.md`; they override skills. Key ones for this work are repeated here.
- Repository: `/data/Development/Code/cronodump` (directory name unchanged). GitHub: `hammersleyfutures/cronos-extract` (a fork of `alephdata/cronodump`, renamed). Remotes: `origin` = hammersleyfutures/cronos-extract, `upstream` = alephdata/cronodump.
- Never push to `master`. Never open a PR or issue against `alephdata/cronodump`. Always pass `-R hammersleyfutures/cronos-extract` to `gh pr` commands: on a fork, `gh` otherwise targets the parent repo.
- Merge PRs with a merge commit (`gh pr merge --merge`), never squash or rebase: `.git-blame-ignore-revs` lists exact commit hashes of formatting commits.
- Every fix is test-first: write the failing test, run it and confirm it fails for the right reason, fix, run it green. Real data only (build databases with `tests/cronos_builder.py`), never mocks.
- One logical change per commit. Subject in imperative mood, ≤ 72 characters. Body says what and why. End every commit message with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`. PR descriptions end with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
- Every new code file starts with two comment lines beginning `# ABOUTME: `.
- Names and comments describe what code is, never its history ("new", "fixed", "improved", "legacy"). Never delete a comment unless it is false.
- Zero findings: `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check` and `uv run ty check` must all be clean before every commit.
- Bash tool gotcha (see memory `bash-tool-set-e-not-reliable`): `set -e` does not stop a multi-line Bash tool command. Guard every commit or push with explicit checks, e.g. `fail() { echo "STOPPED: $*"; exit 1; }` and `cmd > out.txt 2>&1 || fail "cmd"`. Never pipe a checked command through `tail`.
- Golden files: `tests/test_cli_characterisation.py` compares command output with `tests/golden/`. Only after a deliberate output change run `uv run pytest --update-golden`, then inspect `git diff tests/golden` and confirm the diff is exactly the intended change.
- Plain, factual language in commits and PRs. Avoid: critical, crucial, essential, significant, comprehensive, robust, elegant.
- Parallel subagents each need their own git worktree. Agent worktrees have started from an old commit before; tell agents to run `git switch -c <branch> bug-fixes` first. `.claude/worktrees/` is excluded locally via `.git/info/exclude`.
- Give scratch files unique names (two agents once overwrote each other's commit-message file in a shared scratch directory).

---

## Current state (2026-09-15)

- `master` = `5998ae8` (PR 1 merged: rename to cronos-extract, uv tooling, CI, characterisation tests).
- `bug-fixes` = `ade3f54`, pushed to `origin/bug-fixes`. 51 non-merge commits ahead of `master`, 1 behind (only the PR 1 merge commit). Local run: 134 tests pass on Python 3.12, 3.13 and 3.14; ruff and ty clean.
- PR 2 is **not opened yet**.
- Branches that can be deleted after PR 2 merges (ask Ben first): `tooling`, `successor-base`, `bug-fixes`.
- Test layout: `tests/cli.py` (`run_command(module, args, cwd=None, stdin=None)`), `tests/cronos_builder.py` (database builder: `write_database`, `write_datafile`, `write_raw_datafile`, `crackable_database`, `bank_record`, `complex_field`, `file_reference_field`, `file_record`, `random_kod`, constants `TEST_DB`, `TEST_TABLE_ID`, `DAT_PREFIX_SIZE`, `BLOCKSIZE`), test files `test_cli_characterisation.py`, `test_crack.py`, `test_croconvert.py`, `test_crodump.py`, `test_cronos_builder.py`, `test_database.py`, `test_datafile.py`, `test_datamodel.py`, `test_dumpdbfields.py`, `test_hexdump.py`, `test_koddecoder.py`.

## Private repository

Ben is making `hammersleyfutures/cronos-extract` private until the package is published to PyPI. Check the repository's visibility (`gh repo view hammersleyfutures/cronos-extract --json visibility,isFork`) at the start of the session, and plan around these consequences:

- GitHub does not let a public fork be made private. Making it private needs the fork detached from alephdata's network first (GitHub Support), or a new private repository with this history pushed to it. If a new repository is used, update the `origin` remote and every `-R hammersleyfutures/cronos-extract` in this plan.
- CodeQL code scanning on a private repository needs a GitHub Code Security licence. Without it the `codeql.yml` workflow and the `CodeQL` check fail or don't run (Task 3); ask Ben whether to keep the workflow, disable it, or run the CodeQL CLI locally instead (`codeql database create` + `codeql database analyze ... codeql/python-queries:codeql-suites/python-security-and-quality.qls`; the CLI bundle is at https://github.com/github/codeql-action/releases).
- Copilot code review on a private repository needs a Copilot plan with code review (Task 4).
- GitHub Actions minutes are limited for private repositories; each PR push runs the lint job, three test jobs and CodeQL.

## Decisions already made

- Successor project named **cronos-extract** (PyPI distribution `cronos-extract`, import package `cronos_extract`), based on cronodump `master` merged with the `erdgeist-strucrack-ambigous-kods` branch (alephdata/cronodump#13), full history kept. LICENSE keeps OCCRP's notice and adds `Copyright (c) 2026 Ben Hammersley`.
- Python 3.12+. Stacked PRs: PR 1 (tooling, merged), PR 2 (bug fixes).
- Records that partly fail to decode: keep the row with the decoded fields, warn on stderr, print a count at the end.
- PostgreSQL export: every column TEXT; empty values NULL; NUL characters replaced with U+FFFD plus a stderr warning; one INSERT per record; table and column names unique within 63 bytes.
- CodeQL alert `py/clear-text-logging-sensitive-data` (strudump prints the NS1 password) was dismissed as "won't fix": printing the password is intended.
- `--strucrack`/`--dbcrack` in all commands go through `crodump.crack_kod(method, dbdir, compact)`, which parses options with the real subcommand parser (`build_parser()`).
- Crack functions return `None` when they can't produce a valid permutation; never a placeholder table.
- ruff selects `E, W, F, I, B, UP, SIM, RUF, RET501, RET502, RET503`. `ERA001` (commented-out code) is deliberately not enabled: it flags format documentation comments in `Datafile.py`.
- The GitHub fork is to be detached from alephdata's fork network — Ben does this via GitHub Support.
- A courtesy issue on alephdata/cronodump is drafted (Appendix B). Do not post it. Ben will post it once he has developed the package further and published it to PyPI, after approving the final text.
- Ben is making the GitHub repository private until the PyPI release (decided 2026-09-15). See "Private repository" above.

---

### Task 1: Verify the branch before opening PR 2

**Files:** none changed.

- [ ] **Step 1: Check out and sync**

```bash
cd /data/Development/Code/cronodump
git fetch origin --prune
git switch bug-fixes
git status -sb
git rev-parse --short HEAD origin/bug-fixes origin/master
git rev-list --left-right --count origin/master...bug-fixes
```

Expected: clean tree on `bug-fixes` apart from this untracked plan file; `HEAD` equals `origin/bug-fixes` (`ade3f54` unless new commits were pushed); counts `1	54` (behind 1 = the PR 1 merge commit; ahead 54 = 51 commits plus 3 merge commits).

- [ ] **Step 2: Run every check**

```bash
uv sync
uv run pytest -q > /tmp/pr2-pytest.txt 2>&1; echo "pytest exit=$?"; tail -1 /tmp/pr2-pytest.txt
uv run ruff check && uv run ruff format --check && uv run ty check
```

Expected: `pytest exit=0`, `134 passed`; ruff `All checks passed!`; format clean; ty `All checks passed!`. If anything fails, stop and investigate before opening the PR.

### Task 2: Open PR 2

**Files:** none changed (PR description only).

- [ ] **Step 1: Write the PR description to a uniquely named file**

Write this exact text to `/tmp/pr2-body.md` (adjust the test count in the test plan if Task 1 showed a different number):

```markdown
## What this does

Fixes bugs found by a code review of cronodump `master` and the `erdgeist-strucrack-ambigous-kods` branch, CodeQL, strict type checking and GitHub's review of PR #1. Every fix has a test that failed before it. With this branch the lint and type-check jobs that failed on PR #1 pass.

**KOD recovery (`--strucrack`, `--dbcrack`, `crodump strucrack`/`dbcrack`)**
- `--strucrack` and `--dbcrack` no longer stop with `AttributeError` in croconvert, crodump and dumpdbfields (alephdata/cronodump#17). All three call `crack_kod()`, which parses options with the subcommand's own parser.
- Only KOD tables that are permutations of 0–255 are returned; otherwise the functions return `None` and explain why.
- `--silent` silences all crack output, so it no longer ends up inside croconvert's HTML or SQL.
- `-f`, `--text` and `--width` input is validated with clear messages; `--text` plaintext may contain colons; `--noninteractive` stops with a message and exit status 1 when cracking fails.
- Suggested `-f` switches stay inside the record; shift rows without data are skipped; the stronger of two claims on a KOD entry wins; user-forced entries are tracked apart from counts; `match_with_mismatches` tests the last offset; dbcrack reads the last record of each file; `KODcoding` instances no longer share a default confidence list.

**Exports (`croconvert`)**
- The HTML template is autoescaped, so file names can no longer inject attributes or script.
- Unreadable, deleted, non-numeric or non-Files-table file references, and corrupt CroBank records, are skipped with one warning instead of aborting the export.
- Records whose fields partly fail to decode keep the decoded fields; each export ends with a count of such records.
- Referenced files and table CSVs get safe, unique names that fit the file system's 255-byte limit.
- PostgreSQL output is loadable: one INSERT per record, every column TEXT, NULL for empty values, NUL characters replaced with U+FFFD, and table and column names unique within 63 bytes.
- HTML rows are balanced and empty images are no longer emitted.
- Unparseable dates and times show as text instead of a Python bytes repr.
- A database without CroStru files stops with a clear message.
- Diagnostics go to stderr, so they no longer corrupt HTML or SQL written to stdout.

**Reading databases**
- Database and Datafile close their files (`with Database(...)`), including when a file fails to parse.
- Corrupt extended records (truncated header, length beyond the file, looping or out-of-file extension blocks) raise `ValueError` instead of hanging or growing memory without bound.
- An unknown file magic is reported in the error instead of printed to stdout.
- `Database` requires its `kod` argument, which fixes dumpdbfields passing the KOD as `compact`; `dumpdbfields --maxrecs` prints the requested number of records.

**Inspection commands (`crodump`)**
- `recdump` stops at the last record (no trailing error lines, no traceback with `--debug`).
- `destruct -t 1` decodes the definition before printing it.
- The global `--nokod` applies to `kodump`.

**Code and tests**
- `tests/cronos_builder.py` writes crafted, optionally KOD-encrypted databases, used by the tests above; `tests/cli.py` runs the commands.
- Explicit return values (ruff RET501–RET503 enabled), unused fields ignored with `_`, commented-out debug code removed.

The golden files changed only where output was deliberately fixed: diagnostics moved from stdout to stderr, recdump's trailing error lines removed, strucrack/dbcrack output after the KOD fixes, and PostgreSQL/HTML output after the template fixes.

## Test plan

- [x] `uv run pytest -q`: 134 passed on Python 3.12, 3.13 and 3.14
- [x] `uv run ruff check`, `uv run ruff format --check`, `uv run ty check`: clean
- [x] PostgreSQL output with empty tables, empty values, quotes, backslashes, NUL characters and repeated table names loaded into PostgreSQL 16
- [ ] CI and CodeQL on this PR

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

- [ ] **Step 2: Create the PR against the fork's master**

```bash
REPO=hammersleyfutures/cronos-extract
[ -z "$(gh pr list -R $REPO --head bug-fixes --state all --json number -q '.[].number')" ] || echo "STOP: a PR from bug-fixes already exists"
gh pr create -R $REPO --base master --head bug-fixes \
  --title "Fix bugs found by review, CodeQL and type checking" \
  --body-file /tmp/pr2-body.md
gh pr view -R $REPO bug-fixes --json number,url,baseRefName,headRefName -q '"#\(.number) \(.url) base=\(.baseRefName) head=\(.headRefName)"'
```

Expected: a new PR URL on `hammersleyfutures/cronos-extract` (not alephdata), `base=master head=bug-fixes`. Note the PR number (probably 2) for the next tasks.

### Task 3: Get CI and CodeQL green

**Files:** whatever a failure requires (fix test-first on `bug-fixes`).

- [ ] **Step 1: Wait for the checks**

CI and CodeQL run on `pull_request`. Poll without a tight loop, e.g. in a background Bash command:

```bash
REPO=hammersleyfutures/cronos-extract; PR=2
for i in $(seq 1 30); do
  out=$(gh pr checks $PR -R $REPO 2>&1)
  echo "$out" | rg -q 'pending' || { echo "$out"; exit 0; }
  sleep 60
done; echo "checks still pending after 30 minutes"; gh pr checks $PR -R $REPO
```

Expected: `lint`, `test (3.12)`, `test (3.13)`, `test (3.14)`, `analyze`, `Analyze (python)` and `CodeQL` all `pass`.

- [ ] **Step 2: Triage any failure**

For a failed job: `gh run view <run-id> -R hammersleyfutures/cronos-extract --job <job-id> --log-failed`. For the `CodeQL` check, list alerts:

```bash
gh api "repos/hammersleyfutures/cronos-extract/code-scanning/alerts?ref=refs/pull/2/merge&state=open&per_page=100" \
  --jq '.[] | "\(.number) \(.rule.severity) \(.rule.id) \(.most_recent_instance.location.path):\(.most_recent_instance.location.start_line)"'
```

Fix each real finding test-first on `bug-fixes`, commit, push (`git push`). Alerts that are intended behaviour: ask Ben before dismissing.

### Task 4: Copilot review round

**Files:** whatever confirmed findings require.

- [ ] **Step 1: Ask Ben to request the Copilot review** (he requests it in the GitHub UI). Copilot failed twice with "Copilot encountered an error" on PR 1 (56 files). If it fails twice on PR 2, ask Ben how to proceed (on PR 1 his instruction was to merge).

- [ ] **Step 2: Wait for the review**

```bash
REPO=hammersleyfutures/cronos-extract; PR=2; AFTER=$(date -u +%Y-%m-%dT%H:%M:%SZ)
for i in $(seq 1 45); do
  new=$(gh api "repos/$REPO/pulls/$PR/reviews?per_page=100" --jq "[.[] | select(.user.login | test(\"copilot\"; \"i\")) | select(.submitted_at > \"$AFTER\")] | .[-1] | select(. != null) | \"\(.submitted_at) \(.body | split(\"\n\")[0])\"" 2>/dev/null || true)
  [ -n "$new" ] && { echo "NEW COPILOT REVIEW: $new"; exit 0; }
  sleep 60
done; echo "no Copilot review after 45 minutes"; exit 1
```

Set `AFTER` to the time Ben requested the review if he requested it before this command starts.

- [ ] **Step 3: Read the review body and all unresolved threads**

```bash
gh api graphql -f query='query { repository(owner:"hammersleyfutures", name:"cronos-extract") { pullRequest(number:2) { reviews(last:10){nodes{author{login} submittedAt body}} reviewThreads(first:100){ nodes { id isResolved path line originalLine comments(first:10){ nodes { databaseId author{login} body } } } } } } }' > /tmp/pr2-threads.json
```

Read the full Copilot review body too: it lists "Suppressed comments" that are not posted as threads. Bots `github-advanced-security` (CodeQL) and `github-code-quality` also post threads; address them the same way.

- [ ] **Step 4: For each finding, verify, then fix test-first or decline with a reason**

Before changing anything, reproduce the finding (a failing test, or a command showing the problem). Do not apply a bot's suggested code blindly: on PR 1 two suggestions were wrong (returning `[0] * 256` as a fake KOD table; falling back to `bytes(".")`, which itself raises `TypeError`). Commit each fix separately on `bug-fixes`, run all checks, `git push`.

- [ ] **Step 5: Reply to and resolve each thread**

```bash
# reply to the first comment of a thread
gh api -X POST "repos/hammersleyfutures/cronos-extract/pulls/2/comments/<comment databaseId>/replies" -f "body=Fixed in <short sha>: <what changed>."
# resolve the thread
gh api graphql -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{isResolved}}}' -f id=<thread id>
```

Post one PR comment (`gh api -X POST repos/hammersleyfutures/cronos-extract/issues/2/comments -f body=...`) covering Copilot's suppressed comments. Check afterwards that no thread is unresolved.

### Task 5: Fresh Fable review of the finished branch

**Files:** whatever confirmed findings require.

- [ ] **Step 1: Dispatch a read-only review agent** with the `Agent` tool, `model: "fable"`, `subagent_type: "general-purpose"`, background. Prompt (copy verbatim, then fill the scratch directory with a fresh path):

```text
Adversarial code review of the Python package cronos-extract at /data/Development/Code/cronodump, branch bug-fixes (compare with master using `git diff master...bug-fixes`). It reads CronosPro database files (Cro*.dat + Cro*.tad): src/cronos_extract/Datafile.py, Database.py, Datamodel.py, readers.py, koddecoder.py (KOD substitution cipher), hexdump.py, kodump.py, crodump.py (inspection CLI and strucrack/dbcrack KOD recovery), croconvert.py (CSV export and Jinja2 templates in src/cronos_extract/templates), dumpdbfields.py. Tests are in tests/ (tests/cronos_builder.py builds crafted databases). Format notes: docs/cronos-research.md.

The branch already fixed many bugs; review the current code, not the history. Threat model: databases are untrusted (often leaked databases analysed by investigators) — crashes, hangs, unbounded memory, path traversal or overwrite in exports, HTML/SQL injection, silent data loss, output corruption.

READ-ONLY: do not edit or commit in the repository. Write scratch files only under <fresh scratch directory>. Run code with `uv run python` and tests with `uv run pytest`.

Priority: 1) correctness bugs, 2) untrusted-input robustness and security, 3) output integrity (CSV/HTML/SQL), 4) resource handling, 5) brief maintainability notes for the planned modernisation. For every finding in 1–4 reproduce it (CONFIRMED, with the exact command and output) or mark PLAUSIBLE with reasoning; discard what you can't support. Give file:line, severity, a one-line failure scenario and a minimal fix. Report compactly (under 80 lines) as a message, ranked most severe first.
```

- [ ] **Step 2: Verify each CONFIRMED finding yourself** (re-run its reproduction), then fix test-first on `bug-fixes`, one commit per fix, all checks, `git push`. Record PLAUSIBLE findings you don't fix in the modernisation backlog (Appendix A) with the reason.

- [ ] **Step 3: If Task 5 produced commits, repeat Task 3 Step 1** so CI is green on the final head.

### Task 6: Merge PR 2

- [ ] **Step 1: Ask Ben for approval to merge.** Report: CI state, code scanning state, review threads (all resolved?), commits added since the PR opened.

- [ ] **Step 2: Merge with a merge commit and verify**

```bash
REPO=hammersleyfutures/cronos-extract; PR=2
gh pr view $PR -R $REPO --json state,headRefOid,baseRefName,mergeable -q '"state=\(.state) head=\(.headRefOid[0:7]) base=\(.baseRefName) mergeable=\(.mergeable)"'
gh pr merge $PR -R $REPO --merge --subject "Merge pull request #$PR from hammersleyfutures/bug-fixes" --body "Fix bugs found by review, CodeQL and type checking"
gh pr view $PR -R $REPO --json state,mergeCommit -q '"state=\(.state) merge=\(.mergeCommit.oid[0:7])"'
git fetch origin --prune && git fetch origin master:master
git switch master && git log --oneline -3
uv sync && uv run pytest -q > /tmp/pr2-master-pytest.txt 2>&1; echo "pytest exit=$?"; tail -1 /tmp/pr2-master-pytest.txt
```

Expected: `state=MERGED`; `master` contains the merge; tests pass on `master`.

- [ ] **Step 3: Ask Ben whether to delete `tooling`, `successor-base` and `bug-fixes`** locally and on origin. Only then: `git branch -d <name>` and `git push origin --delete <name>`.

### Task 7: /init

- [ ] **Step 1: Create a feature branch** from `master`, e.g. `git switch -c claude-md master`.
- [ ] **Step 2: Invoke the `init` skill** to write `CLAUDE.md`. Make sure it covers: uv commands (`uv sync`, `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check`, `uv run ty check`, `uv run pre-commit install`); the golden-file workflow (`--update-golden` + reviewing the diff); `tests/cronos_builder.py` for crafted databases; the package layout (`src/cronos_extract`, templates inside the package); the KOD cipher (`b[i] = (KOD[a[i]] - i - recno) % 256`, valid KOD is a permutation) and that `test_data/all_field_types/CroStru.dat` is encoded with `INITIAL_KOD`; that diagnostics go to stderr; merge-commit-only PRs because of `.git-blame-ignore-revs`; `gh -R hammersleyfutures/cronos-extract` on this fork. Keep it short; don't repeat Ben's global `~/.claude/CLAUDE.md`.
- [ ] **Step 3: Commit, push the branch, open a PR with `-R hammersleyfutures/cronos-extract --base master`**, ask Ben to review and merge.

### Task 8: Start the modernisation plan

- [ ] **Step 1: Invoke `superpowers:brainstorming`** with Ben. Architectural decisions (CLI shape, module layout, public API, typing strategy) are discussed with Ben before any implementation.
- [ ] **Step 2: Use Appendix A as the input backlog.** Output: a spec in `docs/superpowers/specs/`, then a plan via `superpowers:writing-plans`.

---

## Appendix A: Modernisation backlog (not part of PR 2)

Collected from the reviews, the agents' reports and CodeQL; each needs a decision in the modernisation brainstorm.

- **KOD recovery:** strucrack decides each KOD entry independently from its most common byte, so on `test_data` one entry (`KOD[0x13]`) is wrong under either collision rule. Choosing the permutation that maximises the total count (an assignment problem, e.g. the Hungarian algorithm) would be correct by construction. Interactive strucrack/dbcrack exit 0 when cracking fails (only `--noninteractive` exits 1).
- **`--kod` on files that aren't encrypted:** `Datafile.__init__` (`self.kod = kod if not kod or self.isencrypted() else koddecoder.new()`) silently replaces a user's `--kod` table with the default one for v3 files that aren't KOD-encrypted with their own table, so the user gets no sign their table was unused. It also hid, in PR 3's planning, how a wrong KOD behaves on an encrypted database.
- **`crodump destruct -t 1`:** decodes a hex database definition from stdin with a placeholder `Database(".")` that has no CroStru, without catching errors: a truncated definition ends in a `ValueError` traceback, and a key that refers to a CroStru record ends in `AttributeError` on `self.stru`. It also doesn't print `KOD_HINT` like `strudump` does.
- **CLI shape:** `crodump` and `croconvert` command names clash with the original `cronodump` package's commands; consider one `cronos-extract` command with subcommands. `--nodecompress` uses `default="true"` (a string) with `store_false`. `recdump --bank` is unused. `destruct_sys3_def` is an empty stub.
- **Structure:** `Datafile.readrec` and `Datafile.dump` still duplicate record decoding (only the extended-record part is shared). strucrack is a long function mixing cracking, fix application and presentation. No type annotations yet — annotating `ByteReader`, `Datafile`, `Database` would let ty catch wrong positional arguments and `None` returns. `Database.incomplete_records` is a class attribute (works, since `+=` creates an instance attribute, but belongs in `__init__`).
- **Exports:** the CSV export keeps every file-reference field in memory until the end. The Files table header lists every field plus "Data" and would not match its two cells if the Files table had more than one field. Looking up the Files table id decodes table definitions again, so their warnings repeat on stderr. A corrupt record is warned about once per table pass. If the Files table is not defined, every file reference is skipped with "not a record of the Files table". `croconvert` compares output names case-insensitively, adding suffixes PostgreSQL wouldn't need.
- **Format support:** tables with table id > 255 can never match records (`data[0]` is compared with a dword). CronosPro v7 (`01.19`) is unsupported; alephdata/cronodump#24 has detailed research (record envelope, plaintext CroBank, per-bank KOD, known-plaintext recovery). `Datafile.readrec` raises `struct.error` for a record number past the end of the `.tad`. alephdata/cronodump#23 and #15 ask for decoding link fields between tables (field types 7, 8, 9 are shown as hex).
- **From the PR 2 Fable review (maintainability):** CP-1251 decoding uses three error policies (none, `ignore`, `replace`) in different places; pick one and centralise it. `crodump.main`, `dumpdbfields.main` and `croconvert.main` each repeat the `--kod/--nokod/--strucrack/--dbcrack` selection; factor it into one function. `Datafile.decompress` parses but never verifies each chunk's CRC-32; verifying it and warning on a mismatch would catch silently corrupt data.
- **Test data:** `test_data/all_field_types` has almost no live Bank records. Fork `drey555/cronodump` has a `test_data/test_relation` sample with relations (provenance unknown — check licence before use).
- **Project:** PyPI publishing as `cronos-extract`, then making the repository public again and posting the courtesy issue (Appendix B); GitHub fork detachment (Ben, via GitHub Support); CodeQL "Code Quality" dynamic analysis runs alongside the `codeql.yml` workflow (duplicate analysis).

## Appendix B: Draft courtesy issue for alephdata/cronodump (do not post; Ben posts it after further development and the PyPI release)

```markdown
Title: cronos-extract: a maintained successor to cronodump

Hello @erdgeist and @nlitsme,

First, thank you for cronodump and for the format research in `docs/cronos-research.md`. It is the best public work on CronosPro files, and people still depend on it — issue #24 shows researchers still bring new findings here.

Because this repository has been quiet since late 2023 and #13 has been open since 2022, I have started a maintained successor, **cronos-extract**:

https://github.com/hammersleyfutures/cronos-extract

What it is:

- It continues from this repository's `master` together with the `erdgeist-strucrack-ambigous-kods` branch (#13), with the full git history kept, so every commit stays attributed to its author. The MIT licence and OCCRP's copyright notice are retained, and the README credits cronodump as its origin.
- It fixes bugs we found with a code review, CodeQL and type checking, each with a regression test. Among them: `--strucrack`/`--dbcrack` raising `AttributeError` since `--compact` was added (the crash reported in #17), unescaped file names in the HTML template's `download` attribute, single malformed file references aborting a whole CSV export, and strucrack returning KOD tables that are not permutations.
- It uses a different package name (`cronos-extract` on PyPI), so it does not clash with the `cronodump` package you publish.
- It targets Python 3.12+ with uv packaging, type checking and CI.

If you would rather this happened differently — you want to keep maintaining cronodump, want changes offered back as PRs, or object to anything above — please say so here, and I will adjust. You are both very welcome to take part.

Thanks again,
Ben Hammersley
```
