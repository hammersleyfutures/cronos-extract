# ABOUTME: Tests for the diagnostics of the cronos_extract API: their kinds, the capped log and the record number set.
# ABOUTME: Pins the kind names Phase 2's JSON output relies on and the memory bounds on hostile databases.
import contextlib
import dataclasses
from collections.abc import Callable, Sequence

import pytest
from cronos_builder import TEST_DB

from cronos_extract import (
    CronosError,
    DatabaseDefinitionError,
    Diagnostic,
    DiagnosticKind,
    NotACronosFile,
    UnsupportedVersion,
)
from cronos_extract import open as open_bank
from cronos_extract._api.diagnostics import DIAGNOSTICS_KEPT, DiagnosticLog, RecordNumbers


def corrupt(number: int) -> Diagnostic:
    return Diagnostic(DiagnosticKind.CORRUPT_RECORD, "corrupt", file="CroBank.dat", record=number)


def raise_corrupt() -> None:
    """Raise the ValueError a reader raises for a corrupt record."""
    raise ValueError("corrupt")


def test_the_diagnostic_kinds_have_stable_snake_case_values() -> None:
    assert [kind.value for kind in DiagnosticKind] == [
        "corrupt_record",
        "checksum_mismatch",
        "undecodable_field",
        "invalid_value",
        "undecodable_table",
        "unsupported_table",
        "unexpected_structure",
        "unresolved_file_reference",
        "unreadable_file",
        "unused_kod",
    ]
    assert DiagnosticKind.CORRUPT_RECORD == "corrupt_record"


def test_a_diagnostic_is_frozen_and_its_location_fields_default_to_none() -> None:
    diagnostic = Diagnostic(DiagnosticKind.UNUSED_KOD, "unused")

    assert (diagnostic.file, diagnostic.table, diagnostic.record, diagnostic.field) == (None, None, None, None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        diagnostic.message = "changed"  # ty: ignore[invalid-assignment]


def test_the_log_keeps_the_first_diagnostics_and_counts_every_one() -> None:
    log = DiagnosticLog(None)

    for number in range(1, DIAGNOSTICS_KEPT + 2):
        log.record(corrupt(number))

    assert DIAGNOSTICS_KEPT == 1000
    assert len(log.kept) == 1000
    assert (log.kept[0].record, log.kept[-1].record) == (1, 1000)
    assert log.counts[DiagnosticKind.CORRUPT_RECORD] == 1001


def test_the_log_passes_each_diagnostic_to_the_callback_after_keeping_and_counting_it() -> None:
    seen: list[tuple[Diagnostic, int, int]] = []

    def on_diagnostic(diagnostic: Diagnostic) -> None:
        seen.append((diagnostic, len(log.kept), log.counts[diagnostic.kind]))

    log = DiagnosticLog(on_diagnostic)
    log.record(corrupt(1))
    log.record(corrupt(2))

    assert seen == [(corrupt(1), 1, 1), (corrupt(2), 2, 2)]


def test_an_exception_from_the_callback_reaches_the_caller_after_the_diagnostic_is_counted() -> None:
    class StopReading(Exception):
        pass

    def on_diagnostic(diagnostic: Diagnostic) -> None:
        raise StopReading

    log = DiagnosticLog(on_diagnostic)
    with pytest.raises(StopReading):
        log.record(corrupt(1))

    assert log.counts[DiagnosticKind.CORRUPT_RECORD] == 1


class StopReading(Exception):
    pass


def stopping_callback(calls: list[Diagnostic], stop: BaseException) -> Callable[[Diagnostic], None]:
    """A callback that notes each diagnostic and raises `stop` on the first only."""

    def on_diagnostic(diagnostic: Diagnostic) -> None:
        calls.append(diagnostic)
        if len(calls) == 1:
            raise stop

    return on_diagnostic


def test_outside_the_guard_a_caught_callback_exception_leaves_recording_unchanged() -> None:
    calls: list[Diagnostic] = []
    log = DiagnosticLog(stopping_callback(calls, StopReading()))
    with pytest.raises(StopReading):
        log.record(corrupt(1))

    log.record(corrupt(2))

    assert (list(log.kept), log.counts[DiagnosticKind.CORRUPT_RECORD], calls) == (
        [corrupt(1), corrupt(2)],
        2,
        [corrupt(1), corrupt(2)],
    )


def test_the_guard_raises_a_swallowed_callback_exception_on_exit() -> None:
    stop = StopReading()
    log = DiagnosticLog(stopping_callback([], stop))

    # contextlib.suppress stands for an internal reader that catches broad exceptions and swallows the callback's.
    with pytest.raises(StopReading) as raised, log.guard_callback_errors(), contextlib.suppress(Exception):
        log.record(corrupt(1))

    assert raised.value is stop


def test_the_guard_raises_the_callback_exception_in_place_of_what_the_reader_raised() -> None:
    stop = StopReading()
    log = DiagnosticLog(stopping_callback([], stop))

    with pytest.raises(StopReading) as raised, log.guard_callback_errors():
        try:
            log.record(corrupt(1))
        except StopReading as e:
            raise ValueError("the reader relabels it") from e

    assert raised.value is stop


def test_inside_the_guard_recording_after_a_callback_exception_raises_it_again_and_keeps_nothing() -> None:
    calls: list[Diagnostic] = []
    stop = StopReading()
    log = DiagnosticLog(stopping_callback(calls, stop))

    with pytest.raises(StopReading), log.guard_callback_errors():
        with contextlib.suppress(StopReading):
            log.record(corrupt(1))
        with pytest.raises(StopReading) as raised:
            log.record(corrupt(2))
        assert raised.value is stop

    assert (list(log.kept), dict(log.counts), calls) == ([corrupt(1)], {DiagnosticKind.CORRUPT_RECORD: 1}, [corrupt(1)])


def test_after_the_guard_exits_with_a_callback_exception_the_log_records_normally() -> None:
    calls: list[Diagnostic] = []
    log = DiagnosticLog(stopping_callback(calls, StopReading()))
    with pytest.raises(StopReading), log.guard_callback_errors():
        log.record(corrupt(1))

    log.record(corrupt(2))
    with log.guard_callback_errors():
        log.record(corrupt(3))

    assert (list(log.kept), calls) == ([corrupt(1), corrupt(2), corrupt(3)], [corrupt(1), corrupt(2), corrupt(3)])


def test_the_guard_lets_a_reader_exception_through_when_the_callback_did_not_raise() -> None:
    log = DiagnosticLog(None)

    with pytest.raises(ValueError, match="corrupt"), log.guard_callback_errors():
        log.record(corrupt(1))
        raise_corrupt()

    assert list(log.kept) == [corrupt(1)]


def test_the_kept_diagnostics_are_a_read_only_sequence_that_grows() -> None:
    log = DiagnosticLog(None)
    kept = log.kept

    log.record(corrupt(1))
    log.record(corrupt(2))

    assert isinstance(kept, Sequence)
    assert not hasattr(kept, "append")
    assert list(kept) == [corrupt(1), corrupt(2)]
    assert kept[0:1] == (corrupt(1),)


def test_the_counts_hold_only_kinds_that_occurred() -> None:
    log = DiagnosticLog(None)
    counts = log.counts

    log.record(corrupt(1))
    log.record(Diagnostic(DiagnosticKind.UNUSED_KOD, "unused"))

    assert dict(counts) == {DiagnosticKind.CORRUPT_RECORD: 1, DiagnosticKind.UNUSED_KOD: 1}
    assert not hasattr(counts, "__setitem__")


def test_record_numbers_says_whether_a_number_is_new() -> None:
    numbers = RecordNumbers(16)

    assert [numbers.add(1), numbers.add(16), numbers.add(1), numbers.add(9)] == [True, True, False, True]


def test_record_numbers_needs_one_bit_per_record() -> None:
    numbers = RecordNumbers(8_000_000)

    assert numbers.add(8_000_000)
    assert len(numbers._bits) <= 1_000_001


def test_every_exception_is_a_cronos_error() -> None:
    for error in (NotACronosFile, UnsupportedVersion, DatabaseDefinitionError):
        assert issubclass(error, CronosError)
    assert issubclass(CronosError, Exception)


def test_a_raising_callback_escapes_the_table_definition_reader() -> None:
    class StopAtStructure(Exception):
        pass

    seen: list[Diagnostic] = []

    def on_diagnostic(diagnostic: Diagnostic) -> None:
        seen.append(diagnostic)
        if diagnostic.kind is DiagnosticKind.UNEXPECTED_STRUCTURE:
            raise StopAtStructure

    with pytest.raises(StopAtStructure):
        open_bank(TEST_DB, on_diagnostic=on_diagnostic)

    assert [diagnostic.message for diagnostic in seen] == ["Base000: FieldDefinition Section 2 not marked with a 2"]
