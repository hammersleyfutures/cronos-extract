# ABOUTME: Tests for crodump's inspection subcommands (recdump, destruct) run as subprocesses.
# ABOUTME: Uses the sample database in test_data.
from cli import run_command
from cronos_builder import TEST_DB


def test_recdump_stops_at_the_last_record_even_with_debug() -> None:
    result = run_command("crodump", ["--debug", "recdump", str(TEST_DB)])

    assert result.returncode == 0, result.stderr
    assert "unpack" not in result.stdout
