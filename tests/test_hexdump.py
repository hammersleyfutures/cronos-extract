# ABOUTME: Tests for the byte and text conversion helpers in cronos_extract.hexdump.
# ABOUTME: Covers CP-1251 encoding of user-supplied text used to force KOD entries.
import pytest

from cronos_extract.hexdump import as1251


def test_as1251_encodes_cyrillic_text() -> None:
    assert as1251("Жb") == b"\xc6b"


def test_as1251_rejects_text_cp1251_cannot_encode() -> None:
    with pytest.raises(ValueError, match="can't be encoded as CP-1251"):
        as1251("中")
