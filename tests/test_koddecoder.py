# ABOUTME: Tests for the KOD coder helpers in cronos_extract.koddecoder.
# ABOUTME: Covers the fuzzy known-string matching that strucrack uses to suggest KOD fixes, and choosing a file's KOD.
import pytest
from cronos_builder import random_kod

from cronos_extract._diagnostic import Diagnostic, DiagnosticKind
from cronos_extract._format.header import DatHeader
from cronos_extract.koddecoder import INITIAL_KOD, KODcoding, match_with_mismatches, select_kod

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


def test_kodcoding_instances_do_not_share_their_default_confidence() -> None:
    first = KODcoding()
    first.confidence[0] = 0

    assert KODcoding().confidence[0] == 255


OTHER_KOD = random_kod(seed=1)


@pytest.mark.parametrize(
    ("given", "version", "encoding", "decoded_with", "expected"),
    [
        (
            None,
            b"01.02",
            1,
            None,
            (DiagnosticKind.MISMATCHED_KOD, "the file is KOD-encoded, but is read without KOD decoding"),
        ),
        (None, b"01.02", 0, None, None),
        (INITIAL_KOD, b"01.02", 0, None, None),
        (
            OTHER_KOD,
            b"01.02",
            0,
            None,
            (DiagnosticKind.UNUSED_KOD, "the file is not KOD-encoded, so the KOD given is not used for it"),
        ),
        (INITIAL_KOD, b"01.02", 1, INITIAL_KOD, None),
        (
            OTHER_KOD,
            b"01.02",
            1,
            INITIAL_KOD,
            (
                DiagnosticKind.UNUSED_KOD,
                "the file is encrypted with the default KOD, so the KOD given is not used for it",
            ),
        ),
        (
            INITIAL_KOD,
            b"01.04",
            1,
            INITIAL_KOD,
            (
                DiagnosticKind.MISMATCHED_KOD,
                "the file is encrypted with its own KOD, but is read with the default one; if its records do not "
                "decode, recover its KOD by cracking it",
            ),
        ),
        (OTHER_KOD, b"01.04", 1, OTHER_KOD, None),
        (INITIAL_KOD, b"01.11", 0, None, None),
    ],
    ids=[
        "none-encoded",
        "none-not-encoded",
        "default-not-encoded",
        "other-not-encoded",
        "default-encoded-default",
        "other-encoded-default",
        "default-encoded-own",
        "other-encoded-own",
        "default-v4-not-encoded",
    ],
)
def test_select_kod_chooses_and_reports(
    given: list[int] | None,
    version: bytes,
    encoding: int,
    decoded_with: list[int] | None,
    expected: tuple[DiagnosticKind, str] | None,
) -> None:
    header = DatHeader(version, 0, encoding, 0x40)

    coder, diagnostic = select_kod(header, None if given is None else KODcoding(given), "CroStru.dat")

    assert (None if coder is None else coder.kod) == decoded_with
    assert diagnostic == (None if expected is None else Diagnostic(*expected, file="CroStru.dat"))
