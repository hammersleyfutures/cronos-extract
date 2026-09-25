# ABOUTME: The CSV export: a directory holding a CSV file per table, the Files table's files and the referenced files.
# ABOUTME: Every name is safe and unique within the directory; referenced files are written as their records are.
import csv
import os
from _csv import Writer as RowWriter
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from .._api.bank import Bank, Table
from .._api.values import FieldValue, FileReference, Record
from .names import unique_file_name
from .report import DUPLICATE_TABLE, STRU_FILE, Problem

FIELD_TYPE_FILE = 6
REFERENCED_DIRECTORY = "Files-Referenced"
# The number Files-Referenced is claimed with: no table id is negative, so no other name can be taken for it.
REFERENCED_NUMBER = -1


class CsvWriter:
    """
    Writes an export into `directory`, which exists and is empty.

    Each table goes to <table name>.csv, whose header row holds the field names and whose cells hold each field's
    text as the API decoded it. With `files`, the file a record refers to goes to Files-Referenced/ under its own
    name as the record is written, and every file of the Files table goes to Files-<abbreviation>/, named by its
    CroBank record number, at the end.
    """

    def __init__(
        self,
        directory: Path,
        bank: Bank,
        on_problem: Callable[[Problem], None],
        *,
        delimiter: str,
        files: bool,
    ) -> None:
        self._directory = directory
        self._bank = bank
        self._on_problem = on_problem
        self._delimiter = delimiter
        self._files = files
        self._names: dict[str, int] = {REFERENCED_DIRECTORY.casefold(): REFERENCED_NUMBER}
        self._files_directory = self._claim_files_directory() if files else None
        self._referenced_names: dict[str, int] = {}
        self._referenced_created = False
        self._stream: TextIO | None = None
        self._rows: RowWriter | None = None

    def table(self, table: Table) -> bool:
        """Write the CSV file's header, or report duplicate_table and refuse the table."""
        self._close_table()
        name = unique_file_name(table.name, "csv", table.id, self._names)
        if name is None:
            self._on_problem(
                Problem(
                    DUPLICATE_TABLE,
                    "its CSV file name and table id are those of a table already written, so it is skipped",
                    file=STRU_FILE,
                    table=table.name,
                )
            )
            return False
        # Kept open across record() calls until the next table() or close(); a context manager cannot span those.
        self._stream = open(self._directory / name, "x", encoding="utf-8", newline="")  # noqa: SIM115
        self._rows = csv.writer(self._stream, delimiter=self._delimiter)
        self._rows.writerow([field.name for field in table.fields])
        return True

    def record(self, table: Table, record: Record) -> None:
        """Write `record`; called only after table() accepted `table`, so self._rows is not None."""
        assert self._rows is not None, "record() is called only for a table that table() accepted"
        self._rows.writerow([field.text for field in record.fields])
        if self._files:
            for field in record.fields:
                if field.definition.type == FIELD_TYPE_FILE:
                    self._write_referenced(field.value)

    def diagnostic(self, problem: Problem) -> None:
        """CSV output holds no diagnostics; they are on stderr."""

    def finish(self) -> None:
        self._close_table()
        if self._files_directory is None:
            return
        os.mkdir(self._files_directory)
        for file in self._bank.files():
            with open(self._files_directory / str(file.record), "xb") as output:
                output.write(file.data)

    def close(self) -> None:
        self._close_table()

    def _claim_files_directory(self) -> Path | None:
        """
        The path of Files-<abbreviation>, claimed before any table's name, or None when there is no Files table.

        The Files table's id numbers the name, as a table's id numbers its CSV file's; the id is not public API.
        """
        abbreviation = self._bank.files_abbreviation
        files_table_id = self._bank._files_table_id
        if abbreviation is None or files_table_id is None:
            return None
        name = unique_file_name(f"Files-{abbreviation}", "", files_table_id, self._names)
        assert name is not None, "only Files-Referenced is claimed before it, with a number no table has"
        return self._directory / name

    def _close_table(self) -> None:
        if self._stream is not None:
            self._stream.close()
        self._stream = None
        self._rows = None

    def _write_referenced(self, value: FieldValue) -> None:
        """
        Write the file that the file field `value` refers to into Files-Referenced.

        The directory is created at the first file field met, empty or not, and a reference that cannot be read is
        left out; the API has reported it as unresolved_file_reference.
        """
        referenced = self._directory / REFERENCED_DIRECTORY
        if not self._referenced_created:
            os.mkdir(referenced)
            self._referenced_created = True
        if not isinstance(value, FileReference):
            return
        file = self._bank.read_file(value)
        if file is None:
            return
        name = unique_file_name(value.name, value.extension, file.record, self._referenced_names)
        if name is None:
            # This record's file is already written, under the name of its first reference.
            return
        with open(referenced / name, "xb") as output:
            output.write(file.data)
