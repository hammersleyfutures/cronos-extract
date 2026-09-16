# ABOUTME: open() and the Bank and Table classes, the public way to read a CronosPro database.
# ABOUTME: Drives the internal Database, TableDefinition and Datafile readers and reports problems as diagnostics.
import os
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import ExitStack
from pathlib import Path
from types import TracebackType
from typing import Self, override

from ..Database import Database
from ..Datamodel import TableDefinition, describe_error
from .datafiles import database_directory, list_directory, open_datafile, optional_file_info, warn_into
from .diagnostics import Diagnostic, DiagnosticKind, DiagnosticLog
from .errors import DatabaseDefinitionError
from .info import FileInfo
from .kod import Kod, kod_coder
from .values import FieldDefinition, Record

DEFAULT_KOD = Kod.default()
STRU_FILE = "CroStru.dat"
FIELD_TYPE_SYSTEM_NUMBER = 0
DEFINITION_HINT = (
    "If the KOD used to read this database is not its own, the definition decodes as garbage; "
    "cronos_extract.crack_kod can recover the database's KOD."
)


def is_table_key(key: str) -> bool:
    """Whether a database definition key names a table definition: "Base" followed by digits."""
    return key.startswith("Base") and key[4:].isascii() and key[4:].isdigit()


class Table:
    """A table of a bank: its id, names and field definitions, and its records, read lazily."""

    def __init__(self, bank: "Bank", definition: TableDefinition) -> None:
        self._bank = bank
        self._definition = definition
        self._fields = tuple(FieldDefinition(field.name, field.typ) for field in definition.fields)

    @property
    def id(self) -> int:
        """The table id, which the first byte of each of its CroBank records holds."""
        return int(self._definition.tableid)

    @property
    def name(self) -> str:
        return str(self._definition.tablename)

    @property
    def abbreviation(self) -> str:
        return str(self._definition.abbrev)

    @property
    def fields(self) -> tuple[FieldDefinition, ...]:
        """The field definitions; the first is the system number, and each describes the record field at its index."""
        return self._fields

    def records(self) -> Iterator[Record]:
        """
        The table's records in CroBank order, read one CroBank record per step.

        Raises ValueError when the bank is closed, now or at any later step.
        """
        self._bank._check_open()
        return self._bank._records(self)

    @override
    def __repr__(self) -> str:
        return f"Table(id={self.id}, name={self.name!r})"


class Bank:
    """
    An open CronosPro database. Close it, or use it as a context manager, to close its files.

    A Bank is not thread-safe. Generators from one bank may be interleaved on one thread.
    """

    def __init__(self, directory: Path, database: Database, info: tuple[FileInfo, ...], log: DiagnosticLog) -> None:
        self._directory = directory
        self._database = database
        self._info = info
        self._log = log
        self._closed = False
        self._tables: tuple[Table, ...] = ()
        self._files_table_id: int | None = None
        self._files_abbreviation: str | None = None

    @property
    def tables(self) -> tuple[Table, ...]:
        """The tables, in database-definition order, without the Files table."""
        return self._tables

    @property
    def info(self) -> tuple[FileInfo, ...]:
        """The Cro files found, in the order Stru, Bank, Index, Sys."""
        return self._info

    @property
    def diagnostics(self) -> Sequence[Diagnostic]:
        """The first 1,000 diagnostics, a read-only sequence that grows while reading."""
        return self._log.kept

    @property
    def diagnostic_counts(self) -> Mapping[DiagnosticKind, int]:
        """The number of diagnostics of each kind that occurred, counting every one."""
        return self._log.counts

    @property
    def files_abbreviation(self) -> str | None:
        """The Files table's abbreviation, or None when the database has no Files table."""
        return self._files_abbreviation

    def close(self) -> None:
        """Close the bank's files. Closing a closed bank does nothing."""
        if not self._closed:
            self._closed = True
            self._database.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        self.close()

    @override
    def __repr__(self) -> str:
        return f"Bank({str(self._directory)!r})"

    def _check_open(self) -> None:
        if self._closed:
            raise ValueError(f"the bank in {self._directory} is closed")

    def _records(self, table: Table) -> Iterator[Record]:
        raise NotImplementedError("Task 10 reads records")

    def _load_tables(self) -> None:
        """Decode the database definition and every table definition in it."""
        try:
            definition = self._database.read_db_definition()
        except OSError:
            raise
        except Exception as e:
            self._log.raise_callback_error()
            raise DatabaseDefinitionError(
                f"the database definition in {STRU_FILE} of {self._directory} cannot be decoded: "
                f"{describe_error(e)}. {DEFINITION_HINT}"
            ) from e
        tables = []
        for key, value in definition.items():
            if not is_table_key(key):
                continue
            try:
                table_definition = TableDefinition(
                    value, definition.get("BaseImage" + key[4:], b""), warn_into(self._log, STRU_FILE, f"{key}: ")
                )
            except Exception as e:
                self._log.raise_callback_error()
                self._log.record(
                    Diagnostic(
                        DiagnosticKind.UNDECODABLE_TABLE,
                        f"{key} cannot be decoded and is left out: {describe_error(e)}",
                        file=STRU_FILE,
                    )
                )
                continue
            self._log.raise_callback_error()
            if key[4:] == "000":
                self._files_table_id = table_definition.tableid
                self._files_abbreviation = table_definition.abbrev
            elif not table_definition.fields or table_definition.fields[0].typ != FIELD_TYPE_SYSTEM_NUMBER:
                self._log.record(
                    Diagnostic(
                        DiagnosticKind.UNDECODABLE_TABLE,
                        f"{key} is left out: it does not start with the system number field",
                        file=STRU_FILE,
                        table=table_definition.tablename,
                    )
                )
            else:
                tables.append(Table(self, table_definition))
        self._tables = tuple(tables)


def open(
    path: str | os.PathLike[str],
    *,
    kod: Kod | None = DEFAULT_KOD,
    compact: bool = False,
    on_diagnostic: Callable[[Diagnostic], object] | None = None,
) -> Bank:
    """
    Open the CronosPro database in the directory `path`.

    `kod` is the KOD table to decode records with, or None to read them without KOD decoding. `compact` reads the
    CroStru and CroBank indexes from disk instead of memory. `on_diagnostic` is called with each diagnostic as it is
    recorded.

    Raises OSError when `path` does not exist, is not a directory or cannot be listed; TypeError for a bytes path;
    NotACronosFile or UnsupportedVersion when CroStru or CroBank cannot be read; DatabaseDefinitionError when the
    database definition cannot be decoded.
    """
    directory = database_directory(path)
    names = list_directory(directory)
    log = DiagnosticLog(on_diagnostic)
    with ExitStack() as stack:
        stru, stru_info = open_datafile(directory, names, "Stru", compact=compact, kod=kod, log=log)
        stack.callback(stru.close)
        bank_file, bank_info = open_datafile(directory, names, "Bank", compact=compact, kod=kod, log=log)
        stack.callback(bank_file.close)
        optional = [optional_file_info(directory, names, base, log) for base in ("Index", "Sys")]
        if (
            kod is not None
            and kod != DEFAULT_KOD
            and not any(info.own_kod and info.kod_encoded for info in (stru_info, bank_info))
        ):
            log.record(
                Diagnostic(
                    DiagnosticKind.UNUSED_KOD,
                    "the KOD given is not used: neither CroStru.dat nor CroBank.dat is encrypted with its own KOD",
                )
            )
        database = Database.from_datafiles(
            str(directory), compact, kod_coder(kod), stru, bank_file, warn_into(log, STRU_FILE)
        )
        bank = Bank(directory, database, (stru_info, bank_info, *(info for info in optional if info is not None)), log)
        bank._load_tables()
        stack.pop_all()
    return bank
