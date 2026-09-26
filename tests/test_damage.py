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
    OWN_KOD_VERSIONS,
    TEST_TABLE_FIELD_COUNT,
    TEST_TABLE_ID,
    bank_record,
    compressed_record,
    file_record,
    random_kod,
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


def choose_layout(rng: random.Random, version: bytes) -> tuple[bool, list[int] | None, bool, str]:
    """Pick whether this case writes extended records and how it KOD-encodes them; return the values `write_database`
    needs (extended, its own KOD table or None, whether to KOD-encode with the default table), plus a description
    for `what`.

    For a version with its own KOD table, this sometimes picks a random one of those instead of the default table.
    """
    extended = rng.random() < 0.5
    if version in OWN_KOD_VERSIONS and rng.random() < 0.5:
        table = random_kod(rng.randrange(1_000_000))
        return extended, table, False, f"extended={extended} kod=own"
    encoded = rng.random() < 0.5
    return extended, None, encoded, f"extended={extended} kod={'default' if encoded else 'none'}"


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
    extended, own_kod, encoded, layout = choose_layout(rng, version)
    dbdir = Path(
        write_database(
            tmp_path / "db", database_records(rng), own_kod, version=version, encoded=encoded, extended=extended
        )
    )
    what = f"{damage(rng, dbdir)} ({layout})"
    open_kwargs = {"kod": cronos_extract.Kod.from_table(own_kod)} if own_kod is not None else {}

    with time_limit(TIME_LIMIT_SECONDS):
        try:
            with cronos_extract.open(dbdir, **open_kwargs) as bank:
                for table in bank.tables:
                    for _ in table.records():
                        pass
                for _ in bank.files():
                    pass
        except cronos_extract.CronosError:
            pass

    assert capfd.readouterr() == ("", ""), what
