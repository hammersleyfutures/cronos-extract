# ABOUTME: Diagnostics: the problems the cronos_extract API survives while reading, such as a corrupt record.
# ABOUTME: DiagnosticLog keeps the first few, counts all and passes each to a callback, so memory stays bounded.
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import overload, override

# How many diagnostics a bank keeps; counts and the callback cover every one.
DIAGNOSTICS_KEPT = 1000


class DiagnosticKind(StrEnum):
    """What kind of problem a Diagnostic reports. Later versions may add kinds."""

    CORRUPT_RECORD = "corrupt_record"
    UNDECODABLE_FIELD = "undecodable_field"
    INVALID_VALUE = "invalid_value"
    UNDECODABLE_TABLE = "undecodable_table"
    UNSUPPORTED_TABLE = "unsupported_table"
    UNEXPECTED_STRUCTURE = "unexpected_structure"
    UNRESOLVED_FILE_REFERENCE = "unresolved_file_reference"
    UNREADABLE_FILE = "unreadable_file"
    UNUSED_KOD = "unused_kod"


@dataclass(frozen=True)
class Diagnostic:
    """
    A problem found while reading, which reading survived.

    `file` is a canonical file name such as "CroBank.dat", `table` a table name, `record` a CroBank record number
    and `field` a field name, each None when it does not apply. The message never holds record data.
    """

    kind: DiagnosticKind
    message: str
    file: str | None = None
    table: str | None = None
    record: int | None = None
    field: str | None = None


class DiagnosticsView(Sequence[Diagnostic]):
    """A read-only view of a list of diagnostics, which grows as the list does."""

    def __init__(self, diagnostics: list[Diagnostic]) -> None:
        self._diagnostics = diagnostics

    @overload
    def __getitem__(self, index: int) -> Diagnostic: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[Diagnostic, ...]: ...

    @override
    def __getitem__(self, index: int | slice) -> Diagnostic | tuple[Diagnostic, ...]:
        if isinstance(index, slice):
            return tuple(self._diagnostics[index])
        return self._diagnostics[index]

    @override
    def __len__(self) -> int:
        return len(self._diagnostics)

    @override
    def __repr__(self) -> str:
        return f"DiagnosticsView({self._diagnostics!r})"


class DiagnosticLog:
    """
    Collects a bank's diagnostics.

    It keeps the first DIAGNOSTICS_KEPT of them, counts every one by kind, and passes every one to `on_diagnostic`
    after keeping and counting it. An exception from `on_diagnostic` reaches the code that recorded the diagnostic.
    """

    def __init__(self, on_diagnostic: Callable[[Diagnostic], object] | None) -> None:
        self._kept: list[Diagnostic] = []
        self._counts: Counter[DiagnosticKind] = Counter()
        self._on_diagnostic = on_diagnostic
        self._callback_error: BaseException | None = None
        self.kept: Sequence[Diagnostic] = DiagnosticsView(self._kept)
        self.counts: Mapping[DiagnosticKind, int] = MappingProxyType(self._counts)

    def record(self, diagnostic: Diagnostic) -> None:
        """
        Keep `diagnostic` while fewer than DIAGNOSTICS_KEPT are kept, count it, and pass it to the callback.

        An exception from the callback is remembered before it is raised, because the internal readers catch broad
        exceptions; raise_callback_error raises it again after them. While it is remembered, recording raises it again
        and keeps nothing, so a reader's handler cannot add a diagnostic after the caller asked to stop.
        """
        if self._callback_error is not None:
            raise self._callback_error
        if len(self._kept) < DIAGNOSTICS_KEPT:
            self._kept.append(diagnostic)
        self._counts[diagnostic.kind] += 1
        if self._on_diagnostic is not None:
            try:
                self._on_diagnostic(diagnostic)
            except BaseException as e:
                self._callback_error = e
                raise

    def raise_callback_error(self) -> None:
        """
        Raise the remembered exception from the callback, if any, and forget it.

        Internal readers catch broad exceptions, so code that calls them uses this to pass a caller's request to stop
        on to the caller unchanged.
        """
        error = self._callback_error
        if error is not None:
            self._callback_error = None
            raise error


class RecordNumbers:
    """A set of record numbers from 0 to `size`, held as one bit each, so marking every record stays small."""

    def __init__(self, size: int) -> None:
        self._bits = bytearray(size // 8 + 1)

    def add(self, number: int) -> bool:
        """Add `number`, returning whether it was not in the set before."""
        index, bit = divmod(number, 8)
        if self._bits[index] >> bit & 1:
            return False
        self._bits[index] |= 1 << bit
        return True
