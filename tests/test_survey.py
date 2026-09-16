# ABOUTME: Tests for cronos_extract.survey, which reports the CronosPro version of every database under a directory.
# ABOUTME: Uses databases from tests/cronos_builder.py and header-only files for v4 and v7.
import json
import os
import subprocess
from pathlib import Path

import pytest
from cli import run_command
from cronos_builder import write_database, write_header_only_datafile

from cronos_extract.survey import survey_databases, survey_roots


def test_survey_describes_a_built_database(tmp_path: Path) -> None:
    write_database(tmp_path / "db", [])

    (database,) = survey_databases(tmp_path)

    assert database.directory == tmp_path / "db"
    assert [file.name for file in database.files] == ["Bank", "Stru"]
    stru = database.files[1]
    assert stru.problem is None
    assert stru.generation == "v3"


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
    assert bank.problem is None
    assert (bank.version, bank.generation, bank.compressed) == ("01.19", "v7", True)


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


def test_survey_sorts_a_databases_files_case_insensitively(tmp_path: Path) -> None:
    write_header_only_datafile(tmp_path / "db", "Stru")
    write_header_only_datafile(tmp_path / "db", "Bank")
    (tmp_path / "db" / "CroBank.dat").rename(tmp_path / "db" / "crobank.DAT")

    (database,) = survey_databases(tmp_path)

    assert [file.name for file in database.files] == ["bank", "Stru"]


@pytest.mark.skipif(os.getuid() == 0, reason="root can list a directory whatever its permissions are")
def test_survey_reports_a_directory_it_cannot_list(tmp_path: Path) -> None:
    write_header_only_datafile(tmp_path / "locked", "Stru")
    (tmp_path / "locked").chmod(0o000)
    problems: list[OSError] = []

    try:
        databases = list(survey_databases(tmp_path, problems.append))
    finally:
        (tmp_path / "locked").chmod(0o700)

    assert databases == []
    (problem,) = problems
    assert problem.filename == str(tmp_path / "locked")


def test_survey_roots_yields_a_database_before_walking_the_roots_after_it(tmp_path: Path) -> None:
    write_database(tmp_path / "first" / "db", [])
    (tmp_path / "second").mkdir()

    databases = survey_roots([tmp_path / "first", tmp_path / "second"])
    first = next(databases)
    write_database(tmp_path / "second" / "db", [])
    rest = list(databases)

    assert first.directory == tmp_path / "first" / "db"
    assert [database.directory for database in rest] == [tmp_path / "second" / "db"]


@pytest.mark.skipif(os.getuid() == 0, reason="root can list a directory whatever its permissions are")
def test_survey_roots_reports_an_unlistable_directory_when_the_walk_reaches_it(tmp_path: Path) -> None:
    write_database(tmp_path / "a" / "db", [])
    write_header_only_datafile(tmp_path / "b" / "locked", "Stru")
    write_database(tmp_path / "c" / "db", [])
    (tmp_path / "b" / "locked").chmod(0o000)
    events: list[tuple[str, str]] = []

    try:
        for database in survey_roots(
            [tmp_path / "a", tmp_path / "b", tmp_path / "c"],
            lambda problem: events.append(("problem", str(problem.filename))),
        ):
            events.append(("database", str(database.directory)))
    finally:
        (tmp_path / "b" / "locked").chmod(0o700)

    assert events == [
        ("database", str(tmp_path / "a" / "db")),
        ("problem", str(tmp_path / "b" / "locked")),
        ("database", str(tmp_path / "c" / "db")),
    ]


def test_survey_command_prints_a_line_for_each_file(tmp_path: Path) -> None:
    write_database(tmp_path / "db", [])

    result = run_command("cli", ["survey", str(tmp_path)])

    assert result.returncode == 0, result.stderr
    assert str(tmp_path / "db") in result.stdout
    assert "Stru  01.04  v3       32-bit  plain  uncompressed  own-kod" in result.stdout


def test_survey_command_counts_without_naming_directories(tmp_path: Path) -> None:
    write_database(tmp_path / "db", [])
    write_header_only_datafile(tmp_path / "v7", "Bank", version=b"01.19")

    result = run_command("cli", ["survey", "--counts", str(tmp_path)])

    assert result.returncode == 0, result.stderr
    assert str(tmp_path) not in result.stdout
    assert "01.04  v3       2" in result.stdout
    assert "01.19  v7       1" in result.stdout


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


@pytest.mark.skipif(os.getuid() == 0, reason="root can list a directory whatever its permissions are")
def test_survey_command_warns_about_a_directory_it_cannot_list(tmp_path: Path) -> None:
    write_database(tmp_path / "db", [])
    (tmp_path / "locked").mkdir()
    (tmp_path / "locked").chmod(0o000)

    try:
        result = run_command("cli", ["survey", str(tmp_path)])
    finally:
        (tmp_path / "locked").chmod(0o700)

    assert result.returncode == 0, result.stderr
    assert str(tmp_path / "db") in result.stdout
    assert f"warning: {tmp_path / 'locked'} cannot be listed" in result.stderr
    assert "Traceback" not in result.stderr


def test_survey_command_rejects_a_missing_directory(tmp_path: Path) -> None:
    result = run_command("cli", ["survey", str(tmp_path / "nowhere")])

    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert "nowhere" in result.stderr


def test_survey_command_surveys_the_directories_named_in_a_list_file(tmp_path: Path) -> None:
    write_database(tmp_path / "first" / "db", [])
    write_header_only_datafile(tmp_path / "second" / "v7", "Bank", version=b"01.19")
    list_file = tmp_path / "databases.txt"
    list_file.write_text(
        f"# databases to survey\n\n{tmp_path / 'first'}\n  {tmp_path / 'second'}  \n", encoding="utf-8"
    )

    result = run_command("cli", ["survey", "--list", str(list_file)])

    assert result.returncode == 0, result.stderr
    assert str(tmp_path / "first" / "db") in result.stdout
    assert str(tmp_path / "second" / "v7") in result.stdout


def test_survey_command_counts_a_list_file_as_one_group(tmp_path: Path) -> None:
    write_database(tmp_path / "first" / "db", [])
    write_header_only_datafile(tmp_path / "second" / "v7", "Bank", version=b"01.19")
    list_file = tmp_path / "databases.txt"
    list_file.write_text(f"{tmp_path / 'first'}\n{tmp_path / 'second'}\n", encoding="utf-8")

    result = run_command("cli", ["survey", "--list", str(list_file), "--counts"])

    assert result.returncode == 0, result.stderr
    assert str(tmp_path) not in result.stdout
    assert "01.04  v3       2" in result.stdout
    assert "01.19  v7       1" in result.stdout


def test_survey_command_warns_about_a_list_entry_that_is_not_a_directory(tmp_path: Path) -> None:
    write_database(tmp_path / "db", [])
    list_file = tmp_path / "databases.txt"
    list_file.write_text(f"{tmp_path / 'db'}\n{tmp_path / 'gone'}\n", encoding="utf-8")

    result = run_command("cli", ["survey", "--list", str(list_file)])

    assert result.returncode == 0, result.stderr
    assert str(tmp_path / "db") in result.stdout
    assert f"warning: {tmp_path / 'gone'} is not a directory; skipping it" in result.stderr
    assert "Traceback" not in result.stderr


def test_survey_command_reports_a_database_once_when_the_roots_overlap(tmp_path: Path) -> None:
    write_database(tmp_path / "outer" / "db", [])
    list_file = tmp_path / "databases.txt"
    list_file.write_text(f"{tmp_path / 'outer'}\n{tmp_path / 'outer' / 'db'}\n", encoding="utf-8")

    result = run_command("cli", ["survey", "--list", str(list_file), str(tmp_path / "outer")])

    assert result.returncode == 0, result.stderr
    assert result.stdout.count(str(tmp_path / "outer" / "db")) == 1


def test_survey_command_rejects_a_missing_list_file(tmp_path: Path) -> None:
    result = run_command("cli", ["survey", "--list", str(tmp_path / "nowhere.txt")])

    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert "nowhere.txt" in result.stderr


def test_survey_command_needs_a_directory_or_a_list() -> None:
    result = run_command("cli", ["survey"])

    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert "--list" in result.stderr


def test_survey_command_lines_up_the_columns_of_a_known_and_an_unknown_generation(tmp_path: Path) -> None:
    write_header_only_datafile(tmp_path / "db", "Bank", version=b"01.19")
    write_header_only_datafile(tmp_path / "db", "Stru", version=b"09.99")

    result = run_command("cli", ["survey", str(tmp_path)])

    assert result.returncode == 0, result.stderr
    bank, stru = (line for line in result.stdout.splitlines() if line.startswith("  "))
    assert "  v7" in bank
    assert "  unknown" in stru
    assert bank.index("01.19") == stru.index("09.99")
    assert bank.index("32-bit") == stru.index("32-bit")


def test_survey_command_takes_a_relative_list_entry_from_the_current_directory(tmp_path: Path) -> None:
    write_database(tmp_path / "db", [])
    (tmp_path / "lists").mkdir()
    (tmp_path / "lists" / "databases.txt").write_text("db\n", encoding="utf-8")

    result = run_command("cli", ["survey", "--list", "lists/databases.txt"], cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == "db"
    assert "Stru" in result.stdout


def test_survey_command_counts_the_files_it_could_not_read(tmp_path: Path) -> None:
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "CroStru.dat").write_bytes(b"NotACronosFile" + bytes(20))
    (tmp_path / "broken" / "CroBank.dat").write_bytes(b"short")
    write_header_only_datafile(tmp_path / "v7", "Bank", version=b"01.19")

    result = run_command("cli", ["survey", "--counts", str(tmp_path)])

    assert result.returncode == 0, result.stderr
    assert "unreadable files: 2" in result.stdout
    assert len(result.stdout.splitlines()) == 2


def test_survey_names_a_file_called_cro_dat_after_its_filename(tmp_path: Path) -> None:
    write_header_only_datafile(tmp_path / "db", "")

    (database,) = survey_databases(tmp_path)

    (file,) = database.files
    assert file.name == "Cro.dat"


def test_survey_does_not_follow_a_symlink_loop_back_to_the_parent(tmp_path: Path) -> None:
    write_header_only_datafile(tmp_path / "db", "Bank")
    (tmp_path / "db" / "loop").symlink_to(tmp_path / "db", target_is_directory=True)

    databases = list(survey_databases(tmp_path))

    assert [database.directory for database in databases] == [tmp_path / "db"]


def test_survey_command_reports_a_fifo_instead_of_blocking_on_it(tmp_path: Path) -> None:
    write_header_only_datafile(tmp_path / "db", "Stru")
    os.mkfifo(tmp_path / "db" / "CroBank.dat")

    try:
        result = run_command("cli", ["survey", str(tmp_path)], timeout=30)
    except subprocess.TimeoutExpired:
        pytest.fail("the survey blocked on the FIFO instead of reporting it")
    else:
        assert result.returncode == 0, result.stderr
        assert "Bank  CroBank.dat is not a regular file" in result.stdout
        assert "Stru  01.19" in result.stdout


def test_survey_command_counts_a_fifo_as_unreadable_instead_of_blocking_on_it(tmp_path: Path) -> None:
    write_header_only_datafile(tmp_path / "db", "Stru")
    os.mkfifo(tmp_path / "db" / "CroBank.dat")

    try:
        result = run_command("cli", ["survey", "--counts", str(tmp_path)], timeout=30)
    except subprocess.TimeoutExpired:
        pytest.fail("the survey blocked on the FIFO instead of counting it")
    else:
        assert result.returncode == 0, result.stderr
        assert "unreadable files: 1" in result.stdout


def test_survey_command_reports_a_directory_named_like_a_datafile(tmp_path: Path) -> None:
    write_header_only_datafile(tmp_path / "db", "Bank")
    (tmp_path / "db" / "CroStru.dat").mkdir()

    result = run_command("cli", ["survey", str(tmp_path)])

    assert result.returncode == 0, result.stderr
    assert "Stru  CroStru.dat is not a regular file" in result.stdout
    assert "Bank  01.19" in result.stdout


def test_survey_command_prints_a_directory_name_that_is_not_valid_utf8(tmp_path: Path) -> None:
    directory = os.fsdecode(bytes(tmp_path) + b"/db\xff\xfe")
    os.mkdir(os.fsencode(directory))
    write_header_only_datafile(Path(directory), "Bank")

    result = run_command("cli", ["survey", str(tmp_path)])

    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr
    assert "db" in result.stdout
    assert "Bank  01.19" in result.stdout


def test_survey_command_rejects_a_list_file_that_is_not_text(tmp_path: Path) -> None:
    list_file = tmp_path / "databases.bin"
    list_file.write_bytes(bytes(range(256)) * 16)

    result = run_command("cli", ["survey", "--list", str(list_file)])

    assert result.returncode == 2
    assert "Traceback" not in result.stderr


def test_survey_command_reads_a_list_file_of_cp1251_paths(tmp_path: Path) -> None:
    directory = os.fsdecode(bytes(tmp_path) + "/база".encode("cp1251"))
    os.mkdir(os.fsencode(directory))
    write_header_only_datafile(Path(directory), "Bank")
    list_file = tmp_path / "databases.txt"
    list_file.write_bytes(os.fsencode(directory) + b"\n")

    result = run_command("cli", ["survey", "--list", str(list_file)])

    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr
    assert "Bank  01.19" in result.stdout
