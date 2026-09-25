# ABOUTME: Characterisation tests that pin the current output of the crodump and croconvert commands.
# ABOUTME: They run the real commands as subprocesses against test_data and compare with golden files.
from collections.abc import Callable
from pathlib import Path

import pytest
from cli import run_command

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_DB = "test_data/all_field_types"

CASES = [
    ("inspect-strudump", "crodump", ["strudump", "-v", "-a", TEST_DB]),
    ("inspect-crodump", "crodump", ["crodump", "-v", TEST_DB]),
    ("inspect-recdump", "crodump", ["recdump", TEST_DB]),
    ("inspect-recdump-stats-stru", "crodump", ["recdump", "--stats", "--stru", TEST_DB]),
    ("crack-strucrack", "crodump", ["strucrack", TEST_DB]),
    ("crack-dbcrack", "crodump", ["dbcrack", TEST_DB]),
    ("inspect-kodump-shift1", "crodump", ["kodump", "-s", "1", "-l", "64", f"{TEST_DB}/CroStru.dat"]),
    ("crodump-sysdump", "crodump", ["sysdump", TEST_DB]),
    ("croconvert-html", "croconvert", [TEST_DB]),
    ("export-postgres", "croconvert", ["-t", "postgres", TEST_DB]),
    ("export-postgres-nokod", "croconvert", ["-n", "-t", "postgres", TEST_DB]),
]


@pytest.mark.parametrize(("name", "module", "args"), CASES, ids=[case[0] for case in CASES])
def test_command_output_matches_golden(
    name: str, module: str, args: list[str], golden: Callable[[str, str], None]
) -> None:
    result = run_command(module, args, cwd=REPO_ROOT)

    assert result.returncode == 0, result.stderr
    golden(f"{name}.stdout", result.stdout)
    golden(f"{name}.stderr", result.stderr)


def test_croconvert_csv_output_matches_golden(tmp_path: Path, golden: Callable[[str, str], None]) -> None:
    outdir = tmp_path / "out"

    result = run_command("croconvert", ["--csv", "-o", str(outdir), TEST_DB], cwd=REPO_ROOT)

    assert result.returncode == 0, result.stderr
    golden("export-csv.stdout", result.stdout)
    golden("export-csv.stderr", result.stderr)
    entries = sorted(path.relative_to(outdir).as_posix() for path in outdir.rglob("*"))
    golden("export-csv/_tree.txt", "\n".join(entries) + "\n")
    for path in sorted(outdir.rglob("*.csv")):
        golden(f"export-csv/{path.relative_to(outdir).as_posix()}", path.read_text(encoding="utf-8"))
