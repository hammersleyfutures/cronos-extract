# ABOUTME: Unit tests for field decoding in cronos_extract.Datamodel and text helpers in cronos_extract.hexdump.
# ABOUTME: They pin how raw field bytes become presentable content, using real definition bytes, not mocks.
import argparse
import struct

import pytest
from cronos_builder import erdgeist_table_definition

from cronos_extract._diagnostic import Diagnostic, DiagnosticKind, for_table_definition
from cronos_extract.Datamodel import Field, FieldDefinition, TableDefinition, is_table_key
from cronos_extract.hexdump import aschr, hexdump


def make_fielddef(typ: int, name: str = "Field") -> FieldDefinition:
    """Build a FieldDefinition from bytes laid out as CroStru stores them."""
    encoded_name = name.encode("cp1251")
    data = struct.pack("<HLB", typ, 1, len(encoded_name)) + encoded_name + struct.pack("<LB", 0, 1)
    if typ:
        data += struct.pack("<LLL", 1, 20, 9)
    return FieldDefinition(data)


def test_fielddef_decodes_type_name_and_limits() -> None:
    fielddef = make_fielddef(2, "Имя")

    assert (fielddef.typ, fielddef.name, fielddef.idx2, fielddef.maxval) == (2, "Имя", 1, 20)


def test_system_number_field_is_shown_as_given() -> None:
    assert Field(make_fielddef(0), "7").content == "7"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"1240315", "2024-03-15"),
        (b"1240315\x00\x00", "2024-03-15"),
        (b"-10101", "1899-01-01"),
        (b"00101", "1900-01-01"),
    ],
)
def test_date_field_is_formatted_as_iso_date(raw: bytes, expected: str) -> None:
    assert Field(make_fielddef(4), raw).content == expected


@pytest.mark.parametrize(("raw", "expected"), [(b"0930", "09:30"), (b"2359\x00", "23:59")])
def test_time_field_is_formatted_as_hours_and_minutes(raw: bytes, expected: str) -> None:
    assert Field(make_fielddef(5), raw).content == expected


@pytest.mark.parametrize(
    ("typ", "raw", "expected"),
    [
        (4, b"12x", "12x"),
        (4, b"12x\x00\x00", "12x"),
        (4, "Дата".encode("cp1251"), "Дата"),
        (5, b"ab", "ab"),
        (5, "Время\x00".encode("cp1251"), "Время"),
    ],
    ids=["date", "date-with-nuls", "date-cp1251", "time", "time-cp1251-with-nul"],
)
def test_unparseable_date_or_time_shows_the_raw_text(typ: int, raw: bytes, expected: str) -> None:
    assert Field(make_fielddef(typ), raw).content == expected


def test_text_field_is_decoded_from_cp1251_without_trailing_nuls() -> None:
    assert Field(make_fielddef(2), "Привет".encode("cp1251") + b"\x00\x00").content == "Привет"


def test_text_field_holding_an_undefined_cp1251_byte_keeps_it_as_the_replacement_character() -> None:
    assert Field(make_fielddef(2), b"a\x98b").content == "a�b"


def test_empty_field_has_empty_content() -> None:
    assert Field(make_fielddef(2), b"").content == ""


@pytest.mark.parametrize(
    ("byte", "expected"),
    [(0x41, "A"), (0x20, " "), (0xC0, "\u0410"), (0xFF, "я"), (0x98, "."), (0x10, "."), (0x7F, ".")],
)
def test_aschr_maps_cp1251_bytes_to_text(byte: int, expected: str) -> None:
    assert aschr(byte) == expected


def test_hexdump_prints_hex_and_text_columns(capsys: pytest.CaptureFixture[str]) -> None:
    hexdump(0x10, b"ABCDEFG", argparse.Namespace(width=4, ascdump=False))

    assert capsys.readouterr().out == "00000010: 41 42 43 44  ABCD\n00000014: 45 46 47     EFG\n"


def test_hexdump_ascdump_prints_text_only(capsys: pytest.CaptureFixture[str]) -> None:
    hexdump(0, "Привет!".encode("cp1251"), argparse.Namespace(width=4, ascdump=True))

    assert capsys.readouterr().out == "00000000: Прив\n00000004: ет!\n"


def test_table_definition_problems_go_through_report(capfd: pytest.CaptureFixture[str]) -> None:
    problems: list[Diagnostic] = []

    TableDefinition(erdgeist_table_definition(), report=problems.append)

    assert problems == [
        Diagnostic(DiagnosticKind.UNEXPECTED_STRUCTURE, "FieldDefinition Section 2 not marked with a 2")
    ]
    assert capfd.readouterr().err == ""


def test_a_table_definition_reporter_names_crostru_and_the_key(capfd: pytest.CaptureFixture[str]) -> None:
    problems: list[Diagnostic] = []

    TableDefinition(erdgeist_table_definition(), report=for_table_definition(problems.append, "Base001"))

    assert problems == [
        Diagnostic(
            DiagnosticKind.UNEXPECTED_STRUCTURE,
            "Base001: FieldDefinition Section 2 not marked with a 2",
            file="CroStru.dat",
        )
    ]
    assert capfd.readouterr().err == ""


@pytest.mark.parametrize(
    ("key", "is_table"),
    [
        ("Base000", True),
        ("Base002", True),
        ("BaseImage001", False),
        ("Base", False),
        ("Base\u0662", False),
        ("Base\u00b2", False),
        ("Base\u0660\u0660\u0662", False),
    ],
)
def test_only_base_followed_by_ascii_digits_names_a_table(key: str, is_table: bool) -> None:
    assert is_table_key(key) is is_table
