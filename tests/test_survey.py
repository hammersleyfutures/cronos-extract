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
