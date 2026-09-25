# ABOUTME: Tests for the safe, unique names an export gives its files, directories and PostgreSQL identifiers.
# ABOUTME: They call _cli/names.py directly.
import pytest

from cronos_extract._cli.names import MAX_FILE_NAME_BYTES, safepathname, truncate_utf8, unique_file_name


def test_safepathname_replaces_separators_and_characters_windows_forbids() -> None:
    assert safepathname('a/b\\c:d*e?f"g<h>i|j\x00k\x1fl') == "a_b_c_d_e_f_g_h_i_j_k_l"


def test_truncate_utf8_cuts_at_a_character_boundary() -> None:
    assert truncate_utf8("яяя", 5) == "яя"


@pytest.mark.parametrize(("stem", "expected"), [("", "7"), ("..", "7"), ("../..", ".._.."), ("a/b", "a_b")])
def test_a_file_name_is_safe_and_never_only_dots(stem: str, expected: str) -> None:
    assert unique_file_name(stem, "", 7, {}) == expected


def test_a_name_used_by_another_number_gets_the_number_appended() -> None:
    used: dict[str, int] = {}

    assert unique_file_name("same", "txt", 3, used) == "same.txt"
    assert unique_file_name("SAME", "txt", 4, used) == "SAME-4.txt"
    assert unique_file_name("same", "txt", 3, used) is None


def test_a_long_name_fits_the_file_name_limit_and_keeps_its_extension() -> None:
    name = unique_file_name("я" * 200, "x" * 100, 1, {})

    assert name is not None
    assert len(name.encode("utf-8")) <= MAX_FILE_NAME_BYTES
    assert name.startswith("яяя")
    assert name.endswith("." + "x" * 63)
