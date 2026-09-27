# ABOUTME: open() and the Bank and Table classes, the public way to read a CronosPro database.
# ABOUTME: Drives the internal Database, TableDefinition and Datafile readers and reports problems as diagnostics.
import os
from array import array
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import ExitStack
from pathlib import Path
from types import TracebackType
from typing import Self, override

from .._diagnostic import STRU_FILE, for_table_definition
from ..Database import Database
from ..Datafile import Datafile
from ..Datamodel import TableDefinition, describe_error, is_table_key, undecodable_table
from ..koddecoder import kod_fits_header
from .datafiles import database_directory, list_directory, open_datafile, optional_file_info
from .diagnostics import Diagnostic, DiagnosticKind, DiagnosticLog, RecordNumbers
from .errors import DatabaseDefinitionError, WrongKod
from .info import FileInfo
from .kod import Kod, kod_coder
from .values import EmbeddedFile, FieldDefinition, FileReference, Record, decode_record

DEFAULT_KOD = Kod.default()
BANK_FILE = "CroBank.dat"
# Record data holds the table id in one byte.
LARGEST_TABLE_ID = 255
FIELD_TYPE_SYSTEM_NUMBER = 0
DEFINITION_HINT = (
    "If the KOD used to read this database is not its own, the definition decodes as garbage; "
    "cronos_extract.crack_kod can recover the database's KOD."
)
STRU_KOD_HINT = 'cronos_extract.crack_kod(path, "strucrack") can recover the database\'s KOD.'
BANK_KOD_HINT = 'cronos_extract.crack_kod(path, "dbcrack") can recover the database\'s KOD.'


class Table:
    """A table of a bank: its id, names and field definitions, and its records, read lazily."""

    def __init__(self, bank: "Bank", definition: TableDefinition) -> None:
        self._bank = bank
        self._definition = definition
        self._fields = tuple(FieldDefinition(field.name, field.typ) for field in definition.fields)

    @property
    def id(self) -> int:
        """The table id, which the first byte of each of its CroBank records holds."""
        return self._definition.tableid

    @property
    def name(self) -> str:
        return self._definition.tablename

    @property
    def abbreviation(self) -> str:
        return self._definition.abbrev

    @property
    def fields(self) -> tuple[FieldDefinition, ...]:
        """The field definitions; the first is the system number, and each describes the record field at its index."""
        return self._fields

    def records(self) -> Iterator[Record]:
        """
        The table's records in CroBank order, read lazily: each step reads CroBank only up to the table's next record.

        The first generator of any table to reach a CroBank record indexes it for every table, so a table read after
        another reads only its own records.

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

    def __init__(
        self,
        directory: Path,
        database: Database,
        bank_file: Datafile,
        info: tuple[FileInfo, ...],
        log: DiagnosticLog,
        deleted_records: int,
    ) -> None:
        self._directory = directory
        self._database = database
        self._bank_file = bank_file
        self._info = info
        self._log = log
        self._deleted_records = deleted_records
        self._closed = False
        self._tables: tuple[Table, ...] = ()
        self._files_table_id: int | None = None
        self._files_abbreviation: str | None = None
        self._corrupt_records = RecordNumbers(self._bank_file.nrofrecords)
        self._checksum_mismatches = RecordNumbers(self._bank_file.nrofrecords)
        self._unsupported_tables: set[int] = set()
        # The CroBank index: the next record number no scan step has indexed yet, and the live records found so far
        # per table-id byte, in CroBank order.
        self._scan_position = 1
        self._index: dict[int, array[int]] = {}
        fits_in_four_bytes = array("I").itemsize == 4 and self._bank_file.nrofrecords < 2**32
        self._index_typecode = "I" if fits_in_four_bytes else "Q"

    @property
    def tables(self) -> tuple[Table, ...]:
        """The tables, in database-definition order, without the Files table."""
        return self._tables

    @property
    def info(self) -> tuple[FileInfo, ...]:
        """The Cro files found, in the order Stru, Bank, Index, Sys."""
        return self._info

    @property
    def deleted_records(self) -> int:
        """
        The number of deleted records CroBank's .tad header lists, at most its number of entries; they are not read.
        """
        return self._deleted_records

    @property
    def diagnostics(self) -> Sequence[Diagnostic]:
        """The first 1,000 diagnostics, a read-only sequence that grows while reading."""
        return self._log.kept

    @property
    def diagnostic_counts(self) -> Mapping[DiagnosticKind, int]:
        """
        The number of diagnostics of each kind that occurred, counting every one.

        A kind that never occurred reads as 0, but is not `in` the mapping and is not among its keys.
        """
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

    def files(self) -> Iterator[EmbeddedFile]:
        """
        The files stored in the Files table, in CroBank order, without names, read lazily: each step reads CroBank
        only up to the Files table's next record.

        The first generator of any table to reach a CroBank record indexes it for every table, so files read after
        a table read only the Files table's records.

        Raises ValueError when the bank is closed, now or at any later step.
        """
        self._check_open()
        return self._files()

    def read_file(self, reference: FileReference) -> EmbeddedFile | None:
        """
        The file `reference` refers to, named after the reference.

        Returns None, recording unresolved_file_reference, when the reference's record is not a readable record of
        the Files table. The diagnostic is located at the reference's table, referrer and field. Raises ValueError
        when the bank is closed.
        """
        self._check_open()
        record = reference.record
        if record is None:
            return self._unresolved(reference, "the file cannot be read: its record number is not a number")
        cannot_be_read = f"the file in CroBank record {record} cannot be read"
        if self._files_table_id is None:
            return self._unresolved(reference, f"{cannot_be_read}: the database has no Files table")
        if not 1 <= record <= self._bank_file.nrofrecords:
            return self._unresolved(reference, f"{cannot_be_read}: CroBank has no such record")
        data = self._read(record)
        if data is None:
            return self._unresolved(reference, f"{cannot_be_read}: the record is deleted or corrupt")
        if not data or data[0] != self._files_table_id:
            return self._unresolved(reference, f"{cannot_be_read}: the record is not in the Files table")
        name = f"{reference.name}.{reference.extension}" if reference.extension else reference.name
        return EmbeddedFile(record, data[1:], name)

    def _unresolved(self, reference: FileReference, message: str) -> None:
        self._log.record(
            Diagnostic(
                DiagnosticKind.UNRESOLVED_FILE_REFERENCE,
                message,
                file=BANK_FILE,
                table=reference.table,
                record=reference.referrer,
                field=reference.field,
            )
        )

    def _read(self, number: int) -> bytes | None:
        """
        CroBank record `number`, or None when it is deleted or cannot be read.

        A record that cannot be read is reported as corrupt_record the first time only. A record whose compressed
        data fails its CRC-32 is returned and reported as checksum_mismatch the first time only. OSError propagates.
        Raises ValueError when the bank is closed.
        """
        self._check_open()
        try:
            parts = self._bank_file.read_record(number)
        except OSError:
            raise
        except Exception as e:
            if self._corrupt_records.add(number):
                self._log.record(
                    Diagnostic(
                        DiagnosticKind.CORRUPT_RECORD,
                        f"CroBank record {number} is corrupt and is skipped: {describe_error(e)}",
                        file=BANK_FILE,
                        record=number,
                    )
                )
            return None
        if parts is None:
            return None
        mismatched = len(parts.mismatched_chunks)
        if mismatched and self._checksum_mismatches.add(number):
            chunks = "chunk" if mismatched == 1 else "chunks"
            self._log.record(
                Diagnostic(
                    DiagnosticKind.CHECKSUM_MISMATCH,
                    f"CroBank record {number} has {mismatched} compressed {chunks} whose checksum does not match; "
                    "the record is kept as it decompressed",
                    file=BANK_FILE,
                    record=number,
                )
            )
        return parts.data

    def _records(self, table: Table) -> Iterator[Record]:
        if table.id > LARGEST_TABLE_ID:
            if table.id not in self._unsupported_tables:
                self._unsupported_tables.add(table.id)
                self._log.record(
                    Diagnostic(
                        DiagnosticKind.UNSUPPORTED_TABLE,
                        f"the table has id {table.id}, but this release reads only tables with ids up to "
                        f"{LARGEST_TABLE_ID}, so its records are not read",
                        file=STRU_FILE,
                        table=table.name,
                    )
                )
            return
        for number, data in self._table_records(table.id):
            record = decode_record(number, table.name, table.fields, table._definition.fields, data[1:])
            for diagnostic in record.diagnostics:
                self._log.record(diagnostic)
            yield record

    def _files(self) -> Iterator[EmbeddedFile]:
        if self._files_table_id is None:
            return
        for number, data in self._table_records(self._files_table_id):
            yield EmbeddedFile(number, data[1:], None)

    def _table_records(self, table_id: int) -> Iterator[tuple[int, bytes]]:
        """
        Each CroBank record number of table `table_id` with its data, table-id byte included, in CroBank order.

        Records already indexed are read again from CroBank; past them, each step advances the shared scan by one
        record and indexes it under its table-id byte, so the first generator to reach a record indexes it for every
        table. The scan position moves on only after its record is indexed, so an exception during a step leaves
        the index whole, and a step whose record a re-entrant call (from on_diagnostic) indexed meanwhile does not
        index it again.
        """
        listed = self._listed(table_id)
        taken = 0
        while True:
            if taken < len(listed):
                number = listed[taken]
                taken += 1
                data = self._read(number)
                if data and data[0] == table_id:
                    yield number, data
                continue
            number = self._scan_position
            if number > self._bank_file.nrofrecords:
                return
            data = self._read(number)
            if self._scan_position != number:
                # A re-entrant call from on_diagnostic indexed this record meanwhile.
                continue
            if data:
                self._listed(data[0]).append(number)
            self._scan_position = number + 1
            if data and data[0] == table_id:
                # The record just appended to `listed`.
                taken += 1
                yield number, data

    def _listed(self, table_id: int) -> array[int]:
        """The index's array of record numbers for `table_id`, created empty the first time it is asked for."""
        listed = self._index.get(table_id)
        if listed is None:
            created: array[int] = array(self._index_typecode)
            listed = self._index[table_id] = created
        return listed

    def _load_tables(self) -> None:
        """Decode the database definition and every table definition in it."""
        with self._log.guard_callback_errors():
            try:
                definition = self._database.read_db_definition()
            except OSError:
                raise
            except Exception as e:
                raise DatabaseDefinitionError(
                    f"the database definition in {STRU_FILE} of {self._directory} cannot be decoded: "
                    f"{describe_error(e)}. {DEFINITION_HINT}"
                ) from e
        tables = []
        for key, value in definition.items():
            if not is_table_key(key):
                continue
            with self._log.guard_callback_errors():
                try:
                    table_definition = TableDefinition(
                        value,
                        definition.get("BaseImage" + key[4:], b""),
                        report=for_table_definition(self._log.record, key),
                    )
                except Exception as e:
                    self._log.record(undecodable_table(key, e))
                    continue
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


def refuse_a_kod_the_header_rejects(datafile: Datafile, directory: Path, hint: str) -> None:
    """Raise WrongKod, ending with `hint`, when `datafile`'s header shows that the KOD decoding it is not its own."""
    if datafile.kod is not None and kod_fits_header(datafile.header, datafile.kod) is False:
        raise WrongKod(
            f"Cro{datafile.name}.dat in {directory} has a header that shows the KOD used is not the database's KOD. "
            f"{hint}"
        )


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
    CroStru and CroBank indexes from disk instead of memory; the table index of CroBank holds about 4 bytes per live
    CroBank record (8 where 4 cannot hold its record numbers), whether or not `compact` is set. `on_diagnostic` is
    called with each diagnostic as it is recorded. The bank's `deleted_records` is the number of deleted records
    CroBank's .tad header lists, which are not read; a header listing more than the .tad has entries is reported as
    unexpected_structure, and `deleted_records` is then the number of entries.

    Raises OSError when `path` does not exist, is not a directory or cannot be listed; TypeError for a bytes path;
    NotACronosFile or UnsupportedVersion when CroStru or CroBank cannot be read; WrongKod when the header of a
    KOD-encoded v4 CroStru or CroBank, checked in that order, shows that `kod` is not the database's KOD, which would
    decode its records as garbage; DatabaseDefinitionError when the database definition cannot be decoded.
    """
    directory = database_directory(path)
    names = list_directory(directory)
    log = DiagnosticLog(on_diagnostic)
    with ExitStack() as stack:
        stru, stru_info = open_datafile(directory, names, "Stru", compact=compact, kod=kod, log=log)
        stack.callback(stru.close)
        refuse_a_kod_the_header_rejects(stru, directory, STRU_KOD_HINT)
        bank_file, bank_info = open_datafile(directory, names, "Bank", compact=compact, kod=kod, log=log)
        stack.callback(bank_file.close)
        refuse_a_kod_the_header_rejects(bank_file, directory, BANK_KOD_HINT)
        deleted_records = bank_file.nrdeleted
        if deleted_records > bank_file.nrofrecords:
            log.record(
                Diagnostic(
                    DiagnosticKind.UNEXPECTED_STRUCTURE,
                    f"the .tad header lists {deleted_records} deleted records, more than its "
                    f"{bank_file.nrofrecords} entries",
                    file=BANK_FILE,
                )
            )
            deleted_records = bank_file.nrofrecords
        optional = [optional_file_info(directory, names, base, log) for base in ("Index", "Sys")]
        database = Database.from_datafiles(str(directory), compact, kod_coder(kod), stru, bank_file, log.record)
        bank = Bank(
            directory,
            database,
            bank_file,
            (stru_info, bank_info, *(info for info in optional if info is not None)),
            log,
            deleted_records,
        )
        bank._load_tables()
        stack.pop_all()
    return bank
