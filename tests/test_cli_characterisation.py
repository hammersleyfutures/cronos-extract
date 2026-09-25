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
