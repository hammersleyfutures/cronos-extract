# ABOUTME: How the command reports problems on stderr: escaped text, one line per problem, and a summary of counts.
# ABOUTME: Also Failure, which a subcommand raises to end with one Error line and an exit status.
import io
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Self, TextIO, override

from .._api.bank import DEFINITION_HINT
from .._api.diagnostics import Diagnostic, DiagnosticKind
from ..Database import KOD_HINT

# Kinds the command reports itself, for problems of writing the output rather than of reading the database.
DUPLICATE_TABLE = "duplicate_table"
REPLACED_NUL = "replaced_nul"
COMMAND_KINDS = (DUPLICATE_TABLE, REPLACED_NUL)
# The order of the summary: the API's kinds as DiagnosticKind declares them, then the command's own.
KIND_ORDER = (*(kind.value for kind in DiagnosticKind), *COMMAND_KINDS)
# The surrogates that the surrogateescape error handler uses for the bytes 0x80 to 0xff of an undecodable name.
ESCAPED_BYTES = range(0xDC80, 0xDD00)


def escape(text: str, keep: str = "") -> str:
    """
    `text` with every character that is not printable written as an escape, except those in `keep`.

    A byte that a file name held surrogate-escaped is written \\xNN; any other character as \\xNN, \\uNNNN or
    \\UNNNNNNNN. Control characters, line breaks and format characters such as a right-to-left override are all
    unprintable, so an escaped text is one line and cannot carry a terminal control sequence.
    """
    escaped = []
    for char in text:
        code = ord(char)
        if char.isprintable() or char in keep:
            escaped.append(char)
        elif code in ESCAPED_BYTES:
            escaped.append(f"\\x{code - 0xDC00:02x}")
        elif code <= 0xFF:
            escaped.append(f"\\x{code:02x}")
        elif code <= 0xFFFF:
            escaped.append(f"\\u{code:04x}")
        else:
            escaped.append(f"\\U{code:08x}")
    return "".join(escaped)


class EscapingStream(io.TextIOBase):
    """
    A text stream that writes to `stream` everything it is given, escaped as `escape` does, except line breaks.

    main() puts it in place of sys.stderr, so that text the internal readers print there is escaped too.
    """

    def __init__(self, stream: TextIO) -> None:
        super().__init__()
        self._stream = stream

    @override
    def write(self, s: str, /) -> int:
        self._stream.write(escape(s, keep="\n"))
        return len(s)

    @override
    def flush(self) -> None:
        self._stream.flush()

    @override
    def writable(self) -> bool:
        return True

    @override
    def isatty(self) -> bool:
        return self._stream.isatty()

    @override
    def fileno(self) -> int:
        return self._stream.fileno()


@dataclass(frozen=True)
class Problem:
    """
    A diagnostic from the API, or a problem the command found itself, in the shape both are reported in.

    `kind` is a DiagnosticKind value or one of COMMAND_KINDS; the other fields are as in Diagnostic.
    """

    kind: str
    message: str
    file: str | None = None
    table: str | None = None
    record: int | None = None
    field: str | None = None

    @classmethod
    def from_diagnostic(cls, diagnostic: Diagnostic) -> Self:
        return cls(
            diagnostic.kind.value,
            diagnostic.message,
            diagnostic.file,
            diagnostic.table,
            diagnostic.record,
            diagnostic.field,
        )


def location(problem: Problem) -> str:
    """
    Where `problem` is: its table, record and field when it names a table, else its file, record and field.

    A table's records are all in CroBank, so the file is left out when a table is named.
    """
    parts = []
    if problem.table is not None:
        parts.append(f'table "{problem.table}"')
        if problem.record is not None:
            parts.append(f"record {problem.record}")
    else:
        where = [] if problem.file is None else [problem.file]
        if problem.record is not None:
            where.append(f"record {problem.record}")
        if where:
            parts.append(" ".join(where))
    if problem.field is not None:
        parts.append(f'field "{problem.field}"')
    return ", ".join(parts)


def format_problem(problem: Problem) -> str:
    """The stderr line for `problem`, escaped so that it is one line and holds no terminal control sequence."""
    where = location(problem)
    if where:
        return escape(f"warning: {problem.kind}: {where}: {problem.message}")
    return escape(f"warning: {problem.kind}: {problem.message}")


class Report:
    """Prints each problem on stderr as it is reported, and counts them by kind for the summary."""

    def __init__(self) -> None:
        self._counts: Counter[str] = Counter()

    def problem(self, problem: Problem) -> None:
        self._counts[problem.kind] += 1
        print(format_problem(problem), file=sys.stderr)

    def diagnostic(self, diagnostic: Diagnostic) -> None:
        """Report an API diagnostic; this is what the command passes to cronos_extract.open as on_diagnostic."""
        self.problem(Problem.from_diagnostic(diagnostic))

    @property
    def total(self) -> int:
        """The number of problems reported."""
        return sum(self._counts.values())

    def summary(self) -> str:
        """The counts of problems by kind, as one line."""
        total = self.total
        if not total:
            return "no diagnostics"
        noun = "diagnostic" if total == 1 else "diagnostics"
        counts = ", ".join(f"{self._counts[kind]} {kind}" for kind in KIND_ORDER if self._counts[kind])
        return f"{total} {noun}: {counts}"

    def print_summary(self) -> None:
        """Print the summary on stderr, after a blank line when problem lines precede it."""
        if self.total:
            print(file=sys.stderr)
        print(self.summary(), file=sys.stderr)


class Failure(Exception):
    """A problem that ends the command: main prints "Error: " and the message on stderr and exits with `status`."""

    def __init__(self, message: str, status: int = 1) -> None:
        super().__init__(message)
        self.status = status


def error_message(error: BaseException) -> str:
    """The text of the Error line for `error`, with the API's hint about recovering a KOD replaced by the command's."""
    return str(error).replace(DEFINITION_HINT, KOD_HINT)


def print_error(message: str) -> None:
    """Print the one Error line that ends a command that failed."""
    print(f"Error: {message}", file=sys.stderr)
