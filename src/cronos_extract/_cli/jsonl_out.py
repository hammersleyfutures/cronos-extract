# ABOUTME: The JSON Lines export: one self-contained JSON object per table, record and diagnostic, in order.
# ABOUTME: Each field carries its value only: a string, null, or an object for a file reference.
import datetime
import json
from typing import TextIO

from .._api.bank import Table
from .._api.values import FieldValue, FileReference, Record
from .report import Problem


def json_value(value: FieldValue) -> object:
    """
    The JSON value of a field whose API value is `value`: null when empty, a date or time in ISO format, an object
    for a file reference, and otherwise the text.
    """
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, datetime.time):
        return value.isoformat(timespec="minutes")
    if isinstance(value, FileReference):
        return {"name": value.name, "extension": value.extension, "record": value.record}
    return value


class JsonlWriter:
    """Writes the JSON Lines export to `stream`: a line per table before its records, per record and per problem."""

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream

    def table(self, table: Table) -> bool:
        self._write(
            {
                "type": "table",
                "table": table.name,
                "table_id": table.id,
                "abbreviation": table.abbreviation,
                "fields": [{"name": field.name, "type": field.type} for field in table.fields],
            }
        )
        return True

    def record(self, table: Table, record: Record) -> None:
        self._write(
            {
                "type": "record",
                "table": table.name,
                "table_id": table.id,
                "record": record.number,
                "fields": [
                    {"name": field.definition.name, "value": json_value(field.value)} for field in record.fields
                ],
            }
        )

    def diagnostic(self, problem: Problem) -> None:
        self._write(
            {
                "type": "diagnostic",
                "kind": problem.kind,
                "message": problem.message,
                "file": problem.file,
                "table": problem.table,
                "record": problem.record,
                "field": problem.field,
            }
        )

    def finish(self) -> None:
        self._stream.flush()

    def close(self) -> None:
        """The stream belongs to the export, which closes it."""

    def _write(self, line: dict[str, object]) -> None:
        self._stream.write(json.dumps(line, ensure_ascii=False) + "\n")
