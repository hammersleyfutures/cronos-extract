# ABOUTME: Tests for the KOD coder helpers in cronos_extract.koddecoder.
# ABOUTME: Covers the fuzzy known-string matching that strucrack uses to suggest KOD fixes, and choosing a file's KOD.
import dataclasses
from pathlib import Path

import pytest
from cronos_builder import random_kod, write_datafile, write_header_only_datafile

from cronos_extract._diagnostic import Diagnostic, DiagnosticKind
from cronos_extract._format.header import DatHeader, read_dat_header, read_kod_check
from cronos_extract.koddecoder import INITIAL_KOD, KODcoding, kod_fits_header, match_with_mismatches, select_kod

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


def built_header(path: Path) -> DatHeader:
    """Read the header of the built file at `path` with its KOD check bytes."""
    with path.open("rb") as file:
        header = read_dat_header(file, where=path.name)
        return dataclasses.replace(header, kod_check=read_kod_check(file))


@pytest.mark.parametrize("kod", [random_kod(seed=1), INITIAL_KOD], ids=["own", "default"])
def test_kod_fits_header_accepts_the_kod_a_v4_file_was_written_with(tmp_path: Path, kod: list[int]) -> None:
    write_datafile(tmp_path, "Bank", [b"record"], kod=kod, version=b"01.11")

    assert kod_fits_header(built_header(tmp_path / "CroBank.dat"), KODcoding(kod)) is True


@pytest.mark.parametrize("kod", [random_kod(seed=1), INITIAL_KOD], ids=["own", "default"])
def test_kod_fits_header_rejects_another_kod_for_a_v4_file(tmp_path: Path, kod: list[int]) -> None:
    write_datafile(tmp_path, "Bank", [b"record"], kod=kod, version=b"01.11")
    other = random_kod(seed=2) if kod == INITIAL_KOD else INITIAL_KOD

    assert kod_fits_header(built_header(tmp_path / "CroBank.dat"), KODcoding(other)) is False


def test_kod_fits_header_says_nothing_about_a_v3_file(tmp_path: Path) -> None:
    kod = random_kod(seed=1)
    write_datafile(tmp_path, "Bank", [b"record"], kod=kod, version=b"01.04")

    header = built_header(tmp_path / "CroBank.dat")

    assert len(header.kod_check) == 8
    assert kod_fits_header(header, KODcoding(kod)) is None
    assert kod_fits_header(header, KODcoding(INITIAL_KOD)) is None


def test_kod_fits_header_says_nothing_about_a_v4_file_too_short_for_the_check(tmp_path: Path) -> None:
    write_header_only_datafile(tmp_path, "Bank", version=b"01.11", encoding=1)
    header = built_header(tmp_path / "CroBank.dat")
    with (tmp_path / "CroBank.dat").open("ab") as file:
        file.write(bytes(7))
    seven_bytes = built_header(tmp_path / "CroBank.dat")

    assert (header.kod_check, len(seven_bytes.kod_check)) == (b"", 7)
    assert kod_fits_header(header, KODcoding(INITIAL_KOD)) is None
    assert kod_fits_header(seven_bytes, KODcoding(INITIAL_KOD)) is None


WRONG_KOD_MESSAGE = "the file's header shows that the KOD used is not its KOD"


def v4_header(written_with: list[int], check_size: int = 8) -> DatHeader:
    """A KOD-encoded 01.11 header whose check bytes are the first `check_size` written with `written_with`."""
    return DatHeader(b"01.11", 0, 1, 0x40, KODcoding(written_with).encode(0, bytes(8))[:check_size])


@pytest.mark.parametrize(
    ("written_with", "given", "decoded_with", "expected"),
    [
        (OTHER_KOD, OTHER_KOD, OTHER_KOD, None),
        (INITIAL_KOD, INITIAL_KOD, INITIAL_KOD, None),
        (OTHER_KOD, INITIAL_KOD, INITIAL_KOD, (DiagnosticKind.MISMATCHED_KOD, WRONG_KOD_MESSAGE)),
        (INITIAL_KOD, OTHER_KOD, OTHER_KOD, (DiagnosticKind.MISMATCHED_KOD, WRONG_KOD_MESSAGE)),
        (OTHER_KOD, random_kod(seed=2), random_kod(seed=2), (DiagnosticKind.MISMATCHED_KOD, WRONG_KOD_MESSAGE)),
        (
            OTHER_KOD,
            None,
            None,
            (DiagnosticKind.MISMATCHED_KOD, "the file is KOD-encoded, but is read without KOD decoding"),
        ),
    ],
    ids=[
        "own-accepted",
        "default-accepted",
        "default-rejected",
        "other-rejected-default-file",
        "other-rejected-own-file",
        "none",
    ],
)
def test_select_kod_follows_the_header_of_a_kod_encoded_v4_file(
    written_with: list[int],
    given: list[int] | None,
    decoded_with: list[int] | None,
    expected: tuple[DiagnosticKind, str] | None,
) -> None:
    coder, diagnostic = select_kod(v4_header(written_with), None if given is None else KODcoding(given), "CroBank.dat")

    assert (None if coder is None else coder.kod) == decoded_with
    assert diagnostic == (None if expected is None else Diagnostic(*expected, file="CroBank.dat"))


@pytest.mark.parametrize("check_size", [0, 7])
@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (
            INITIAL_KOD,
            (
                DiagnosticKind.MISMATCHED_KOD,
                "the file is encrypted with its own KOD, but is read with the default one; if its records do not "
                "decode, recover its KOD by cracking it",
            ),
        ),
        (random_kod(seed=2), None),
    ],
    ids=["default", "other"],
)
def test_select_kod_keeps_3c_rows_for_a_v4_file_too_short_for_the_check(
    check_size: int, given: list[int], expected: tuple[DiagnosticKind, str] | None
) -> None:
    coder, diagnostic = select_kod(v4_header(OTHER_KOD, check_size), KODcoding(given), "CroBank.dat")

    assert coder is not None
    assert coder.kod == given
    assert diagnostic == (None if expected is None else Diagnostic(*expected, file="CroBank.dat"))
