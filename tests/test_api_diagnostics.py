# ABOUTME: Tests for the diagnostics of the cronos_extract API: their kinds, the capped log and the record number set.
# ABOUTME: Pins the kind names Phase 2's JSON output relies on and the memory bounds on hostile databases.
import contextlib
import dataclasses
from collections.abc import Sequence

import pytest

from cronos_extract._api.diagnostics import (
    DIAGNOSTICS_KEPT,
    Diagnostic,
    DiagnosticKind,
    DiagnosticLog,
    RecordNumbers,
)
from cronos_extract._api.errors import CronosError, DatabaseDefinitionError, NotACronosFile, UnsupportedVersion


def corrupt(number: int) -> Diagnostic:
    return Diagnostic(DiagnosticKind.CORRUPT_RECORD, "corrupt", file="CroBank.dat", record=number)


def test_the_diagnostic_kinds_have_stable_snake_case_values() -> None:
    assert [kind.value for kind in DiagnosticKind] == [
        "corrupt_record",
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


def test_a_remembered_callback_exception_is_raised_again_once() -> None:
    class StopReading(Exception):
        pass

    stop = StopReading()

    def on_diagnostic(diagnostic: Diagnostic) -> None:
        raise stop

    log = DiagnosticLog(on_diagnostic)
    # An internal reader that catches broad exceptions swallows the first raise.
    with contextlib.suppress(StopReading):
        log.record(corrupt(1))

    with pytest.raises(StopReading) as raised:
        log.raise_callback_error()
    assert raised.value is stop
    log.raise_callback_error()


def test_while_a_callback_exception_is_remembered_recording_raises_it_again_and_keeps_nothing() -> None:
    class StopReading(Exception):
        pass

    calls: list[Diagnostic] = []

    def on_diagnostic(diagnostic: Diagnostic) -> None:
        calls.append(diagnostic)
        raise StopReading

    log = DiagnosticLog(on_diagnostic)
    with pytest.raises(StopReading):
        log.record(corrupt(1))
    with pytest.raises(StopReading):
        log.record(corrupt(2))

    assert (list(log.kept), calls) == ([corrupt(1)], [corrupt(1)])


def test_raise_callback_error_does_nothing_when_the_callback_did_not_raise() -> None:
    log = DiagnosticLog(None)
    log.record(corrupt(1))
    log.raise_callback_error()


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
