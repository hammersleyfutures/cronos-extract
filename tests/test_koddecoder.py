# ABOUTME: Tests for the KOD coder helpers in cronos_extract.koddecoder.
# ABOUTME: Covers the fuzzy known-string matching that strucrack uses to suggest KOD fixes.
from cronos_extract.koddecoder import match_with_mismatches


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
