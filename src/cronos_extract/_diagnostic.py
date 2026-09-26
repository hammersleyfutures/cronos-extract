# ABOUTME: Diagnostic and DiagnosticKind: a problem that reading survived, and the kinds there are.
# ABOUTME: The internal readers report them through a Reporter; the public API re-exports both types.
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum


class DiagnosticKind(StrEnum):
    """What kind of problem a Diagnostic reports. Later versions may add kinds."""

    CORRUPT_RECORD = "corrupt_record"
    CHECKSUM_MISMATCH = "checksum_mismatch"
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

    `file` is a canonical file name such as "CroBank.dat", `table` a table name, `record` a record number in `file`
    (in CroBank when a table is named) and `field` a field name, each None when it does not apply. The message never
    holds CroBank record data.
    """

    kind: DiagnosticKind
    message: str
    file: str | None = None
    table: str | None = None
    record: int | None = None
    field: str | None = None


# A callback that receives each problem a reader survives.
type Reporter = Callable[[Diagnostic], object]

STRU_FILE = "CroStru.dat"


def for_table_definition(report: Reporter, key: str) -> Reporter:
    """
    A Reporter for the problems of the table definition stored under `key`, such as "Base001".

    It names CroStru.dat as the file and prefixes each message with the key, as `export` has always shown them, then
    passes the problem to `report`.
    """

    def report_definition_problem(diagnostic: Diagnostic) -> None:
        report(replace(diagnostic, file=STRU_FILE, message=f"{key}: {diagnostic.message}"))

    return report_definition_problem
