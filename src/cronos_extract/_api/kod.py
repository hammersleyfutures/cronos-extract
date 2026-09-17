# ABOUTME: Kod: a CronosPro KOD table, the byte substitution that obfuscates records, as an immutable value.
# ABOUTME: Validates that a table is a permutation of 0-255 and converts it to and from 512 hex digits.
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Self

from ..koddecoder import INITIAL_KOD, KODcoding

HEX_KOD = re.compile(r"[0-9a-fA-F]{512}")


@dataclass(frozen=True)
class Kod:
    """A KOD table: a permutation of the numbers 0 to 255. Two Kods are equal when their tables are."""

    table: tuple[int, ...]

    def __post_init__(self) -> None:
        if (
            len(self.table) != 256
            or any(type(entry) is not int for entry in self.table)
            or sorted(self.table) != list(range(256))
        ):
            raise ValueError("a KOD table must hold each number from 0 to 255 exactly once")

    @classmethod
    def default(cls) -> Self:
        """The KOD table CronosPro uses for databases that are not encrypted with their own."""
        return cls(tuple(INITIAL_KOD))

    @classmethod
    def from_table(cls, table: Sequence[int]) -> Self:
        """A Kod holding `table`. Raises ValueError unless it is a permutation of 0 to 255."""
        return cls(tuple(table))

    @classmethod
    def from_hex(cls, text: str) -> Self:
        """
        A Kod from 512 hex digits, two per table entry, in either case and with nothing else around them.
        Raises ValueError for any other text, or when the digits are not a permutation of 0 to 255.
        """
        if not HEX_KOD.fullmatch(text):
            raise ValueError("a KOD in hex must be exactly 512 hex digits, two per table entry")
        return cls(tuple(bytes.fromhex(text)))

    def hex(self) -> str:
        """The table as 512 lower-case hex digits, as from_hex reads it."""
        return bytes(self.table).hex()


def kod_coder(kod: Kod | None) -> KODcoding | None:
    """The internal decoder for `kod`, or None to read without KOD decoding."""
    return None if kod is None else KODcoding(list(kod.table))
