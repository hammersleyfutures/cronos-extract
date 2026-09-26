# ABOUTME: Tests for how the API decodes records, with each field type's value, text, raw bytes and diagnostics.
# ABOUTME: Decodes records laid out by tests/cronos_builder.py against the real "erdgeist" table definition.
import dataclasses
import datetime

import pytest
from cronos_builder import (
    TEST_TABLE_FIELD_COUNT,
    TEST_TABLE_ID,
    bank_record,
    erdgeist_table_definition,
    file_reference_field,
    ignore_problems,
)

from cronos_extract import Diagnostic, DiagnosticKind, FieldDefinition, FileReference, Record
from cronos_extract._api.values import decode_record
from cronos_extract.Datamodel import TableDefinition

DATE, TIME, FILE, TEXT, LINK = 3, 4, 5, 0, 7


def decode(fields: list[bytes], number: int = 7) -> Record:
    """Decode a record of the erdgeist table holding `fields`, one per field after the system number."""
    table = TableDefinition(erdgeist_table_definition(), report=ignore_problems)
    definitions = tuple(FieldDefinition(field.name, field.typ) for field in table.fields)
    return decode_record(number, "erdgeist", definitions, table.fields, bank_record(TEST_TABLE_ID, fields)[1:])


def with_field(index: int, data: bytes) -> list[bytes]:
    """The fields of a record whose field `index` (0 is Entry #1) holds `data` and whose other fields are empty."""
    fields = [b""] * TEST_TABLE_FIELD_COUNT
    fields[index] = data
    return fields


def invalid_value(field: str, message: str) -> Diagnostic:
    return Diagnostic(
        DiagnosticKind.INVALID_VALUE, message, file="CroBank.dat", table="erdgeist", record=7, field=field
    )


def test_the_system_number_is_the_record_number_as_text_with_no_raw_bytes() -> None:
    field = decode(with_field(TEXT, b""), number=42).fields[0]

    assert field.definition == FieldDefinition("Системный номер", 0)
    assert (field.value, field.text, field.raw) == ("42", "42", b"")


def test_a_record_has_one_field_per_field_definition_in_order() -> None:
    record = decode(with_field(TEXT, b"x"))

    assert [field.definition.name for field in record.fields] == [
        "Системный номер",
        *(f"Entry #{number}" for number in range(1, 12)),
    ]


def test_a_text_field_is_its_text() -> None:
    field = decode(with_field(TEXT, b"Hammersley")).fields[1]

    assert (field.value, field.text, field.raw) == ("Hammersley", "Hammersley", b"Hammersley")


def test_an_empty_field_has_no_value() -> None:
    field = decode(with_field(TEXT, b"x"))["Entry #4"]

    assert (field.value, field.text, field.raw) == (None, "", b"")


def test_a_full_date_is_a_date() -> None:
    record = decode(with_field(DATE, b"1240315"))

    assert (record["Entry #4"].value, record["Entry #4"].text, record["Entry #4"].raw) == (
        datetime.date(2024, 3, 15),
        "2024-03-15",
        b"1240315",
    )
    assert record.diagnostics == ()


def test_a_year_only_date_is_its_text_without_a_diagnostic() -> None:
    record = decode(with_field(DATE, b"850000"))

    assert (record["Entry #4"].value, record["Entry #4"].text) == ("1985-00-00", "1985-00-00")
    assert record.diagnostics == ()


def test_a_date_field_holding_words_is_its_text_with_a_diagnostic() -> None:
    record = decode(with_field(DATE, "до 1990".encode("cp1251")))

    assert record["Entry #4"].value == "до 1990"
    assert record.diagnostics == (invalid_value("Entry #4", "the value is not a date; it is kept as text"),)


def test_a_date_with_month_13_is_its_text_with_a_diagnostic() -> None:
    record = decode(with_field(DATE, b"851301"))

    assert record["Entry #4"].value == "1985-13-01"
    assert record.diagnostics == (invalid_value("Entry #4", "the value is not a valid date; it is kept as text"),)


def test_a_date_with_only_a_zero_day_is_its_text_with_a_diagnostic() -> None:
    record = decode(with_field(DATE, b"850300"))

    assert record["Entry #4"].value == "1985-03-00"
    assert [diagnostic.kind for diagnostic in record.diagnostics] == [DiagnosticKind.INVALID_VALUE]


def test_a_date_past_the_largest_year_is_its_text_with_a_diagnostic() -> None:
    record = decode(with_field(DATE, b"99999999990101"))

    assert record["Entry #4"].value == "10000001899-01-01"
    assert record.diagnostics == (invalid_value("Entry #4", "the value is not a valid date; it is kept as text"),)


def test_a_date_before_year_one_is_its_text_with_a_diagnostic() -> None:
    record = decode(with_field(DATE, b"-19050101"))

    assert record["Entry #4"].value == "-005-01-01"
    assert record.diagnostics == (invalid_value("Entry #4", "the value is not a valid date; it is kept as text"),)


def test_a_time_is_a_time() -> None:
    record = decode(with_field(TIME, b"0930"))

    assert (record["Entry #5"].value, record["Entry #5"].text) == (datetime.time(9, 30), "09:30")
    assert record.diagnostics == ()


def test_a_time_past_midnight_is_its_text_with_a_diagnostic() -> None:
    record = decode(with_field(TIME, b"2561"))

    assert record["Entry #5"].value == "25:61"
    assert record.diagnostics == (invalid_value("Entry #5", "the value is not a valid time; it is kept as text"),)


def test_a_time_field_holding_a_letter_is_its_text_with_a_diagnostic() -> None:
    record = decode(with_field(TIME, b"x"))

    assert record["Entry #5"].value == "x"
    assert record.diagnostics == (invalid_value("Entry #5", "the value is not a time; it is kept as text"),)


def test_a_file_reference_is_a_file_reference_whose_raw_bytes_omit_the_complex_field_header() -> None:
    stored = file_reference_field("report", "pdf", 12)

    field = decode(with_field(FILE, stored))["Entry #6"]

    assert field.value == FileReference(name="report", extension="pdf", record=12)
    assert field.text == "report pdf 12"
    assert field.raw == stored[5:]


@pytest.mark.parametrize(
    "record_text",
    ["+12", " 12", "1_2", "x", "", "9" * 5000],
    ids=["plus", "space", "underscore", "letter", "empty", "5000-digits"],
)
def test_a_file_reference_whose_record_is_not_ascii_digits_has_no_record(record_text: str) -> None:
    field = decode(with_field(FILE, file_reference_field("report", "pdf", record_text)))["Entry #6"]

    assert isinstance(field.value, FileReference)
    assert field.value.record is None


def test_a_link_field_is_its_hex_text() -> None:
    field = decode(with_field(LINK, b"\x01\x02"))["Entry #8"]

    assert isinstance(field.value, str)
    assert field.value == field.text
    assert field.raw == b"\x01\x02"


def test_a_field_that_cannot_be_decoded_leaves_it_and_the_rest_empty_with_a_diagnostic() -> None:
    record = decode([b"\x1b\xff\xff\xff\x7f"], number=7)

    assert len(record.fields) == 12
    assert [field.value for field in record.fields[1:]] == [None] * 11
    (diagnostic,) = record.diagnostics
    assert (diagnostic.kind, diagnostic.file, diagnostic.table, diagnostic.record, diagnostic.field) == (
        DiagnosticKind.UNDECODABLE_FIELD,
        "CroBank.dat",
        "erdgeist",
        7,
        "Entry #1",
    )
    assert "could not be decoded" in diagnostic.message


def test_a_record_looks_fields_up_by_name() -> None:
    record = decode(with_field(TEXT, b"x"))

    assert record["Entry #1"] is record.fields[1]
    with pytest.raises(KeyError):
        _ = record["Entry #12"]


def test_diagnostic_messages_hold_no_field_data() -> None:
    record = decode(with_field(DATE, b"secret-value"))

    assert all("secret" not in diagnostic.message for diagnostic in record.diagnostics)


def test_records_and_fields_are_frozen() -> None:
    record = decode(with_field(TEXT, b"x"))

    with pytest.raises(dataclasses.FrozenInstanceError):
        record.number = 8  # ty: ignore[invalid-assignment]
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.fields[1].text = "y"  # ty: ignore[invalid-assignment]
