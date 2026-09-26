# ABOUTME: The API's record types: field definitions, fields with typed values, records, file references and files.
# ABOUTME: decode_record turns a CroBank record decoded by Datamodel into them, with field problems as diagnostics.
import datetime
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from ..Datamodel import Field as DecodedField
from ..Datamodel import FieldDefinition as DecodedFieldDefinition
from ..Datamodel import Record as DecodedRecord
from .diagnostics import Diagnostic, DiagnosticKind

FIELD_TYPE_DATE = 4
FIELD_TYPE_TIME = 5
FIELD_TYPE_FILE = 6
BANK_FILE = "CroBank.dat"
# Datamodel formats a date as the year, month and day, and a time as the hour and minute.
DATE_TEXT = re.compile(r"(-?[0-9]+)-([0-9]{2})-([0-9]{2})")
TIME_TEXT = re.compile(r"([0-9]{2}):([0-9]{2})")
ASCII_DIGITS = re.compile(r"[0-9]+")


@dataclass(frozen=True)
class FieldDefinition:
    """A field of a table: its name and its CronosPro field type code."""

    name: str
    type: int


@dataclass(frozen=True)
class FileReference:
    """A field's reference to a file stored in the Files table: the file's name, extension and CroBank record."""

    name: str
    extension: str
    record: int | None


@dataclass(frozen=True)
class EmbeddedFile:
    """
    A file stored in the Files table: its CroBank record number and its bytes.

    `name` is "name.extension" when the file was read through a FileReference, and None from Bank.files(), because
    the Files table stores no names.
    """

    record: int
    data: bytes
    name: str | None


type FieldValue = str | datetime.date | datetime.time | FileReference | None


@dataclass(frozen=True)
class Field:
    """
    One field of a record.

    `text` is the field for display. `value` is a datetime.date or datetime.time for a date or time field, a
    FileReference for a file field, None for an empty field, and otherwise the text; a date stored with only its
    year, and a date or time that does not parse, are the text. `raw` is the field's bytes in the record, without
    the field separator or a complex field's marker and length.
    """

    definition: FieldDefinition
    value: FieldValue
    text: str
    raw: bytes


@dataclass(frozen=True)
class Record:
    """A record of a table: its CroBank record number, one field per field definition, and its diagnostics."""

    number: int
    fields: tuple[Field, ...]
    diagnostics: tuple[Diagnostic, ...]

    def __getitem__(self, name: str) -> Field:
        """The first field named `name`. Raises KeyError when there is none."""
        for field in self.fields:
            if field.definition.name == name:
                return field
        raise KeyError(name)


def parse_date(text: str) -> tuple[FieldValue, str | None]:
    """The value of a date field whose text is `text`, and the problem with it, if any."""
    match = DATE_TEXT.fullmatch(text)
    if match is None:
        return text, "the value is not a date; it is kept as text"
    try:
        year, month, day = (int(part) for part in match.groups())
        if month == 0 and day == 0:
            return text, None
        return datetime.date(year, month, day), None
    # A year with more digits than a C long makes datetime.date raise OverflowError instead of ValueError.
    except (ValueError, OverflowError):
        return text, "the value is not a valid date; it is kept as text"


def parse_time(text: str) -> tuple[FieldValue, str | None]:
    """The value of a time field whose text is `text`, and the problem with it, if any."""
    match = TIME_TEXT.fullmatch(text)
    if match is None:
        return text, "the value is not a time; it is kept as text"
    try:
        return datetime.time(int(match[1]), int(match[2])), None
    except ValueError:
        return text, "the value is not a valid time; it is kept as text"


def record_number(text: str) -> int | None:
    """The record number `text` holds when it is ASCII decimal digits that make a number, else None."""
    if not ASCII_DIGITS.fullmatch(text):
        return None
    try:
        return int(text)
    except ValueError:
        return None


def convert_field(definition: FieldDefinition, decoded: DecodedField) -> tuple[Field, str | None]:
    """The public Field for the field `decoded` described by `definition`, and the problem with its value, if any."""
    raw = cast(bytes, decoded.data)
    text = decoded.content
    if not raw:
        return Field(definition, None, "", b""), None
    if definition.type == FIELD_TYPE_DATE:
        value, problem = parse_date(text)
    elif definition.type == FIELD_TYPE_TIME:
        value, problem = parse_time(text)
    elif definition.type == FIELD_TYPE_FILE:
        value = FileReference(decoded.filename, decoded.extname, record_number(decoded.filedatarecord))
        problem = None
    else:
        value, problem = text, None
    return Field(definition, value, text, raw), problem


def decode_record(
    number: int,
    table: str,
    definitions: Sequence[FieldDefinition],
    fielddefs: Sequence[DecodedFieldDefinition],
    data: bytes,
) -> Record:
    """
    Decode CroBank record `number` of the table named `table` from `data`, the record after its table id byte.

    `fielddefs` are the table's Datamodel field definitions, which `definitions` describe one for one; the first
    is the system number. A field that cannot be decoded is left empty, as are the fields after it, and reported
    as undecodable_field; a date or time that does not parse is reported as invalid_value.
    """
    decoded = DecodedRecord(number, list(fielddefs), data)
    diagnostics = [
        Diagnostic(
            DiagnosticKind.UNDECODABLE_FIELD,
            f"the field could not be decoded ({error}) and is left empty",
            file=BANK_FILE,
            table=table,
            record=number,
            field=name,
        )
        for name, error in decoded.errors
    ]
    system_number = decoded.fields[0].content
    fields = [Field(definitions[0], system_number, system_number, b"")]
    for definition, decoded_field in zip(definitions[1:], decoded.fields[1:], strict=True):
        field, problem = convert_field(definition, decoded_field)
        fields.append(field)
        if problem is not None:
            diagnostics.append(
                Diagnostic(
                    DiagnosticKind.INVALID_VALUE,
                    problem,
                    file=BANK_FILE,
                    table=table,
                    record=number,
                    field=definition.name,
                )
            )
    return Record(number, tuple(fields), tuple(diagnostics))
