# ABOUTME: Tests for Kod, the cronos_extract API's KOD table: construction, validation and hex conversion.
# ABOUTME: Also checks that its internal decoder decodes exactly as the koddecoder module does.
import pytest
from cronos_builder import random_kod

from cronos_extract._api.kod import Kod, kod_coder
from cronos_extract.koddecoder import INITIAL_KOD, KODcoding


def test_the_default_kod_is_the_initial_kod_table() -> None:
    assert Kod.default().table == tuple(INITIAL_KOD)


def test_a_kod_from_a_table_keeps_the_table() -> None:
    table = random_kod(seed=5)

    assert Kod.from_table(table).table == tuple(table)


def test_kods_compare_and_hash_by_table() -> None:
    assert Kod.from_table(INITIAL_KOD) == Kod.default()
    assert Kod.from_table(random_kod(seed=5)) != Kod.default()
    assert len({Kod.default(), Kod.from_table(INITIAL_KOD)}) == 1


@pytest.mark.parametrize(
    "table",
    [
        list(range(255)),
        [*range(256), 0],
        [0, *range(255)],
        [*range(255), 256],
        [-1, *range(1, 256)],
        [False, True, *range(2, 256)],
        [0.0, *range(1, 256)],
    ],
    ids=["too-short", "too-long", "duplicate", "256", "negative", "bool", "float"],
)
def test_a_table_that_is_not_a_permutation_of_ints_is_refused(table: list[object]) -> None:
    with pytest.raises(ValueError, match="each number from 0 to 255 exactly once"):
        Kod.from_table(table)  # ty: ignore[invalid-argument-type]


def test_hex_round_trips() -> None:
    kod = Kod.from_table(random_kod(seed=5))

    assert kod.hex() == bytes(random_kod(seed=5)).hex()
    assert Kod.from_hex(kod.hex()) == kod
    assert Kod.from_hex(kod.hex().upper()) == kod


@pytest.mark.parametrize(
    "text",
    [
        bytes(range(255)).hex(),
        bytes(range(256)).hex() + "00",
        " " + bytes(range(256)).hex()[1:],
        bytes(range(256)).hex()[:-1] + "\n",
        "zz" + bytes(range(256)).hex()[2:],
    ],
    ids=["510-digits", "514-digits", "space", "newline", "not-hex"],
)
def test_hex_that_is_not_512_hex_digits_is_refused(text: str) -> None:
    with pytest.raises(ValueError, match="exactly 512 hex digits"):
        Kod.from_hex(text)


def test_hex_digits_that_are_not_a_permutation_are_refused() -> None:
    with pytest.raises(ValueError, match="each number from 0 to 255 exactly once"):
        Kod.from_hex("00" * 256)


def test_kod_coder_decodes_as_the_koddecoder_does() -> None:
    table = random_kod(seed=5)
    coder = kod_coder(Kod.from_table(table))

    assert coder is not None
    assert coder.decode(3, b"any bytes") == KODcoding(table).decode(3, b"any bytes")
    assert kod_coder(None) is None
