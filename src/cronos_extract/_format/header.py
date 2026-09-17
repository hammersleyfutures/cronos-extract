# ABOUTME: Parses the 19-byte header that starts every Cro*.dat file.
# ABOUTME: Reports the format version, its generation and the encoding flags.
import struct
from dataclasses import dataclass
from typing import BinaryIO, Literal

DAT_HEADER = struct.Struct("<8sH5sHH")
MAGIC = b"CroFile\x00"
# Versions with 64-bit file offsets in their .tad entries.
VERSIONS_64BIT = (b"01.03", b"01.05", b"01.11")
# Versions whose records are encoded with the database's own KOD table instead of the default one.
VERSIONS_OWN_KOD = (b"01.04", b"01.05")
V3_VERSIONS = (b"01.02", b"01.03", b"01.04", b"01.05")
V4_VERSIONS = (b"01.11", b"01.13", b"01.14")
V7_VERSIONS = (b"01.19",)

# The CronosPro generations a header's version belongs to.
type Generation = Literal["v3", "v4", "v7", "unknown"]


@dataclass(frozen=True)
class DatHeader:
    """The fields of a Cro*.dat file header."""

    version: bytes
    unknown: int
    encoding: int
    blocksize: int

    @property
    def version_text(self) -> str:
        """The version as text, such as "01.19", with undecodable bytes replaced."""
        return self.version.decode("ascii", "replace")

    @property
    def generation(self) -> Generation:
        """The CronosPro generation of this version: "v3", "v4", "v7", or "unknown"."""
        if self.version in V3_VERSIONS:
            return "v3"
        if self.version in V4_VERSIONS:
            return "v4"
        if self.version in V7_VERSIONS:
            return "v7"
        return "unknown"

    @property
    def use64bit(self) -> bool:
        """Whether the .tad entries hold 64-bit file offsets."""
        return self.version in VERSIONS_64BIT

    @property
    def kod_encoded(self) -> bool:
        """Whether the records are KOD encoded (encoding bit 0)."""
        return bool(self.encoding & 1)

    @property
    def compressed(self) -> bool:
        """Whether the records can be compressed (encoding bit 1)."""
        return bool(self.encoding & 2)

    @property
    def own_kod(self) -> bool:
        """Whether the records are encoded with the database's own KOD table instead of the default one."""
        return self.version in VERSIONS_OWN_KOD or self.generation == "v4"


def read_dat_header(file: BinaryIO, *, where: str) -> DatHeader:
    """
    Read the header from the start of `file`, naming `where` in errors.

    Raises ValueError when the file is shorter than the header or does not start with the Cronos magic.
    """
    file.seek(0)
    data = file.read(DAT_HEADER.size)
    if len(data) < DAT_HEADER.size:
        raise ValueError(f"{where} is shorter than its {DAT_HEADER.size}-byte header")
    magic, unknown, version, encoding, blocksize = DAT_HEADER.unpack(data)
    if magic != MAGIC:
        raise ValueError(f"{where} is not a Cronos file: unknown magic {magic!r}")
    return DatHeader(version=version, unknown=unknown, encoding=encoding, blocksize=blocksize)
