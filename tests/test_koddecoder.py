# ABOUTME: Tests for the KOD coder helpers in cronos_extract.koddecoder.
# ABOUTME: Covers the fuzzy known-string matching that strucrack uses to suggest KOD fixes.
from cronos_extract.koddecoder import KODcoding, match_with_mismatches

UNRESOLVED = -1


def kod_with_an_unresolved_duplicate() -> KODcoding:
    """Return an identity KOD whose entry 1 duplicates entry 0's value and is marked unresolved."""
    kod = list(range(256))
    kod[1] = 0
    confidence = [1] * 256
    confidence[1] = UNRESOLVED
    return KODcoding(kod, confidence)


def test_try_decode_treats_an_unresolved_entry_as_unknown() -> None:
    # At shift 5 entry 1 would decode to (0 - 5) % 256 = 251; as an unknown entry it decodes to 0.
    assert kod_with_an_unresolved_duplicate().try_decode(5, b"\x01") == ([0], [UNRESOLVED])


def test_encode_ignores_an_unresolved_entry() -> None:
    assert kod_with_an_unresolved_duplicate().encode(0, b"\x00") == b"\x00"


def known(text: bytes) -> tuple[list[int], list[int]]:
    """Return `text` as decoded bytes with every byte's KOD entry known."""
    return list(text), [1] * len(text)


def test_match_with_mismatches_finds_a_near_match_at_the_last_offset() -> None:
    data, confidence = known(b"xxABD")

    assert match_with_mismatches(data, confidence, b"ABC", 2) == [(2, 2)]


def test_match_with_mismatches_finds_a_near_match_filling_the_whole_data() -> None:
    data, confidence = known(b"ABD")

    assert match_with_mismatches(data, confidence, b"ABC", 2) == [(0, 2)]


def test_match_with_mismatches_needs_at_least_the_given_number_of_matching_characters() -> None:
    data, confidence = known(b"ABDx")

    assert match_with_mismatches(data, confidence, b"ABC", 3) == []
    assert match_with_mismatches(data, confidence, b"ABC", 2) == [(0, 2)]
