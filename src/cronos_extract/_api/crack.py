# ABOUTME: Recovers a database's KOD table from byte statistics of its encrypted records, printing nothing.
# ABOUTME: crack_kod uses these steps, and so do the cronos-extract crack subcommands.
import os
from collections.abc import Iterator
from contextlib import ExitStack
from typing import Literal

from ..Datafile import Datafile
from .datafiles import database_directory, list_directory, open_datafile
from .diagnostics import DiagnosticLog
from .errors import NotACronosFile, UnsupportedVersion
from .kod import Kod

# dbcrack reads at most this many records of CroBank and of CroIndex.
DBCRACK_RECORD_LIMIT = 10000


def readable_records(datafile: Datafile, limit: int | None = None) -> Iterator[tuple[int, bytes | None]]:
    """
    Yield (record number, data) for the first `limit` records of `datafile`, or all of them.

    The data is None for a deleted record and for one that cannot be read, which encrypted records read without a
    KOD can be when they look compressed by chance. OSError propagates.
    """
    count = datafile.nrofrecords if limit is None else min(limit, datafile.nrofrecords)
    for recno in range(1, count + 1):
        try:
            data = datafile.readrec(recno)
        except OSError:
            raise
        except Exception:
            data = None
        yield recno, data


def new_xref() -> list[list[int]]:
    """An empty count table: xref[shift][encrypted byte]."""
    return [[0] * 256 for _ in range(256)]


def stru_xref(stru: Datafile) -> list[list[int]]:
    """
    Count, for every shift, how often each encrypted byte occurs in the readable records of `stru`.

    Most bytes of CroStru records are zero, so the commonest encrypted byte at a shift is the one that decodes to zero.
    """
    xref = new_xref()
    for recno, data in readable_records(stru):
        if not data:
            continue
        for offset, byte in enumerate(data):
            xref[(offset + recno) % 256][byte] += 1
    return xref


def bank_and_index_xref(bank: Datafile, index: Datafile) -> list[list[int]]:
    """
    Count the fourth byte of the first DBCRACK_RECORD_LIMIT readable records of `bank` and `index` longer than 11 bytes.

    Compressed records start with a uint16 size, 0x08 and 0x00, so the fourth byte decodes to zero.
    """
    xref = new_xref()
    for datafile in (bank, index):
        for recno, data in readable_records(datafile, DBCRACK_RECORD_LIMIT):
            if data and len(data) > 11:
                xref[(recno + 3) % 256][data[3]] += 1
    return xref


def kod_from_xref(xref: list[list[int]]) -> tuple[list[int], list[int]]:
    """
    Build a KOD table and its confidence from `xref`, where xref[shift][encrypted byte] counts how often that
    encrypted byte was seen at that shift where the plaintext is assumed to be zero.

    Each shift claims the encrypted byte it saw most, with that count as the confidence. When two shifts claim
    the same byte, the higher count keeps it, and on an equal count the first claim stays. Shifts that saw
    no data claim nothing, so their entries keep confidence 0.
    """
    KOD = [0] * 256
    KOD_CONFIDENCE = [0] * 256
    for i, xx in enumerate(xref):
        k, v = max(enumerate(xx), key=lambda kv: kv[1])
        if v <= KOD_CONFIDENCE[k]:
            continue

        #       Display the confidence, matches under 3 usually are unreliable
        KOD[k] = i
        KOD_CONFIDENCE[k] = v
    return KOD, KOD_CONFIDENCE


def fill_single_gap(kod: list[int], confidence: list[int]) -> None:
    """
    When exactly one entry of `kod` is unset and exactly one value is unused, assume they belong together.

    The entry gets confidence 1.
    """
    used = {value for entry, value in enumerate(kod) if confidence[entry] > 0}
    unset_entries = [entry for entry in range(256) if confidence[entry] == 0]
    unused_values = sorted(set(range(256)).difference(used))
    if len(unset_entries) == 1 and len(unused_values) == 1:
        kod[unset_entries[0]] = unused_values[0]
        confidence[unset_entries[0]] = 1


def kod_is_resolved(kod: list[int], confidence: list[int]) -> bool:
    """Whether every entry has a positive confidence and `kod` is a permutation of 0-255, so it can decode."""
    return all(value > 0 for value in confidence) and sorted(kod) == list(range(256))


def crack_kod(path: str | os.PathLike[str], method: Literal["strucrack", "dbcrack"]) -> Kod | None:
    """
    Recover the KOD table of the database in the directory `path` from its encrypted records, printing nothing.

    "strucrack" reads CroStru; "dbcrack" reads CroBank and CroIndex. Returns None when the method cannot recover a
    permutation of 0-255, including when dbcrack finds no readable CroIndex. Records that cannot be read are
    skipped. Raises NotACronosFile or UnsupportedVersion when CroStru or CroBank cannot be read, and ValueError for
    an unknown method.
    """
    if method not in ("strucrack", "dbcrack"):
        raise ValueError(f"unknown crack method {method!r}; use 'strucrack' or 'dbcrack'")
    directory = database_directory(path)
    names = list_directory(directory)
    log = DiagnosticLog(None)
    with ExitStack() as stack:
        stru, _ = open_datafile(directory, names, "Stru", compact=True, kod=None, log=log)
        stack.callback(stru.close)
        bank, _ = open_datafile(directory, names, "Bank", compact=True, kod=None, log=log)
        stack.callback(bank.close)
        if method == "strucrack":
            kod, confidence = kod_from_xref(stru_xref(stru))
            fill_single_gap(kod, confidence)
        else:
            try:
                index, _ = open_datafile(directory, names, "Index", compact=True, kod=None, log=log)
            except (NotACronosFile, UnsupportedVersion):
                return None
            stack.callback(index.close)
            kod, confidence = kod_from_xref(bank_and_index_xref(bank, index))
    return Kod.from_table(kod) if kod_is_resolved(kod, confidence) else None
