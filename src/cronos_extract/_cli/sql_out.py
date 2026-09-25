# ABOUTME: The PostgreSQL export: a CREATE TABLE per table, every column TEXT, and one INSERT per record.
# ABOUTME: Names are quoted, unique and at most 63 bytes; values are standard SQL literals, with NULL when empty.
from collections.abc import Callable, Sequence
from typing import TextIO

from .._api.bank import Table
from .._api.values import Field, FieldDefinition, Record
from .names import POSTGRES_IDENTIFIER_BYTES, unique_name
from .report import DUPLICATE_TABLE, REPLACED_NUL, Problem

BANK_FILE = "CroBank.dat"
STRU_FILE = "CroStru.dat"


def unique_sql_table_name(table: Table, used_names: dict[str, int]) -> str | None:
    """
    Return the name to give `table` in SQL output, or None when a table with the same name and table id
    is already written. Double quotes become underscores, an empty name becomes the table id, and the name
    fits in POSTGRES_IDENTIFIER_BYTES. See unique_name for how names are kept unique.
    """
    name = table.name.replace('"', "_") or str(table.id)
    return unique_name(name, "", table.id, used_names, POSTGRES_IDENTIFIER_BYTES)


def unique_sql_column_names(fields: Sequence[FieldDefinition]) -> list[str]:
    """
    Return the names to give the columns of a table with `fields` in SQL output, in the order of the fields.
    Double quotes become underscores, an empty name becomes the column number, counting the system number
    as column 0, and every name is unique within the table and fits in POSTGRES_IDENTIFIER_BYTES.
    See unique_name for how names are kept unique.
    """
    used_names: dict[str, int] = {}
    names = []
    for number, field in enumerate(fields):
        name = unique_name(
            field.name.replace('"', "_") or str(number), "", number, used_names, POSTGRES_IDENTIFIER_BYTES
        )
        assert name is not None, "each column has its own number, so its name is never taken to be its own"
        names.append(name)
    return names


def sql_value(table: Table, record: Record, field: Field, on_problem: Callable[[Problem], None]) -> str:
    """
    Return the text of `field` as a PostgreSQL literal for its TEXT column, or NULL when the field is empty.
    Single quotes are doubled, which is correct with standard_conforming_strings on.
    PostgreSQL text cannot hold NUL, so each NUL becomes U+FFFD, reported as replaced_nul.
    """
    if not field.text:
        return "NULL"
    text = field.text
    if "\x00" in text:
        on_problem(
            Problem(
                REPLACED_NUL,
                "the value holds NUL characters, which PostgreSQL text cannot hold; they are written as U+FFFD",
                file=BANK_FILE,
                table=table.name,
                record=record.number,
                field=field.definition.name,
            )
        )
        text = text.replace("\x00", "�")
    return "'" + text.replace("'", "''") + "'"


class SqlWriter:
    """Writes the PostgreSQL export to `stream`, starting with SET standard_conforming_strings = on."""

    def __init__(self, stream: TextIO, on_problem: Callable[[Problem], None]) -> None:
        self._stream = stream
        self._on_problem = on_problem
        self._table_names: dict[str, int] = {}
        self._current: str | None = None
        stream.write("SET standard_conforming_strings = on;\n")

    def table(self, table: Table) -> bool:
        self._current = unique_sql_table_name(table, self._table_names)
        if self._current is None:
            self._on_problem(
                Problem(
                    DUPLICATE_TABLE,
                    "its SQL table name and table id are those of a table already written, so it is skipped",
                    file=STRU_FILE,
                    table=table.name,
                )
            )
            return False
        columns = ",\n".join(f'    "{column}" TEXT' for column in unique_sql_column_names(table.fields))
        self._stream.write(f'\nCREATE TABLE "{self._current}" (\n{columns}\n);\n')
        return True

    def record(self, table: Table, record: Record) -> None:
        """Write `record`; called only after table() accepted `table`, so self._current is not None."""
        assert self._current is not None, "record() is called only for a table that table() accepted"
        values = ", ".join(sql_value(table, record, field, self._on_problem) for field in record.fields)
        self._stream.write(f'INSERT INTO "{self._current}" VALUES ({values});\n')

    def diagnostic(self, problem: Problem) -> None:
        """SQL output holds no diagnostics; they are on stderr."""

    def finish(self) -> None:
        self._stream.flush()

    def close(self) -> None:
        """The stream belongs to the export, which closes it."""
