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
