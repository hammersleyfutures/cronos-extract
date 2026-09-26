# Phase 3a: the Datafile core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `Datafile` one record-decoding path and a `.tad` layout per format version, check the CRC of every
compressed chunk (keeping the data and reporting `checksum_mismatch`), bound decompression at 256 MiB, and add a
seeded random-damage test.

**Architecture:** Two new typed modules hold what `Datafile` does today in two copies: `_format/tad.py` turns a raw
`.tad` entry into a `TadEntry` through a `TadLayout` per generation, and `_format/record.py` decodes a record
(read, reassemble extension blocks, KOD-decode, check and decompress) into `RecordParts`. `Datafile` is restructured
in place onto them and fully annotated; `readrec` keeps its contract, `read_record` gives the API the CRC result,
and `dump` prints from the same parts.

**Tech Stack:** Python 3.12+, `struct`, `zlib`, `dataclasses`; uv; ruff (line length 120); ty (every rule an error);
pytest (`filterwarnings = error`); real files from `tests/cronos_builder.py`.

**Spec:** `docs/superpowers/specs/2026-09-25-phase3a-datafile-core-design.md` (decisions A1–A6, Testing,
Documentation, Delivery). Read it before starting any task.

## Global Constraints

- Address the user as "Ben". Ben's global rules in `~/.claude/CLAUDE.md` override skills; the repository's rules are
  in `CLAUDE.md`.
- Work in the repository root on branch `phase3a-datafile-core`. Never push to `master`. GitHub is
  `hammersleyfutures/cronos-extract`; always pass `-R hammersleyfutures/cronos-extract` to `gh pr` commands.
- Test first for every change: write the test, run it, see it fail for the stated reason, write the code, see it
  pass. Real files from `tests/cronos_builder.py` or bytes built in the test; never mock.
- One commit per task. Subject in imperative mood, at most 72 characters; the body says what and why. Every commit
  message ends with exactly these two lines, verbatim:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_01W65g7XvoLhDJL4UHJymUtd`
- Every new code file starts with two comment lines beginning `# ABOUTME: `; neither may contain `coding:` or
  `coding=`.
- New and restructured code is fully type-annotated and ty-clean. Values from unannotated code (`Database`,
  `Datamodel`) are narrowed at the boundary with `int(...)`, `str(...)` or `typing.cast(...)`.
- Names and comments describe what code is, never its history. Never delete a comment unless it is false; a comment
  whose code moves goes with it.
- Before every commit, all clean, each checked by exit code: `uv run ruff format`, `uv run ruff check`,
  `uv run ruff format --check`, `uv run ty check`, `uv run pytest -q`. Guard with explicit checks, e.g.
  `uv run pytest -q > /tmp/t3-pytest.txt 2>&1 || echo FAILED`; `set -e` does not stop a multi-line Bash command,
  and never pipe a checked command through `tail`. Long runs go in the foreground with a timeout, or in the
  background with the output file read directly — never wait on a notification.
- `tests/golden/` must not change. `git diff master -- tests/golden` is empty after every task.
- `inspect` stdout stays byte for byte what it is for every input the golden files and tests cover (Phase 2 D11).
- `local/mash_datasets_with_CroIndex_dat.txt` names real datasets: never commit it, never quote any path or name from
  it anywhere, and report realdata results as counts only.
- When this plan and the code disagree about existing behaviour, follow the code and report the divergence; never
  loosen an assertion to make it pass.
- Plain, factual language; avoid critical, crucial, essential, significant, comprehensive, robust, elegant.
- Scratch files go in `/tmp` with names prefixed by the task number.

## Review Focus

Inputs the spec implies but its test list does not name, most likely to bite first. Each has its test in the task
named.

1. **A CRC mismatch in a CroStru record** (the database definition and table definitions) is not silent: `readrec`
   reports it through `warn`, which the API records as `unexpected_structure` until 3b. Task 5,
   `test_readrec_reports_a_checksum_mismatch_through_warn`.
2. **A record number outside 1 to `nrofrecords`** is a `ValueError` naming the file, not a `struct.error`. Task 5,
   `test_a_record_number_outside_the_file_is_a_value_error`.
3. **A compressed chunk whose 8-byte header is cut off** is a `ValueError`, not a `struct.error` that `inspect`
   would print as a traceback. Task 4, `test_a_chunk_whose_header_is_cut_off_is_a_value_error`.
4. **`inspect crodump` of an inline record the `.dat` file truncates** keeps printing the bytes that are there, as
   today, instead of an error line. Task 5, `test_dump_prints_the_bytes_of_a_truncated_inline_record`.
5. **A `.tad` file shorter than its header, opened directly** (as `inspect` does) is a `ValueError` naming the file.
   Task 5, `test_a_tad_shorter_than_its_header_is_a_value_error`.

## File Structure

Created:

- `src/cronos_extract/_format/tad.py` — `TadEntry`, `TadLayout`, `tad_layout(version)`, the `.tad` constants.
- `src/cronos_extract/_format/record.py` — `RecordSource`, `RecordParts`, `read_stored`, `is_compressed`,
  `decompress`, `decode_record`, `MAX_DECOMPRESSED_BYTES`.
- `tests/test_tad.py`, `tests/test_record.py`, `tests/test_damage.py`.

Modified:

- `src/cronos_extract/Datafile.py` — restructured onto the new modules, annotated; `isv3`, `isv4`, `isv7`,
  `isencrypted`, `iscompressed`, `decompress`, `readextendedrecord`, `tadidx`, `tadidx_seek` and `enumrecords` go.
- `src/cronos_extract/koddecoder.py` — `KODcoding.decode` and `encode` annotated.
- `src/cronos_extract/_api/datafiles.py` — `TAD_HEADER_SIZES` replaced by `tad_layout`.
- `src/cronos_extract/_api/diagnostics.py`, `src/cronos_extract/_api/bank.py` — `CHECKSUM_MISMATCH`.
- `tests/cronos_builder.py`, `tests/test_cronos_builder.py` — real CRCs, wrong CRCs, multi-chunk records, KOD-encoded
  `01.02`/`01.03`, the v3 inline bit.
- `tests/test_datafile.py`, `tests/test_api_bank.py`, `tests/test_cli_export.py`, `tests/test_cli_inspect.py`,
  `tests/test_realdata.py`.
- `README.md`, `CLAUDE.md`, `docs/cronos-research.md`, `docs/superpowers/specs/2026-09-15-modernisation-roadmap-design.md`,
  this plan.

---

### Task 1: Commit this plan

- [ ] **Step 1:** `git branch --show-current` prints `phase3a-datafile-core`; `uv run ruff format --check
  docs/superpowers/plans/2026-09-25-phase3a-datafile-core.md` exits 0.
- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/plans/2026-09-25-phase3a-datafile-core.md
git commit -m "Plan Phase 3a: the Datafile core" -m "The task list, interfaces and tests for the Phase 3a design, in its delivery order.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01W65g7XvoLhDJL4UHJymUtd"
```

---

### Task 2: The builder gaps

**Files:**
- Modify: `tests/cronos_builder.py`, `tests/test_cronos_builder.py`

**Interfaces:**
- Produces:
  - `compressed_chunk(compdata: bytes, checksum: int) -> bytes`
  - `compressed_record(*payloads: bytes, wrong_checksums: Collection[int] = ()) -> bytes` — one chunk per payload,
    each with the CRC-32 of its payload, except the chunks whose index (from 0) is in `wrong_checksums`, whose CRC is
    inverted (`crc ^ 0xFFFFFFFF`).
  - `corrupt_compressed_record() -> bytes` — unchanged behaviour (not valid deflate).
  - `V3_INLINE_BIT = 1 << 31`, replacing `INLINE_RECORD_FLAGS << 24` where the builder writes a v3 length.
  - `write_datafile(..., encoded: bool = False)` and `write_database(..., encoded: bool = False)`: with no `kod`,
    `encoded=True` KOD-encodes the records with the default table (`INITIAL_KOD`) and sets encoding bit 0, which every
    version may carry.

- [ ] **Step 1: Write the failing builder tests**

Append to `tests/test_cronos_builder.py` (import what is new from `cronos_builder`, and `struct`, `zlib`,
`cronos_extract` if not already imported):

```python
def test_compressed_record_holds_the_crc_of_each_chunk() -> None:
    record = compressed_record(b"one", b"two", wrong_checksums={1})

    offset = 0
    crcs = []
    while offset < len(record) - 3:
        size, _ = struct.unpack_from(">HH", record, offset)
        (crc,) = struct.unpack_from("<L", record, offset + 4)
        crcs.append(crc)
        offset += size + 2

    assert crcs == [zlib.crc32(b"one"), zlib.crc32(b"two") ^ 0xFFFFFFFF]
    assert record.endswith(b"\x00\x00\x02")


@pytest.mark.parametrize("version", [b"01.02", b"01.03", b"01.04"])
def test_a_v3_inline_record_sets_bit_31_of_its_length(tmp_path: Path, version: bytes) -> None:
    write_datafile(tmp_path, "Bank", [b"hello"], version=version)

    header, entry = tad_layout(version)
    tad = (tmp_path / "CroBank.tad").read_bytes()
    _, length, _ = entry.unpack_from(tad, len(header))

    assert length == 5 | V3_INLINE_BIT


@pytest.mark.parametrize("version", [b"01.02", b"01.03"])
def test_a_database_of_a_default_kod_version_can_be_written_kod_encoded(tmp_path: Path, version: bytes) -> None:
    fields = [b""] * TEST_TABLE_FIELD_COUNT
    fields[0] = b"encoded"
    dbdir = write_database(tmp_path / "db", [bank_record(TEST_TABLE_ID, fields)], version=version, encoded=True)

    assert (Path(dbdir) / "CroBank.dat").read_bytes()[15] & 1
    with cronos_extract.open(dbdir) as bank:
        (record,) = bank.tables[0].records()
        assert record.fields[1].text == "encoded"
```

(`read_bytes()[15]` is the low byte of the header's encoding field: magic 8 bytes, unknown uint16, version 5 bytes.)

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest -q tests/test_cronos_builder.py` — Expected: `ImportError` for `V3_INLINE_BIT` (and, once that
exists, `TypeError` for `wrong_checksums` and `encoded`).

- [ ] **Step 3: Change the builder**

In `tests/cronos_builder.py`: replace the `INLINE_RECORD_FLAGS` constant and its comment with

```python
# A v3 .tad entry keeps its inline flag in bit 31 of the length field; the length is bits 0-30.
V3_INLINE_BIT = 1 << 31
```

and in `write_datafile` write `len(stored) | V3_INLINE_BIT` for v3 entries. Replace `compressed_chunk`,
`compressed_record` and `corrupt_compressed_record` with:

```python
def compressed_chunk(compdata: bytes, checksum: int) -> bytes:
    """Encode `compdata` as one chunk of Datafile's compressed record format: size, flag, CRC-32, then the data.

    A compressed record is one or more of these chunks followed by the final marker b"\\x00\\x00\\x02".
    """
    return struct.pack(">HH", 6 + len(compdata), 0x800) + struct.pack("<L", checksum) + compdata


def compressed_record(*payloads: bytes, wrong_checksums: Collection[int] = ()) -> bytes:
    """Compress each of `payloads` into one chunk of Datafile's compressed record format, in order.

    Each chunk holds the CRC-32 of its payload, except those whose index, counted from 0, is in `wrong_checksums`,
    whose CRC-32 is inverted.
    """
    chunks = []
    for index, payload in enumerate(payloads):
        coder = zlib.compressobj(9, zlib.DEFLATED, -15)
        checksum = zlib.crc32(payload) ^ (0xFFFFFFFF if index in wrong_checksums else 0)
        chunks.append(compressed_chunk(coder.compress(payload) + coder.flush(), checksum))
    return b"".join(chunks) + b"\x00\x00\x02"


def corrupt_compressed_record() -> bytes:
    """Return record bytes that pass Datafile's compression check but whose data is not valid deflate output."""
    return compressed_chunk(b"\xff\xff\xff\xff", 0) + b"\x00\x00\x02"
```

Add `encoded: bool = False` to `write_datafile` (documented: "With `encoded` and no `kod`, the records are KOD-encoded
with the default table and the encoding bit is set, as CronosPro stores them in many files of every version.") and
build the coder as

```python
    if kod is not None:
        coder = KODcoding(list(kod))
    elif encoded:
        coder = KODcoding(INITIAL_KOD)
    else:
        coder = None
```

keeping the existing check that a `kod` is given only for `OWN_KOD_VERSIONS`. Add `encoded: bool = False` to
`write_database`, passed to both `write_datafile` calls and to the `CroIndex` one. Import `Collection` from
`collections.abc` and `INITIAL_KOD` from `cronos_extract.koddecoder`.

- [ ] **Step 4: Run every check**

Run: `uv run pytest -q` — Expected: all pass. Compressed builder records now carry real CRCs; nothing reads them yet.
Then `uv run ruff format && uv run ruff check && uv run ty check`.

- [ ] **Step 5: Commit**

```bash
git add tests/cronos_builder.py tests/test_cronos_builder.py
git commit -m "Build compressed records with real CRCs and KOD-encoded v3 files" -m "Compressed chunks carry the CRC-32 of their payload, or an inverted one on request, and a record can hold several chunks. Files of the default-KOD versions can be written KOD-encoded, and v3 lengths set the inline flag as bit 31.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01W65g7XvoLhDJL4UHJymUtd"
```

---

### Task 3: `_format/tad.py`

**Files:**
- Create: `src/cronos_extract/_format/tad.py`, `tests/test_tad.py`

**Interfaces:**
- Consumes: `_format/header.py`'s `V3_VERSIONS`, `V4_VERSIONS`, `VERSIONS_64BIT`.
- Produces:
  - `TadEntry(offset: int, length: int, flags: int, checksum: int, inline: bool, deleted: bool)`, frozen. For a
    deleted entry, `offset`, `length` and `checksum` are the raw fields.
  - `TadLayout(header: struct.Struct, entry: struct.Struct, generation: Literal["v3", "v4"])`, frozen, with
    `deleted_counts(data: bytes) -> tuple[int, int]` and `parse(data: bytes) -> TadEntry`.
  - `tad_layout(version: bytes) -> TadLayout | None`.
  - `DELETED_LENGTH = 0xFFFFFFFF`, `V3_INLINE_BIT = 1 << 31`, `V3_INLINE_FLAGS = 0x80`, `V4_FLAG_SHIFT = 56`.

The entry size follows today's `Datafile` exactly: 16 bytes (`<QLL`) for the versions in `VERSIONS_64BIT`, else 12
(`<LLL`) — including `01.13` and `01.14`, for which no real file exists.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tad.py`:

```python
# ABOUTME: Tests for the .tad layouts: where each generation keeps a record's offset, length and flags.
# ABOUTME: Entries are built as bytes, as CronosPro writes them.
import struct

import pytest

from cronos_extract._format.tad import DELETED_LENGTH, V3_INLINE_BIT, TadEntry, tad_layout

V3_32 = struct.Struct("<LLL")
ENTRY_64 = struct.Struct("<QLL")


@pytest.mark.parametrize(
    ("version", "header_size", "entry_size"),
    [(b"01.02", 8, 12), (b"01.03", 8, 16), (b"01.04", 8, 12), (b"01.05", 8, 16), (b"01.11", 16, 16)],
)
def test_each_version_has_its_header_and_entry_size(version: bytes, header_size: int, entry_size: int) -> None:
    layout = tad_layout(version)

    assert layout is not None
    assert (layout.header.size, layout.entry.size) == (header_size, entry_size)


@pytest.mark.parametrize("version", [b"01.19", b"99.99"])
def test_a_version_this_release_cannot_read_has_no_layout(version: bytes) -> None:
    assert tad_layout(version) is None


def test_a_v3_inline_entry_has_its_flag_in_bit_31() -> None:
    layout = tad_layout(b"01.02")
    assert layout is not None

    assert layout.parse(V3_32.pack(0x100, 5 | V3_INLINE_BIT, 7)) == TadEntry(0x100, 5, 0x80, 7, True, False)


def test_a_v3_entry_without_bit_31_is_extended() -> None:
    layout = tad_layout(b"01.02")
    assert layout is not None

    assert layout.parse(V3_32.pack(0x100, 20, 0)) == TadEntry(0x100, 20, 0, 0, False, False)


def test_bits_24_to_30_of_a_v3_length_are_length() -> None:
    layout = tad_layout(b"01.03")
    assert layout is not None

    entry = layout.parse(ENTRY_64.pack(0x100, 0x7F000001 | V3_INLINE_BIT, 0))

    assert (entry.length, entry.inline) == (0x7F000001, True)


def test_a_v4_entry_keeps_its_flags_in_the_top_byte_of_the_offset() -> None:
    layout = tad_layout(b"01.11")
    assert layout is not None

    assert layout.parse(ENTRY_64.pack(0x04 << 56 | 0x100, 9, 3)) == TadEntry(0x100, 9, 0x04, 3, True, False)
    assert layout.parse(ENTRY_64.pack(0x100, 9, 3)) == TadEntry(0x100, 9, 0, 3, False, False)


@pytest.mark.parametrize(("version", "entry"), [(b"01.02", V3_32), (b"01.11", ENTRY_64)])
def test_a_deleted_entry_keeps_its_raw_fields(version: bytes, entry: struct.Struct) -> None:
    layout = tad_layout(version)
    assert layout is not None

    parsed = layout.parse(entry.pack(0x1234, DELETED_LENGTH, 0x55))

    assert parsed == TadEntry(0x1234, DELETED_LENGTH, 0, 0x55, False, True)


def test_the_header_gives_the_deleted_record_counts() -> None:
    v3, v4 = tad_layout(b"01.02"), tad_layout(b"01.11")
    assert v3 is not None and v4 is not None

    assert v3.deleted_counts(struct.pack("<2L", 3, 40)) == (3, 40)
    assert v4.deleted_counts(struct.pack("<4L", 0xFFFFFFFE, 3, 40, 0)) == (3, 40)
```

- [ ] **Step 2: Run them to see them fail** — `uv run pytest -q tests/test_tad.py`: `ModuleNotFoundError` for
  `cronos_extract._format.tad`.

- [ ] **Step 3: Write `_format/tad.py`**

```python
# ABOUTME: The layout of a Cro*.tad index for each CronosPro generation: its header and its entries.
# ABOUTME: A TadLayout turns a raw entry into a TadEntry: where a record is, how long, and whether inline or deleted.
import struct
from dataclasses import dataclass
from typing import Literal

from .header import V3_VERSIONS, V4_VERSIONS, VERSIONS_64BIT

# The length field of a deleted record's entry.
DELETED_LENGTH = 0xFFFFFFFF
# A v3 entry keeps its inline flag in bit 31 of the length field and the length in bits 0-30.
V3_INLINE_BIT = 1 << 31
# The flag byte of an inline v3 entry: the top byte of its length field, which holds only bit 31.
V3_INLINE_FLAGS = 0x80
# A v4 entry keeps its flags in the top byte of the offset field. The research notes say 04 marks data (compressed
# v3-style), 02 and 03 a deleted record and 00 an extended record; 3d checks 02 and 03 against real databases.
V4_FLAG_SHIFT = 56
V3_HEADER = struct.Struct("<2L")
V4_HEADER = struct.Struct("<4L")
# 01.03, 01.05 and 01.11 have 64-bit file offsets; 01.02 and 01.04 have 32-bit ones.
ENTRY_64BIT = struct.Struct("<QLL")
ENTRY_32BIT = struct.Struct("<LLL")


@dataclass(frozen=True)
class TadEntry:
    """
    One entry of a .tad index: where a record's data starts in the .dat file, how many bytes it has, and how it is
    stored.

    `flags` is the entry's flag byte. An `inline` record is stored whole at `offset`; any other starts with an
    extended-record header and continues in extension blocks. A `deleted` entry keeps its raw fields.
    """

    offset: int
    length: int
    flags: int
    checksum: int
    inline: bool
    deleted: bool


@dataclass(frozen=True)
class TadLayout:
    """How one generation lays out its .tad header and entries."""

    header: struct.Struct
    entry: struct.Struct
    generation: Literal["v3", "v4"]

    def deleted_counts(self, data: bytes) -> tuple[int, int]:
        """The number of deleted records and the offset of the first deleted entry, from the .tad header `data`."""
        fields = self.header.unpack(data)
        if self.generation == "v3":
            return int(fields[0]), int(fields[1])
        return int(fields[1]), int(fields[2])

    def parse(self, data: bytes) -> TadEntry:
        """The entry that the raw .tad entry `data` describes."""
        offset, length, checksum = self.entry.unpack(data)
        if length == DELETED_LENGTH:
            return TadEntry(offset, length, 0, checksum, inline=False, deleted=True)
        if self.generation == "v3":
            inline = bool(length & V3_INLINE_BIT)
            flags = V3_INLINE_FLAGS if inline else 0
            return TadEntry(offset, length & ~V3_INLINE_BIT, flags, checksum, inline=inline, deleted=False)
        flags = offset >> V4_FLAG_SHIFT
        offset &= (1 << V4_FLAG_SHIFT) - 1
        return TadEntry(offset, length, flags, checksum, inline=flags != 0, deleted=False)


def tad_layout(version: bytes) -> TadLayout | None:
    """The .tad layout of files of `version`, or None for a version whose .tad this release cannot read."""
    entry = ENTRY_64BIT if version in VERSIONS_64BIT else ENTRY_32BIT
    if version in V3_VERSIONS:
        return TadLayout(V3_HEADER, entry, "v3")
    if version in V4_VERSIONS:
        return TadLayout(V4_HEADER, entry, "v4")
    return None
```

- [ ] **Step 4: Run the tests** — `uv run pytest -q tests/test_tad.py`: all pass. Then every check.
- [ ] **Step 5: Commit** — `git add src/cronos_extract/_format/tad.py tests/test_tad.py`; subject "Add the .tad
  layout of each CronosPro generation"; body says the v3 inline flag is bit 31 (spec A2) and nothing uses the module
  yet; the two trailer lines.

---

### Task 4: `_format/record.py`

**Files:**
- Create: `src/cronos_extract/_format/record.py`, `tests/test_record.py`
- Modify: `src/cronos_extract/koddecoder.py` (annotate `KODcoding.decode` and `encode`:
  `def decode(self, o: int, data: bytes) -> bytes`, `def encode(self, o: int, data: bytes) -> bytes`)

**Interfaces:**
- Consumes: Task 3's `TadEntry`; `koddecoder.KODcoding`; Task 2's `compressed_record`, `corrupt_compressed_record`,
  `random_kod`.
- Produces:
  - `MAX_DECOMPRESSED_BYTES = 256 * 1024 * 1024`
  - `RecordSource(name: str, read: Callable[[int, int], bytes], size: int, blocksize: int, use64bit: bool, kod:
    KODcoding | None)`, frozen, with property `filename -> str` (`f"Cro{name}.dat"`). `kod` is None when the file's
    records are not KOD-encoded.
  - `RecordParts(data: bytes, flags: int, extended: bool = False, chain: tuple[int, ...] = (), length: int = 0,
    tail: bytes = b"", compressed: bool = False, mismatched_chunks: tuple[int, ...] = ())`, frozen.
  - `read_stored(source: RecordSource, recno: int, entry: TadEntry, *, require_whole: bool = True) -> RecordParts`
    — the stored bytes, reassembled and KOD-decoded, not decompressed.
  - `is_compressed(data: bytes) -> bool` — today's `Datafile.iscompressed`, unchanged.
  - `decompress(data: bytes, where: str) -> tuple[bytes, tuple[int, ...]]` — the data and the mismatched chunks.
  - `decode_record(source: RecordSource, recno: int, entry: TadEntry) -> RecordParts`.

Error messages are today's, word for word (`tests/test_datafile.py` checks several): "`record N in CroX.dat has L
bytes at offset 0x..., which runs past the end of the file`", "`... is shorter than its 8-byte extended record
header`", "`... claims N bytes, more than the file holds`", "`... has a loop in its extension blocks at offset
0x...`", "`... has an extension block past the end of the file at offset 0x...`", "`corrupt compressed data: ...`".

- [ ] **Step 1: Write the failing tests**

Create `tests/test_record.py`:

```python
# ABOUTME: Tests for decoding one record: extension blocks, KOD decoding, CRC checking and the decompression limit.
# ABOUTME: Records are built as bytes and read through a RecordSource over those bytes.
import struct
import tracemalloc
import zlib

import pytest
from cronos_builder import compressed_record, corrupt_compressed_record, random_kod

from cronos_extract._format.record import (
    MAX_DECOMPRESSED_BYTES,
    RecordParts,
    RecordSource,
    decode_record,
    decompress,
)
from cronos_extract._format.tad import TadEntry
from cronos_extract.koddecoder import KODcoding


def source_of(data: bytes, *, blocksize: int = 16, kod: KODcoding | None = None) -> RecordSource:
    """A 32-bit RecordSource reading `data` as the .dat file of CroBank."""
    return RecordSource("Bank", lambda offset, size: data[offset : offset + size], len(data), blocksize, False, kod)


def inline(offset: int, length: int) -> TadEntry:
    return TadEntry(offset, length, 0x80, 0, True, False)


def extended(offset: int, length: int) -> TadEntry:
    return TadEntry(offset, length, 0, 0, False, False)


def test_an_inline_record_is_its_bytes() -> None:
    assert decode_record(source_of(b"xxhelloyy"), 1, inline(2, 5)) == RecordParts(b"hello", 0x80)


def test_a_record_is_kod_decoded_with_its_record_number_as_shift() -> None:
    kod = KODcoding(random_kod(seed=1))
    stored = kod.encode(3, b"hello")

    assert decode_record(source_of(stored, kod=kod), 3, inline(0, 5)).data == b"hello"


def test_a_compressed_record_is_decompressed_and_its_crc_checked() -> None:
    record = compressed_record(b"one", b"two", b"three")

    parts = decode_record(source_of(record), 1, inline(0, len(record)))

    assert (parts.data, parts.compressed, parts.mismatched_chunks) == (b"onetwothree", True, ())


def test_a_crc_mismatch_keeps_the_data_and_names_the_chunk() -> None:
    record = compressed_record(b"one", b"two", b"three", wrong_checksums={1})

    parts = decode_record(source_of(record), 1, inline(0, len(record)))

    assert (parts.data, parts.mismatched_chunks) == (b"onetwothree", (1,))


def test_a_record_in_extension_blocks_is_reassembled() -> None:
    first = struct.pack("<LL", 100, 20) + b"01234567"
    block = struct.pack("<L", 200) + b"89abcdefghij"
    data = first + bytes(100 - len(first)) + block

    parts = decode_record(source_of(data), 1, extended(0, len(first)))

    assert parts == RecordParts(b"0123456789abcdefghij", 0, extended=True, chain=(100, 200), length=20)


@pytest.mark.parametrize(
    ("data", "entry", "message"),
    [
        (b"short", inline(0, 9), "record 1 in CroBank.dat has 9 bytes at offset 0x0, which runs past the end"),
        (b"1234", extended(0, 4), "record 1 in CroBank.dat is shorter than its 8-byte extended record header"),
        (struct.pack("<LL", 0, 999), extended(0, 8), "record 1 in CroBank.dat claims 999 bytes"),
        (struct.pack("<LL", 8, 40) + struct.pack("<L", 8) + bytes(12) + bytes(40), extended(0, 8), "has a loop"),
        (struct.pack("<LL", 900, 40) + bytes(40), extended(0, 8), "has an extension block past the end"),
        (corrupt_compressed_record(), None, "corrupt compressed data: "),
    ],
    ids=["past-the-end", "short-header", "longer-than-file", "loop", "block-past-end", "corrupt-deflate"],
)
def test_a_record_that_cannot_be_decoded_is_a_value_error(data: bytes, entry: TadEntry | None, message: str) -> None:
    with pytest.raises(ValueError, match=message.replace("(", r"\(")):
        decode_record(source_of(data), 1, entry or inline(0, len(data)))


def test_a_chunk_whose_header_is_cut_off_is_a_value_error() -> None:
    with pytest.raises(ValueError, match="cut off"):
        decompress(struct.pack(">HH", 10, 0x800) + b"\x00\x00\x02", "record 1 in CroBank.dat")


def test_a_record_that_decompresses_past_the_limit_is_refused_without_holding_it() -> None:
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    chunk_payload = bytes(32 * 1024 * 1024)
    compdata = compressor.compress(chunk_payload) + compressor.flush()
    assert len(compdata) <= 0xFFFF - 6
    chunk = struct.pack(">HH", 6 + len(compdata), 0x800) + struct.pack("<L", zlib.crc32(chunk_payload)) + compdata
    del chunk_payload
    bomb = chunk * 40 + b"\x00\x00\x02"

    tracemalloc.start()
    try:
        with pytest.raises(ValueError, match=f"more than {MAX_DECOMPRESSED_BYTES} bytes"):
            decompress(bomb, "record 1 in CroBank.dat")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    # Forty chunks would decompress to 1.25 GiB; stopping at the limit keeps the peak far below that.
    assert peak < 3 * MAX_DECOMPRESSED_BYTES
```

- [ ] **Step 2: Run them to see them fail** — `uv run pytest -q tests/test_record.py`: `ModuleNotFoundError` for
  `cronos_extract._format.record`.

- [ ] **Step 3: Write `_format/record.py`**

`is_compressed` is `Datafile.iscompressed`'s body, unchanged; the extension-block loop is
`Datafile.readextendedrecord`'s, unchanged apart from reading through `source`.

```python
# ABOUTME: Decodes one record of a Cro*.dat file: reassembles extension blocks, KOD-decodes, checks and decompresses.
# ABOUTME: Every reader of records goes through decode_record; a record may decompress to at most 256 MiB.
import struct
import zlib
from collections.abc import Callable
from dataclasses import dataclass, replace

from ..koddecoder import KODcoding
from .tad import TadEntry

# The most bytes a record may decompress to; a crafted record could otherwise exhaust memory.
MAX_DECOMPRESSED_BYTES = 256 * 1024 * 1024
# A compressed record ends with a chunk of size 0 followed by 2.
COMPRESSED_END = b"\x00\x00\x02"
# Each chunk starts with a big-endian size (of flag, CRC and data) and flag, then a little-endian CRC-32 of the
# chunk's decompressed data.
CHUNK_HEADER = struct.Struct(">HH")
CHUNK_CRC = struct.Struct("<L")
CHUNK_PREFIX_SIZE = CHUNK_HEADER.size + CHUNK_CRC.size


@dataclass(frozen=True)
class RecordSource:
    """What decoding a record needs from a .dat file: its name, a way to read it, its size and layout, and its KOD."""

    name: str
    read: Callable[[int, int], bytes]
    size: int
    blocksize: int
    use64bit: bool
    kod: KODcoding | None

    @property
    def filename(self) -> str:
        return f"Cro{self.name}.dat"


@dataclass(frozen=True)
class RecordParts:
    """
    A record as decoding found it.

    `data` is the decoded record, decompressed when `compressed`. `flags` is its .tad entry's flag byte. For an
    `extended` record, `chain` holds the first block's offset from the record header, then the next-block offset
    read from each block, `length` is the length the header gives, and `tail` holds the bytes read past the record's
    end. `mismatched_chunks` lists the compressed chunks, counted from 0, whose CRC-32 does not match their data.
    """

    data: bytes
    flags: int
    extended: bool = False
    chain: tuple[int, ...] = ()
    length: int = 0
    tail: bytes = b""
    compressed: bool = False
    mismatched_chunks: tuple[int, ...] = ()


def read_stored(source: RecordSource, recno: int, entry: TadEntry, *, require_whole: bool = True) -> RecordParts:
    """
    Record `recno` as stored: its bytes, reassembled from extension blocks and KOD-decoded, not decompressed.

    Raises ValueError naming the record when it cannot be read; with `require_whole` false, an inline record the file
    cuts short is returned as far as it goes, as inspect crodump shows it.
    """
    where = f"record {recno} in {source.filename}"
    data = source.read(entry.offset, entry.length)
    if len(data) < entry.length and (require_whole or not entry.inline):
        raise ValueError(
            f"{where} has {entry.length} bytes at offset {entry.offset:#x}, which runs past the end of the file"
        )
    parts = RecordParts(data, entry.flags)
    if data and not entry.inline:
        parts = read_extended(source, where, data, entry.flags)
    if source.kod is not None:
        parts = replace(parts, data=source.kod.decode(recno, parts.data))
    return parts


def read_extended(source: RecordSource, where: str, first: bytes, flags: int) -> RecordParts:
    """
    Reassemble a record from extension blocks, given `first`, the record's first block.

    The first block holds the offset of the first extension block, the record length, then data; each
    extension block starts with the offset of the next one. Raises ValueError when the header is truncated,
    the length exceeds the file, the blocks loop, or a block lies past the end of the file.
    """
    headersize, pointersize, pointerformat = (12, 8, "<Q") if source.use64bit else (8, 4, "<L")
    if len(first) < headersize:
        raise ValueError(f"{where} is shorter than its {headersize}-byte extended record header")
    extofs, extlen = struct.unpack("<QL" if source.use64bit else "<LL", first[:headersize])
    if extlen > source.size:
        raise ValueError(f"{where} claims {extlen} bytes, more than the file holds")

    data = first[headersize:]
    chain = [extofs]
    while len(data) < extlen:
        if extofs in chain[:-1]:
            raise ValueError(f"{where} has a loop in its extension blocks at offset {extofs:#x}")
        block = source.read(extofs, source.blocksize)
        if len(block) <= pointersize:
            raise ValueError(f"{where} has an extension block past the end of the file at offset {extofs:#x}")
        (extofs,) = struct.unpack(pointerformat, block[:pointersize])
        chain.append(extofs)
        data += block[pointersize:]
    return RecordParts(data[:extlen], flags, extended=True, chain=tuple(chain), length=extlen, tail=data[extlen:])


def is_compressed(data: bytes) -> bool:
    """
    Check if this record looks like a compressed record.
    """
    if len(data) < 11:
        return False
    if data[-3:] != b"\x00\x00\x02":
        return False
    o = 0
    while o < len(data) - 3:
        size, flag = struct.unpack_from(">HH", data, o)
        if flag != 0x800 and flag != 0x008:
            return False
        o += size + 2
    return True


def decompress(data: bytes, where: str) -> tuple[bytes, tuple[int, ...]]:
    """
    Decompress a record, returning its data and the chunks, counted from 0, whose CRC-32 does not match.

    Compressed records can have several chunks of compressed data.
    Note that the compression header uses a mix of big-endian and little numbers.

    each chunk has the following format:
        size  - big endian uint16, size of flag + crc + compdata
        flag  - big endian uint16 - always 0x800
        crc   - little endian uint32, crc32 of the decompressed data
    the final chunk has only 3 bytes: a zero size followed by a 2.

    the crc algorithm is the one labeled 'crc-32' on this page:
        http://crcmod.sourceforge.net/crcmod.predefined.html

    Raises ValueError naming `where` when a chunk header is cut off, the data is not valid deflate output, or the
    record would decompress to more than MAX_DECOMPRESSED_BYTES; decompression stops at that limit.
    """
    result = bytearray()
    mismatched = []
    offset = 0
    chunk = 0
    while offset < len(data) - len(COMPRESSED_END):
        if offset + CHUNK_PREFIX_SIZE > len(data):
            raise ValueError(f"{where} has a compressed chunk cut off in its header at byte {offset}")
        # note the mix of bigendian and little endian numbers here.
        size, _ = CHUNK_HEADER.unpack_from(data, offset)
        (crc,) = CHUNK_CRC.unpack_from(data, offset + CHUNK_HEADER.size)
        room = MAX_DECOMPRESSED_BYTES - len(result)
        try:
            out = zlib.decompressobj(-15).decompress(data[offset + CHUNK_PREFIX_SIZE : offset + 2 + size], room + 1)
        except zlib.error as e:
            raise ValueError(f"corrupt compressed data: {e}") from e
        if len(out) > room:
            raise ValueError(
                f"{where} decompresses to more than {MAX_DECOMPRESSED_BYTES} bytes, the most a record may hold"
            )
        if zlib.crc32(out) != crc:
            mismatched.append(chunk)
        result += out
        chunk += 1
        offset += size + 2
    return bytes(result), tuple(mismatched)


def decode_record(source: RecordSource, recno: int, entry: TadEntry) -> RecordParts:
    """Record `recno`, whose .tad entry is `entry`, read, reassembled, KOD-decoded, checked and decompressed."""
    parts = read_stored(source, recno, entry)
    if not is_compressed(parts.data):
        return parts
    data, mismatched = decompress(parts.data, f"record {recno} in {source.filename}")
    return replace(parts, data=data, compressed=True, mismatched_chunks=mismatched)
```

(`data[offset + 8 : offset + 2 + size]` is today's `data[o + 8 : o + 8 + size - 6]`.)

- [ ] **Step 4: Run the tests** — `uv run pytest -q tests/test_record.py`: all pass. Then every check.
- [ ] **Step 5: Commit** — `git add src/cronos_extract/_format/record.py src/cronos_extract/koddecoder.py
  tests/test_record.py`; subject "Decode records through one pipeline with CRC checks and a size limit"; the body
  names A3 and A4; the two trailer lines.

---

### Task 5: `Datafile` on the new modules

**Files:**
- Modify: `src/cronos_extract/Datafile.py` (the whole file), `src/cronos_extract/_api/datafiles.py`
- Test: `tests/test_datafile.py`

**Interfaces:**
- Consumes: Tasks 3 and 4.
- Produces (every later task relies on these): `Datafile(name: str, dat: BinaryIO, tad: BinaryIO, compact: bool,
  kod: KODcoding | None, warn: Callable[[str], None] = warn_on_stderr)`; attributes `name`, `header: DatHeader`,
  `layout: TadLayout`, `version`, `encoding`, `blocksize`, `use64bit`, `hdrunk`, `datsize`, `nrdeleted`,
  `firstdeleted`, `nrofrecords`, `kod`, `source: RecordSource`; methods `entry(index: int) -> TadEntry` (from 0),
  `readdata(ofs: int, size: int) -> bytes`, `read_record(recno: int) -> RecordParts | None`,
  `readrec(recno: int) -> bytes | None`, `enumunreferenced(...)`, `dump(args: argparse.Namespace) -> None`, `close()`.

Before editing, run `rg -n 'enumrecords|tadidx|iscompressed|isencrypted|isv[347]|readextendedrecord' src tests`: only
`Datafile.py` may use them; if anything else does, stop and report it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_datafile.py` (import `write_datafile`, `compressed_record`, `V3_INLINE_BIT` and `write_raw_datafile`
from `cronos_builder` as needed, and `argparse`, `io`):

```python
def dump_args(**options: object) -> argparse.Namespace:
    return argparse.Namespace(maxrecs=0xFFFFFFFF, verbose=False, ascdump=False, decompress=True, **options)


def test_readrec_reports_a_checksum_mismatch_through_warn(tmp_path: Path) -> None:
    write_datafile(tmp_path, "Stru", [compressed_record(b"definition", wrong_checksums={0})])
    messages: list[str] = []

    with (tmp_path / "CroStru.dat").open("rb") as dat, (tmp_path / "CroStru.tad").open("rb") as tad:
        datafile = Datafile("Stru", dat, tad, False, None, warn=messages.append)
        assert datafile.readrec(1) == b"definition"

    assert messages == ["WARN: record 1 in CroStru.dat has compressed data whose checksum does not match; it is kept"]


def test_read_record_gives_the_mismatched_chunks(tmp_path: Path) -> None:
    write_datafile(tmp_path, "Bank", [compressed_record(b"a", b"b", wrong_checksums={1})])

    with open_bank(tmp_path) as bank:
        parts = bank.read_record(1)

    assert parts is not None
    assert (parts.data, parts.mismatched_chunks) == (b"ab", (1,))


@pytest.mark.parametrize("recno", [0, -1, 2])
def test_a_record_number_outside_the_file_is_a_value_error(tmp_path: Path, recno: int) -> None:
    write_datafile(tmp_path, "Bank", [b"only"])

    with open_bank(tmp_path) as bank, pytest.raises(ValueError, match=f"CroBank.dat has no record {recno}"):
        bank.readrec(recno)


def test_a_tad_shorter_than_its_header_is_a_value_error(tmp_path: Path) -> None:
    write_datafile(tmp_path, "Bank", [b"x"])
    (tmp_path / "CroBank.tad").write_bytes(b"\x00\x00\x00")

    with pytest.raises(ValueError, match="CroBank.tad is shorter than its 8-byte header"), open_bank(tmp_path):
        pass


def test_dump_prints_the_bytes_of_a_truncated_inline_record(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_raw_datafile(tmp_path, "Bank", b"abc", [(DAT_PREFIX_SIZE, 10 | V3_INLINE_BIT)], version=b"01.02")

    with open_bank(tmp_path) as bank:
        bank.dump(dump_args())

    (line,) = [line for line in capsys.readouterr().out.splitlines() if line.startswith("    1:")]
    assert "616263" in line
    assert "<" not in line
```

`open_bank` and `DAT_PREFIX_SIZE` already exist in the file's helpers or `cronos_builder`; use them. The `dump`
test asserts today's behaviour (the bytes are printed); run it against the current code first — it must already pass
there, and it keeps passing after the restructure.

- [ ] **Step 2: Run them** — `uv run pytest -q tests/test_datafile.py`: the new tests fail except
  `test_dump_prints_the_bytes_of_a_truncated_inline_record`, which pins today's behaviour. (Spec A2's flag rule is
  pinned by `tests/test_tad.py`: on real files the old and new rules read the same lengths.)

- [ ] **Step 3: Rewrite `Datafile.py` in place**

Replace the file with the following. It keeps every method's contract and comment (moved comments now live in
`tad.py` and `record.py`), and prints exactly what `dump` prints today.

```python
# ABOUTME: Datafile: reads the records of one CronosPro .dat file through its .tad index.
# ABOUTME: Decodes each record through _format/record.py and dumps them, byte range by byte range, for inspect.
import argparse
import io
from collections.abc import Callable, Iterator
from typing import BinaryIO

from . import koddecoder
from ._format.header import read_dat_header
from ._format.record import RecordParts, RecordSource, decode_record, decompress, is_compressed, read_stored
from ._format.tad import TadEntry, tad_layout
from .hexdump import tohex, toout, warn_on_stderr
from .koddecoder import KODcoding


class Datafile:
    """Represent a single .dat with it's .tad index file"""

    def __init__(
        self,
        name: str,
        dat: BinaryIO,
        tad: BinaryIO,
        compact: bool,
        kod: KODcoding | None,
        warn: Callable[[str], None] = warn_on_stderr,
    ) -> None:
        self.warn = warn
        self.name = name
        self.dat = dat
        self.tad = tad
        self.compact = compact

        self.readdathdr()
        self.readtad()

        self.dat.seek(0, io.SEEK_END)
        self.datsize = self.dat.tell()

        # A file that is not encrypted with its own KOD table is decoded with the default one, whatever KOD is given.
        self.kod = kod if kod is None or self.header.own_kod else koddecoder.new()
        self.source = RecordSource(
            self.name,
            self.readdata,
            self.datsize,
            self.blocksize,
            self.use64bit,
            self.kod if self.encoding & 1 else None,
        )

    def close(self) -> None:
        """
        Close the .dat and .tad files.
        """
        self.dat.close()
        self.tad.close()

    def readdathdr(self) -> None:
        """
        Read the .dat file header.
        Note that the 19 byte header if followed by 0xE9 random bytes, generated by
        'srand(time())' followed by 0xE9 times obfuscate(rand())
        """
        header = read_dat_header(self.dat, where=f"Cro{self.name}.dat")
        layout = tad_layout(header.version)
        if layout is None:
            raise ValueError(
                f"Cro{self.name}.dat is CronosPro version {header.version_text}, whose .tad index this release "
                "cannot read"
            )
        self.header = header
        self.layout = layout
        self.hdrunk = header.unknown
        self.version = header.version
        self.encoding = header.encoding
        self.blocksize = header.blocksize
        self.use64bit = header.use64bit

        # blocksize
        #   0040 -> Bank
        #   0400 -> Index or Sys
        #   0200 -> Stru  or Sys

        # encoding
        #   bit0 = 'KOD encoded'
        #   bit1 = compressed

    def readtad(self) -> None:
        """
        read and decode the .tad file.
        """
        self.tad.seek(0)
        header_size = self.layout.header.size
        hdrdata = self.tad.read(header_size)
        if len(hdrdata) < header_size:
            raise ValueError(f"Cro{self.name}.tad is shorter than its {header_size}-byte header")
        self.nrdeleted, self.firstdeleted = self.layout.deleted_counts(hdrdata)

        self.tadhdrlen = self.tad.tell()
        self.tadentrysize = self.layout.entry.size
        self.idxdata = b""
        if self.compact:
            self.tad.seek(0, io.SEEK_END)
        else:
            self.idxdata = self.tad.read()
        self.tadsize = self.tad.tell() - self.tadhdrlen
        self.nrofrecords = self.tadsize // self.tadentrysize
        if self.tadsize % self.tadentrysize:
            self.warn("WARN: leftover data in .tad")

    def entry(self, index: int) -> TadEntry:
        """
        The .tad entry of the record at `index`, counted from 0. With `compact`, it is read from the .tad file
        instead of the cached copy.
        """
        if self.compact:
            self.tad.seek(self.tadhdrlen + index * self.tadentrysize)
            raw = self.tad.read(self.tadentrysize)
        else:
            start = index * self.tadentrysize
            raw = self.idxdata[start : start + self.tadentrysize]
        return self.layout.parse(raw)

    def readdata(self, ofs: int, size: int) -> bytes:
        """
        Read raw data from the .dat file
        """
        self.dat.seek(ofs)
        return self.dat.read(size)

    def read_record(self, recno: int) -> RecordParts | None:
        """
        Record `recno`, counted from 1, decoded and decompressed, or None when it is deleted.
        Raises ValueError, naming the record and the file, when it is not in the file or cannot be decoded.
        """
        if not 1 <= recno <= self.nrofrecords:
            raise ValueError(
                f"Cro{self.name}.dat has no record {recno}; its records are numbered 1 to {self.nrofrecords}"
            )
        entry = self.entry(recno - 1)
        if entry.deleted:
            return None
        return decode_record(self.source, recno, entry)

    def readrec(self, recno: int) -> bytes | None:
        """
        Extract and decode a single record, or None when it is deleted.
        Compressed data whose CRC-32 does not match is kept and reported through `warn`.
        Raises ValueError when the record is not in the file or cannot be decoded.
        """
        parts = self.read_record(recno)
        if parts is None:
            return None
        if parts.mismatched_chunks:
            self.warn(
                f"WARN: record {recno} in Cro{self.name}.dat has compressed data whose checksum does not match; "
                "it is kept"
            )
        return parts.data

    def enumunreferenced(self, ranges: list[tuple[int, int, str]], filesize: int) -> Iterator[tuple[int, int]]:
        """
        From a list of used byte ranges and the filesize, enumerate the list of unused byte ranges
        """
        o = 0
        for start, end, _desc in sorted(ranges):
            if start > o:
                yield o, start - o
            o = end
        if o < filesize:
            yield o, filesize - o

    def dump(self, args: argparse.Namespace) -> None:
        """
        Dump decodes all data referenced from the .tad file.
        And optionally print out all unreferenced byte ranges in the .dat file.

        This function is mostly useful for reverse-engineering the database format.

        the `args` object controls how data is decoded.
        """
        print(
            f"hdr: {self.name:<6} dat: {self.hdrunk:04x} {self.version} "
            f"enc:{self.encoding:04x} bs:{self.blocksize:04x}, "
            f"tad: {self.nrdeleted:08x} {self.firstdeleted:08x}"
        )

        ranges: list[tuple[int, int, str]] = []  # keep track of used bytes in the .dat file.

        for i in range(self.nrofrecords):
            entry = self.entry(i)
            idx = i + 1
            if args.maxrecs and i == args.maxrecs:
                break
            if entry.deleted:
                print(f"{idx:5d}: {entry.offset:08x} {entry.length:08x} {entry.checksum:08x}")
                continue

            ofs, ln, flags, chk = entry.offset, entry.length, entry.flags, entry.checksum
            ranges.append((ofs, ofs + ln, f"item #{i:d}"))
            decflags = [" ", " "]
            infostr = ""

            try:
                parts = read_stored(self.source, idx, entry, require_whole=False)
            except ValueError as e:
                print(f"{idx:5d}: {ofs:08x}-{ofs + ln:08x}: ({flags:02x}:{chk:08x}) <{e}>")
                continue
            if parts.extended:
                infostr = ";".join(f"{value:08x}" for value in [parts.chain[0], parts.length, *parts.chain[1:]])
                for blockofs in parts.chain[:-1]:
                    ranges.append((blockofs, blockofs + self.blocksize, f"item #{i:d} ext"))
                decflags[0] = "+"
            elif parts.data:
                decflags[0] = "*"

            if not self.encoding & 1:
                decflags[0] = " "

            data = parts.data
            if args.decompress and is_compressed(data):
                try:
                    data, _ = decompress(data, f"record {idx} in Cro{self.name}.dat")
                except ValueError as e:
                    print(f"{idx:5d}: {ofs:08x}-{ofs + ln:08x}: ({flags:02x}:{chk:08x}) <{e}>")
                    continue
                decflags[1] = "@"

            # TODO: separate handling for v4
            print(
                f"{i + 1:5d}: {ofs:08x}-{ofs + ln:08x}: ({flags:02x}:{chk:08x}) "
                f"{infostr} {''.join(decflags)}{toout(args, data)} {tohex(parts.tail)}"
            )

        if args.verbose:
            # output parts not referenced in the .tad file.
            for o, length in self.enumunreferenced(ranges, self.datsize):
                dat = self.readdata(o, length)
                print(f"{o:08x}-{o + length:08x}: {toout(args, dat)}")
```

Check this against today's `dump` line by line before replacing it: today's decflags start as `[" ", " "]`; `"+"`
for an extended record, `"*"` for a non-empty inline one, and `" "` again when encoding bit 0 is clear; `"@"` when
decompressed. `read_stored` with `require_whole=False` KOD-decodes exactly when today's dump does (encoding bit 0
set and a KOD present). If anything differs, follow today's code and report it.

In `src/cronos_extract/_api/datafiles.py`, delete `TAD_HEADER_SIZES` and write:

```python
        layout = tad_layout(header.version)
        if layout is None:
            raise UnsupportedVersion(
                f"{datname} in {directory} is CronosPro version {header.version_text} ({header.generation}), "
                "which this release cannot read"
            )
        if os.fstat(tad.fileno()).st_size < layout.header.size:
            raise NotACronosFile(f"{tadname} in {directory} is shorter than its {layout.header.size}-byte header")
```

importing `tad_layout` from `.._format.tad`.

- [ ] **Step 4: Run the tests** — `uv run pytest -q tests/test_datafile.py tests/test_cli_characterisation.py
  tests/test_cli_inspect.py`, then the full suite: all pass, `git diff master -- tests/golden` empty.
- [ ] **Step 5: Commit** — `git add src/cronos_extract/Datafile.py src/cronos_extract/_api/datafiles.py
  tests/test_datafile.py`; subject "Read Datafile records through the tad and record modules"; the body names A1, A2
  and A5 and the removed methods; the two trailer lines.

---

### Task 6: `checksum_mismatch` in the API

**Files:**
- Modify: `src/cronos_extract/_api/diagnostics.py`, `src/cronos_extract/_api/bank.py`
- Test: `tests/test_api_bank.py`, `tests/test_cli_export.py`

**Interfaces:**
- Consumes: Task 5's `Datafile.read_record`; Task 2's `compressed_record(..., wrong_checksums=...)`.
- Produces: `DiagnosticKind.CHECKSUM_MISMATCH = "checksum_mismatch"`, declared right after `CORRUPT_RECORD`;
  `Bank._read` records it once per record, message
  `f"CroBank record {n} has {k} compressed chunk{'s' if k != 1 else ''} whose checksum does not match; the record is kept as it decompressed"`,
  `file="CroBank.dat"`, `record=n`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_api_bank.py` (use its existing `person()` helper and imports; add `compressed_record` and
`DiagnosticKind`):

```python
def test_a_checksum_mismatch_keeps_the_record_and_is_reported_once(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [compressed_record(person(), wrong_checksums={0})])

    with cronos_extract.open(dbdir) as bank:
        first = list(bank.tables[0].records())
        second = list(bank.tables[0].records())
        counts = bank.diagnostic_counts[DiagnosticKind.CHECKSUM_MISMATCH]
        diagnostics = [d for d in bank.diagnostics if d.kind == DiagnosticKind.CHECKSUM_MISMATCH]

    assert len(first) == len(second) == 1
    assert counts == 1
    assert diagnostics[0].record == 1
    assert diagnostics[0].file == "CroBank.dat"
    assert diagnostics[0].message == (
        "CroBank record 1 has 1 compressed chunk whose checksum does not match; the record is kept as it decompressed"
    )
```

Append to `tests/test_cli_export.py` (it already imports `run_command`, `write_database`, `table_record`):

```python
def test_a_checksum_mismatch_is_on_stderr_in_the_stream_and_fails_strict(tmp_path: Path) -> None:
    dbdir = write_database(tmp_path / "db", [compressed_record(table_record({0: b"x"}), wrong_checksums={0})])

    result = run_command("cli", ["export", "--jsonl", "--strict", dbdir])

    assert result.returncode == 1
    assert "warning: checksum_mismatch: CroBank.dat record 1: " in result.stderr
    assert "1 checksum_mismatch" in result.stderr.splitlines()[-1]
    assert '"kind": "checksum_mismatch"' in result.stdout
    assert '"record": 1' in result.stdout
```

- [ ] **Step 2: Run them to see them fail** — `AttributeError: CHECKSUM_MISMATCH`.

- [ ] **Step 3: Implement**

In `diagnostics.py`, add `CHECKSUM_MISMATCH = "checksum_mismatch"` after `CORRUPT_RECORD`. In `bank.py`: add
`self._checksum_mismatches = RecordNumbers(database.bank.nrofrecords)` in `Bank.__init__`, import `RecordParts`
from `.._format.record`, and make `_read`:

```python
        try:
            parts = cast(RecordParts | None, self._database.bank.read_record(number))
        except OSError:
            raise
        except Exception as e:
            ... (unchanged corrupt_record handling, returning None)
        if parts is None:
            return None
        mismatched = len(parts.mismatched_chunks)
        if mismatched and self._checksum_mismatches.add(number):
            chunks = "chunk" if mismatched == 1 else "chunks"
            self._log.record(
                Diagnostic(
                    DiagnosticKind.CHECKSUM_MISMATCH,
                    f"CroBank record {number} has {mismatched} compressed {chunks} whose checksum does not match; "
                    "the record is kept as it decompressed",
                    file=BANK_FILE,
                    record=number,
                )
            )
        return parts.data
```

Update `_read`'s docstring: a record whose compressed data fails its CRC is returned and reported as
`checksum_mismatch` the first time only.

- [ ] **Step 4: Run the tests** — the two new tests and the full suite pass; `tests/test_cli_report.py`'s summary
  order test still passes (the new kind sits in declaration order).
- [ ] **Step 5: Commit** — subject "Report compressed records whose checksum does not match"; the two trailer lines.

---

### Task 7: `inspect crodump` marks a checksum mismatch

**Files:**
- Modify: `src/cronos_extract/Datafile.py` (`dump`)
- Test: `tests/test_cli_inspect.py`

- [ ] **Step 1: Write the failing test**

```python
def test_inspect_crodump_marks_a_record_whose_checksum_does_not_match(tmp_path: Path) -> None:
    fields = [b""] * TEST_TABLE_FIELD_COUNT
    fields[0] = b"good"
    dbdir = write_database(
        tmp_path / "db",
        [compressed_record(bank_record(TEST_TABLE_ID, fields)), compressed_record(b"bad", wrong_checksums={0})],
    )

    result = run_command("cli", ["inspect", "crodump", dbdir])

    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    bank_start = next(i for i, line in enumerate(lines) if line.startswith("hdr: Bank"))
    first, second = [line for line in lines[bank_start + 1 :] if line.startswith(("    1:", "    2:"))]
    assert not first.endswith("<checksum mismatch>")
    assert second.endswith(" <checksum mismatch>")
```

- [ ] **Step 2: Run it to see it fail** — the second line lacks the marker.
- [ ] **Step 3: Implement** — in `dump`, keep the mismatched chunks from `decompress` and append ` <checksum
  mismatch>` to the printed line when there are any:

```python
            mismatch = ""
            if args.decompress and is_compressed(data):
                try:
                    data, mismatched = decompress(data, f"record {idx} in Cro{self.name}.dat")
                except ValueError as e:
                    ...
                decflags[1] = "@"
                if mismatched:
                    mismatch = " <checksum mismatch>"
            ...
                f"{infostr} {''.join(decflags)}{toout(args, data)} {tohex(parts.tail)}{mismatch}"
```

- [ ] **Step 4: Run the tests** — the new test, `tests/test_cli_characterisation.py` and the full suite pass;
  golden diff empty.
- [ ] **Step 5: Commit** — subject "Mark a checksum mismatch in inspect crodump"; the two trailer lines.

---

### Task 8: The seeded random-damage test

**Files:**
- Create: `tests/test_damage.py`

- [ ] **Step 1: Write the test**

```python
# ABOUTME: A seeded random-damage test of the reading path: a damaged database must never crash, hang or print.
# ABOUTME: Each case builds a database, damages one of its files from a fixed seed, and reads everything.
import random
import signal
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import FrameType

import pytest
from cronos_builder import (
    BUILDER_VERSIONS,
    TEST_TABLE_FIELD_COUNT,
    TEST_TABLE_ID,
    bank_record,
    compressed_record,
    file_record,
    write_database,
)

import cronos_extract

SEED = 20260925
CASES_PER_VERSION = 40
TIME_LIMIT_SECONDS = 10


class TooSlow(BaseException):
    """Raised by the time limit; a BaseException, so that no reader's broad `except Exception` can swallow it."""


@contextmanager
def time_limit(seconds: int) -> Iterator[None]:
    """Raise TooSlow in the code inside the block when it runs for more than `seconds`."""

    def stop(signum: int, frame: FrameType | None) -> None:
        raise TooSlow(f"reading took more than {seconds} s")

    previous = signal.signal(signal.SIGALRM, stop)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def database_records(rng: random.Random) -> list[bytes | None]:
    """A few records of the test table, some compressed, and a stored file or two."""
    records: list[bytes | None] = []
    for number in range(rng.randint(1, 12)):
        fields = [b""] * TEST_TABLE_FIELD_COUNT
        fields[0] = str(number).encode()
        fields[3] = b"1240315"
        record = bank_record(TEST_TABLE_ID, fields)
        choice = rng.random()
        if choice < 0.3:
            record = compressed_record(record)
        elif choice < 0.4:
            record = file_record(rng.randbytes(rng.randint(0, 40)))
        records.append(record)
    return records


def damage(rng: random.Random, dbdir: Path) -> str:
    """Damage one Cro file of `dbdir` by flipping bits, truncating it or overwriting bytes; say what was done."""
    path = rng.choice(sorted(dbdir.iterdir()))
    data = bytearray(path.read_bytes())
    kind = rng.choice(["flip", "truncate", "overwrite"])
    if kind == "flip":
        for _ in range(rng.randint(1, 8)):
            data[rng.randrange(len(data))] ^= 1 << rng.randrange(8)
    elif kind == "truncate":
        del data[rng.randrange(len(data)) :]
    else:
        start = rng.randrange(len(data))
        count = rng.randint(1, 64)
        data[start : start + count] = rng.randbytes(count)
    path.write_bytes(bytes(data))
    return f"{kind} {path.name}"


CASES = [(version, index) for version in BUILDER_VERSIONS for index in range(CASES_PER_VERSION)]


@pytest.mark.skipif(not hasattr(signal, "SIGALRM"), reason="the time limit needs SIGALRM")
@pytest.mark.parametrize(("version", "index"), CASES, ids=[f"{v.decode()}-{i:03d}" for v, i in CASES])
def test_a_damaged_database_is_read_without_crashing_hanging_or_printing(
    tmp_path: Path, capfd: pytest.CaptureFixture[str], version: bytes, index: int
) -> None:
    rng = random.Random(f"{SEED}:{version.decode()}:{index}")
    dbdir = Path(write_database(tmp_path / "db", database_records(rng), version=version))
    what = damage(rng, dbdir)

    with time_limit(TIME_LIMIT_SECONDS):
        try:
            with cronos_extract.open(dbdir) as bank:
                for table in bank.tables:
                    for _ in table.records():
                        pass
                for _ in bank.files():
                    pass
        except cronos_extract.CronosError:
            pass

    assert capfd.readouterr() == ("", ""), what
```

- [ ] **Step 2: Run it** — `uv run pytest -q tests/test_damage.py`. Expected: 200 passed in a few seconds. A failure
  is a bug in the reader (its id is `<version>-<index>`, and `what` says which file and how it was damaged): fix the
  reader with its own test in the right test file, not the damage test, and report it.
- [ ] **Step 3: Check that the test catches something** — temporarily change `_format/record.py`'s
  `decompress` to raise `struct.error` in place of the "cut off" `ValueError` (copy the file aside first, restore it
  by copying back; never `git checkout`), run `uv run pytest -q tests/test_damage.py`, and record in the report
  whether any case fails. Restore the file and confirm `git diff` shows no change to it.
- [ ] **Step 4: Run every check and commit** — subject "Add a seeded random-damage test of the reading path"; the two
  trailer lines.

---

### Task 9: No real database reports a checksum mismatch

**Files:**
- Modify: `tests/test_realdata.py`

- [ ] **Step 1: Add the test**

```python
def test_no_real_database_reports_a_checksum_mismatch(dbdir: Path) -> None:
    if not bank_is_small(dbdir):
        pytest.skip("CroBank is too large to walk once per table")
    with open_or_skip(dbdir) as bank:
        for table in bank.tables:
            for _ in itertools.islice(table.records(), RECORDS_COMPARED):
                pass
        list(itertools.islice(bank.files(), RECORDS_COMPARED))
        assert bank.diagnostic_counts[cronos_extract.DiagnosticKind.CHECKSUM_MISMATCH] == 0
```

- [ ] **Step 2: Run it over the real databases** — `uv run pytest -q -m realdata tests/test_realdata.py -k
  "checksum or open_reads or field_text" -rs > /tmp/t9-realdata.txt 2>&1`, in the background, reading the output file
  until it ends. Report counts only (passed, skipped, failed). A failure means a real database fails its CRC or the
  reader changed what it returns: stop and report the test id and the kind of failure.
- [ ] **Step 3: Run every check and commit** — subject "Check that no real database reports a checksum mismatch";
  the two trailer lines.

---

### Task 10: Documentation

**Files:**
- Modify: `README.md`, `CLAUDE.md`, `docs/cronos-research.md`,
  `docs/superpowers/specs/2026-09-15-modernisation-roadmap-design.md`

- [ ] **Step 1: Write the changes**

- `README.md`, in the Exporting section after the paragraph on diagnostics: "A compressed record whose CRC-32 does
  not match its data is kept and reported as `checksum_mismatch`; a record that would decompress to more than 256 MiB
  is skipped and reported as `corrupt_record`."
- `CLAUDE.md`, the `Datafile` bullet: state that a `.tad` entry is parsed by `_format/tad.py`'s layout for its
  generation (v3: the inline flag is bit 31 of the length; v4: the flags are the top byte of the offset), that every
  record is decoded by `_format/record.py`'s `decode_record` (extension blocks, KOD, then CRC-checked decompression,
  at most 256 MiB), and that `read_record` returns the parts with the mismatched chunks.
- `docs/cronos-research.md`: under the compressed record description, the CRC evidence (11,885 chunks, all
  `zlib.crc32` of the decompressed chunk); under the v3 `.tad` layout, the flag evidence (top byte `0x00` or `0x80`
  only, over 12.1 million live entries in 70 files).
- The roadmap's "Public API contract" `Diagnostic` bullet: add `checksum_mismatch` to the list of kinds.

- [ ] **Step 2: Check** — `uv run ruff format --check README.md CLAUDE.md docs`; `uv run pytest -q`.
- [ ] **Step 3: Commit** — subject "Document CRC checking and the Datafile modules"; the two trailer lines.

---

### Task 11: The outcome and the roadmap's open items

- [ ] **Step 1:** Add an "Outcome" section at the end of this plan: the commits (hash and subject), the test count on
  `master` and on the branch, the damage test's result and the mutation check of Task 8, the realdata result as counts
  only, and every place the code turned out different from this plan and what was done.
- [ ] **Step 2:** In the roadmap: the status line says Phase 3a is implemented on `phase3a-datafile-core`, pull request
  pending; in "Open items carried forward", mark done the Phase 3 items this phase closes (the duplicate version lists
  in `Datafile`, `decompress` not limiting the size, the v3 `.tad` flag overlap, the random-damage test and the builder
  gaps) and add the spec's two open items (3d: v4 flags `02` and `03` and the third `.tad` field; 3b: a CroStru
  checksum mismatch reaches the API as `unexpected_structure` through `warn` until 3b turns warnings into diagnostics).
- [ ] **Step 3:** `uv run ruff format --check` and `uv run pytest -q`; commit with subject "Record the Phase 3a outcome
  and carry its open items forward" and the two trailer lines.

---

## Outcome

### Commits

```
0a6f364 Design Phase 3a: the Datafile core
a989bbb Plan Phase 3a: the Datafile core
74ceb0a Build compressed records with real CRCs and KOD-encoded v3 files
0cf7dde Migrate INLINE_RECORD_FLAGS use sites to V3_INLINE_BIT
e59d6ee Add the .tad layout of each CronosPro generation
3e19d02 Decode records through one pipeline with CRC checks and a size limit
ec78a18 Skip read_stored's length check for every kind of cut-short record
fa66b36 Read Datafile records through the tad and record modules
e177618 Fix Task 5 review findings in Datafile and record decoding
3c7ff13 Report compressed records whose checksum does not match
35a7449 Mark a checksum mismatch in inspect crodump
969a2bf Add a seeded random-damage test of the reading path
905c046 Give the builder an extended-record option
a068b6e Damage extended and KOD-encoded records too
5b87644 Check that no real database reports a checksum mismatch
df01bf8 Document CRC checking and the Datafile modules
```

### Test counts

`uv run pytest -q` on `master` (worktree at `58aec82`): 575 passed, 9 deselected. On this branch, after Task 10:
834 passed, 10 deselected.

### The damage test and Task 8's mutation check

`tests/test_damage.py` runs 200 seeded cases, each building a database, flipping/truncating/overwriting random
bytes of one `.dat` or `.tad` file, and opening it: 200 passed, no reader bug found (no hang, no unhandled
exception, no stdout/stderr output).

The plan's mutation check (`decompress` raising `struct.error` for a cut-off chunk header) turned out to be
vacuous: `Bank._read` catches any `Exception` as `corrupt_record`, so a `struct.error` there is swallowed exactly
like the `ValueError` it replaces, and no damage case could ever fail from it. The controller's substitute check
removed `read_extended`'s extension-block loop guard and its `extlen > source.size` guard instead: still 0/200
failed, both rounds. The first removal alone proved nothing, since a looping chain without the guard still
terminates within `source.size` iterations rather than hanging; instrumenting the guard's `raise` showed it was
never reached by the original (inline-only, unencoded) corpus at all. The corpus was then extended (extended
records and KOD encoding, default and own tables) and the check repeated: `read_extended` ran in every one of the
200 cases (863 calls total), and still 0/200 failed — not because the removed guards are unreachable, but because
an already-in-place third guard (a read running past the end of the file) catches the paths this style of random
damage produces before either removed guard would.

### Realdata

`uv run pytest -q -m realdata tests/test_realdata.py -k "checksum or open_reads or field_text" -rs`: 62 passed, 28
skipped, 0 failed. No real database reported a checksum mismatch or a change in field text.

### Where the code turned out different from this plan

- **Task 2:** the brief said to replace `INLINE_RECORD_FLAGS` with `V3_INLINE_BIT` and delete the former, but three
  test files outside the task's file list also constructed the bit from `INLINE_RECORD_FLAGS`. The task kept both
  constants and flagged the duplication; the controller then ruled to migrate those three files and delete
  `INLINE_RECORD_FLAGS`, done as a follow-up commit in the same task.
- **Task 4:** the brief's `read_stored(require_whole=False)` skipped its length check only for inline records; a
  truncated extended record would then raise instead of being reassembled as far as it goes, changing `inspect`
  output the plan requires to stay byte for byte the same. The controller ruled to skip the length check for every
  record when `require_whole` is false, matching what `Datafile.dump` already did.
- **Task 5:** the plan's Review Focus 3 and Task 4's `test_a_chunk_whose_header_is_cut_off_is_a_value_error`
  expected a cut-off compressed-chunk header to raise `ValueError`. The controller ruled instead to keep the
  record's data as far as it was decoded and count the chunk as a `checksum_mismatch`, since today's code decodes
  such a record as far as its data goes and turning that into a raised error would be new data loss the plan's own
  principle (A3, keep data on a mismatch) argues against.
- **Task 5:** outside the brief's file list, three more changes were made because other rules required them:
  `_format/header.py` gained two comment lines above `V4_VERSIONS`/`V7_VERSIONS` carrying over notes from the
  deleted `Datafile.isv4`/`isv7` (the "never delete a comment unless false" rule); `_api/crack.py`'s
  `readable_records` dropped a `cast(bytes | None, ...)` around `datafile.readrec(...)` that `ty check` now flags
  as `redundant-cast`, since `readrec` is fully annotated; and one `pytest.raises(match=...)` pattern in
  `tests/test_datafile.py` had its literal `.` escaped to `\.` for ruff's `RUF043`.
- **Task 6:** `tests/test_api_diagnostics.py` pins the full ordered list of `DiagnosticKind` values; adding
  `CHECKSUM_MISMATCH` to the enum, as the brief specified, failed that test until `"checksum_mismatch"` was added
  to the pinned list too. Not in the brief's file list; required by the rule against leaving a test failing.
- **Task 8:** the plan's damage corpus wrote only inline, unencoded records, which never reached extended-record
  reassembly or KOD decoding. The controller ruled to give the builder an `extended=` option and vary KOD encoding
  (none, default table, own table) per case, so the corpus reaches the code the damage test exists to protect.

### Deferred minors (not carried into the roadmap as open items)

- `decompress` does not check a chunk's compression flag itself; callers rely on `is_compressed` first, as today.
- `tests/test_cli_export.py`'s docstring still names `iscompressed()`, now `record.is_compressed`.
- The cut-off-chunk behaviour change and the A2 flag reading, as they appear in `inspect crodump` output, are not
  covered by any golden input (for the pull request description).
- The damage corpus has no CroIndex file and no directly written deleted records.
- The damage corpus reaches `read_extended` in every case, but its loop and length guards stay unreachable by
  random byte damage, since the EOF guard already in place catches first; `tests/test_record.py` covers both
  guards directly instead.

### Final review

Recorded after the whole-branch review.
