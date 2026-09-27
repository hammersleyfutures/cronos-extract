# ABOUTME: Tests that every cronos-extract command in the README's bash blocks runs and exits as the README says,
# ABOUTME: and that every link in the README is an absolute URL, because PyPI renders it where relative links are dead.
import re
import shlex
from pathlib import Path

import pytest
from cli import run_command
from cronos_builder import TEST_TABLE_ID, bank_record, crackable_database, random_kod

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"
BASH_BLOCK = re.compile(r"^```bash\n(.*?)^```", re.MULTILINE | re.DOTALL)
# A line that stores the output of a command in a shell variable: KOD=$(cronos-extract ...).
CAPTURE = re.compile(r"^(?P<name>[A-Z_]+)=\$\((?P<command>cronos-extract [^)]*)\)(\s+#.*)?$")
# A trailing comment that states the exit status of the command before it, such as "# exits 1, because ...".
STATED_STATUS = re.compile(r"\s#\s*exits (?P<status>\d+)\b")
# The programs of README lines that the test does not run: installers, the development tools, and jq.
SKIPPED_PROGRAMS = ("uv", "pipx", "pip", "jq")
# Inline links [text](target), images ![text](target), and reference definitions [label]: target.
INLINE_LINK = re.compile(r"\]\((?P<target>[^)\s]*)")
REFERENCE_LINK = re.compile(r"^\s*\[[^\]]+\]:\s*(?P<target>\S+)", re.MULTILINE)
PERSON_FIELDS = [b"42", b"Hammersley", b"", b"1240315", b"0930", b"", b"", b"", b"", b"", b""]


def readme_text() -> str:
    return README.read_text(encoding="utf-8")


def bash_blocks(text: str) -> list[str]:
    return [match[1] for match in BASH_BLOCK.finditer(text)]


def without_code(text: str) -> str:
    """The README with its fenced code blocks and inline code removed, leaving the Markdown that PyPI links."""
    text = re.sub(r"^```.*?^```", "", text, flags=re.MULTILINE | re.DOTALL)
    return re.sub(r"`[^`\n]*`", "", text)


def placeholders(tmp_path: Path) -> dict[str, str]:
    """
    The value that each placeholder path of the README stands for in the test.

    /path/to/database is a database encrypted with its own KOD, which the crack examples can recover. The
    placeholders for directories of databases stand for test_data.
    """
    database = crackable_database(tmp_path / "database", [bank_record(TEST_TABLE_ID, PERSON_FIELDS)], random_kod(7))
    list_file = tmp_path / "list.txt"
    list_file.write_text(f"{REPO_ROOT / 'test_data'}\n", encoding="utf-8")
    return {
        "/path/to/database": database,
        "/path/to/databases": str(REPO_ROOT / "test_data"),
        "/path/to/list.txt": str(list_file),
    }


def command_arguments(words: list[str], values: dict[str, str], variables: dict[str, str]) -> list[str]:
    """
    The arguments of a README command after `cronos-extract`, with placeholders, shell variables and test_data
    paths replaced by what they stand for in the test.
    """
    arguments = []
    for word in words[1:]:
        if word.startswith("/path/to/"):
            assert word in values, f"the README uses a placeholder the test does not know: {word}"
            word = values[word]
        elif word.startswith("$"):
            assert word[1:] in variables, f"the README uses a shell variable no earlier line sets: {word}"
            word = variables[word[1:]]
        elif word == "test_data" or word.startswith("test_data/"):
            word = str(REPO_ROOT / word)
        arguments.append(word)
    return arguments


def stated_status(line: str) -> int:
    """The exit status that the trailing comment of a README line states, 0 when it states none."""
    stated = STATED_STATUS.search(line)
    return int(stated["status"]) if stated else 0


def test_the_readme_has_bash_blocks_with_cronos_extract_commands() -> None:
    commands = [
        line for block in bash_blocks(readme_text()) for line in block.splitlines() if "cronos-extract " in line
    ]

    assert len(commands) >= 10


@pytest.mark.parametrize("index", range(len(bash_blocks(README.read_text(encoding="utf-8")))))
def test_each_command_in_a_readme_bash_block_exits_as_the_readme_says(tmp_path: Path, index: int) -> None:
    # Each block runs in its own new directory, so that its outputs go to tmp_path and never exist already. The
    # test_data paths of the README are made absolute for this.
    block = bash_blocks(readme_text())[index]
    values = placeholders(tmp_path)
    workdir = tmp_path / "work"
    workdir.mkdir()
    variables: dict[str, str] = {}
    for line in block.splitlines():
        captured = CAPTURE.match(line.strip())
        words = shlex.split(captured["command"] if captured else line, comments=True)
        if not words:
            continue
        if words[0] in SKIPPED_PROGRAMS:
            continue
        assert words[0] == "cronos-extract", f"the test does not know how to run this README line: {line}"
        result = run_command("cli", command_arguments(words, values, variables), cwd=workdir, stdin="", timeout=120)
        output = f"stdout: {result.stdout[-2000:]}\nstderr: {result.stderr[-2000:]}"
        assert result.returncode == stated_status(line), f"{line}\n{output}"
        if captured:
            variables[captured["name"]] = result.stdout.strip()


def test_every_readme_link_is_an_absolute_url() -> None:
    text = without_code(readme_text())
    targets = [match["target"] for match in INLINE_LINK.finditer(text)]
    targets += [match["target"] for match in REFERENCE_LINK.finditer(text)]

    assert targets
    assert [target for target in targets if not target.startswith(("https://", "http://"))] == []


def test_the_readme_links_the_repository_files_on_github() -> None:
    base = "https://github.com/hammersleyfutures/cronos-extract/blob/main/"
    text = readme_text()

    for path in ("docs/api.md", "CHANGELOG.md", "docs/cronos-research.md", "LICENSE"):
        assert f"]({base}{path})" in text, path
