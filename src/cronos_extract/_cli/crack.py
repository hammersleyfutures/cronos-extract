# ABOUTME: The crack subcommands: strucrack and dbcrack recover a database's KOD table from its encrypted records.
# ABOUTME: stdout holds the dump and the KOD; messages go to stderr. Each opens only the files its method reads.
import argparse
import sys
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager

from .. import koddecoder
from .._api.crack import (
    bank_and_index_xref,
    fill_single_gap,
    kod_from_xref,
    kod_is_resolved,
    readable_records,
    stru_xref,
)
from .._api.datafiles import database_directory, list_directory, open_datafile
from .._api.diagnostics import Diagnostic, DiagnosticLog
from ..Datafile import Datafile
from ..hexdump import as1251, asambigoushex, asasc, tohex, unhex
from ..koddecoder import match_with_mismatches
from .options import Subcommands
from .report import Report

KEY_MESSAGE = "Pass the following database key to cronos-extract export --kod or inspect --kod to decrypt the database:"


def color_code(c: str, confidence: int, forced: bool, force: bool) -> str:
    from sys import stdout

    is_a_tty = hasattr(stdout, "isatty") and stdout.isatty()
    if not force and not is_a_tty:
        return c

    if forced:
        return "\033[32m" + c + "\033[0m"
    if confidence < 0:
        return "\033[96m" + c + "\033[0m"
    if confidence == 0:
        return "\033[31m" + c + "\033[0m"
    if confidence > 3:
        return "\033[93m" + c + "\033[0m"
    return "\033[94m" + c + "\033[0m"


FIX_FORMAT = "use xxyy=C or xxyycc, with the encrypted byte xx, the shift yy and the plaintext C or cc"


def parse_fix(value: str) -> tuple[int, int, int]:
    """
    Parse a strucrack --fix switch into (encrypted byte, shift, plaintext byte).

    Raises argparse.ArgumentTypeError with the reason when the switch can't be parsed.
    """
    try:
        if len(value) != 6:
            raise ValueError(f"expected 6 characters, got {len(value):d}")
        if value[4] == "=":
            i, o = unhex(value[0:4])
            (c,) = as1251(value[5:])
        else:
            i, o, c = unhex(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"invalid fix {value!r}: {e}; {FIX_FORMAT}") from e
    return int(i), int(o), int(c)


def positive_int(value: str) -> int:
    """
    Parse a command line option that must be a positive whole number.

    Raises argparse.ArgumentTypeError when `value` is not one.
    """
    try:
        number = int(value)
    except ValueError:
        number = 0
    if number <= 0:
        raise argparse.ArgumentTypeError(f"{value!r} must be a positive number")
    return number


TEXT_FORMAT = "use record:line:offset:plaintext, with the record, line and offset that the strucrack dump shows"


def parse_text(value: str) -> tuple[int, int, bytes]:
    """
    Parse a strucrack --text value into (record number, offset in the record, CP-1251 plaintext bytes).

    Raises argparse.ArgumentTypeError with the reason when the value can't be parsed.
    """
    parts = value.split(":", 3)
    try:
        if len(parts) != 4:
            raise ValueError("expected four parts separated by ':'")
        record, line, offset = [int(part) for part in parts[:3]]
        if min(record, line, offset) < 0:
            raise ValueError("record, line and offset can't be negative")
        plaintext = as1251(parts[3])
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"invalid text {value!r}: {e}; {TEXT_FORMAT}") from e
    return record, line + offset, bytes(plaintext)


class CrackInputError(Exception):
    """
    A strucrack option that doesn't fit the database being cracked.
    """


def add_parser(subcommands: Subcommands) -> None:
    """Add the crack subcommand and its two methods to `subcommands`."""
    crack_parser = subcommands.add_parser(
        "crack", help="recover the KOD table of a database encrypted with its own, without its password"
    )
    methods = crack_parser.add_subparsers(dest="crack_method", required=True, metavar="METHOD")

    p = methods.add_parser(
        "strucrack",
        help="recover the KOD from CroStru, showing the records so that unresolved entries can be fixed by hand",
    )
    p.add_argument("--sys", action="store_true", help="Use CroSys for cracking")
    p.add_argument("--silent", action="store_true", help="print only the KOD, without the dump or messages")
    p.add_argument("--noninteractive", action="store_true", help="Stop if automatic cracking fails")
    p.add_argument("--color", action="store_true", help="force color output even on non-ttys")
    p.add_argument(
        "--fix", "-f", action="append", dest="fix", type=parse_fix, help="force KOD entries after identification"
    )
    p.add_argument(
        "--text",
        "-t",
        action="append",
        dest="text",
        type=parse_text,
        help="add fixed bytes to decoder box by providing whole strings for a position in a record, "
        "format is record:line:offset:plaintext",
    )
    p.add_argument("--width", "-w", type=positive_int, help="max number of decoded characters on screen", default=24)
    p.add_argument("dbdir", type=str)
    p.set_defaults(handler=run_strucrack, command_parser=p)

    p = methods.add_parser("dbcrack", help="recover the KOD from the fourth byte of CroBank and CroIndex records")
    p.add_argument("--silent", action="store_true", help="print only the KOD, without messages")
    p.add_argument("dbdir", type=str)
    p.set_defaults(handler=run_dbcrack, command_parser=p)


@contextmanager
def raw_datafile(dbdir: str, base: str) -> Iterator[Datafile]:
    """
    Cro<base> in `dbdir`, opened without KOD decoding and reading its index from disk, with its warnings on stderr.

    The crack reads some records more than once, so each diagnostic is printed only the first time it is reported.
    Raises NotACronosFile or UnsupportedVersion when it cannot be read, and OSError when `dbdir` cannot be listed.
    """
    directory = database_directory(dbdir)
    report = Report()
    reported: set[Diagnostic] = set()

    def report_once(diagnostic: Diagnostic) -> None:
        if diagnostic not in reported:
            reported.add(diagnostic)
            report.diagnostic(diagnostic)

    log = DiagnosticLog(report_once)
    datafile, _ = open_datafile(directory, list_directory(directory), base, compact=True, kod=None, log=log)
    try:
        yield datafile
    finally:
        datafile.close()


def run_strucrack(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Recover the KOD from CroStru, or CroSys with --sys. A --noninteractive crack that fails exits 1."""
    with raw_datafile(args.dbdir, "Sys" if args.sys else "Stru") as table:
        kod = derive_kod_from_stru(table, args)
    return 1 if kod is None and args.noninteractive else 0


def run_dbcrack(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Recover the KOD from CroBank and CroIndex, exiting 1 when it cannot."""
    with ExitStack() as stack:
        bank = stack.enter_context(raw_datafile(args.dbdir, "Bank"))
        index = stack.enter_context(raw_datafile(args.dbdir, "Index"))
        kod = derive_kod_from_bank_and_index(bank, index, args)
    return 0 if kod is not None else 1


def print_unresolved(kod: list[int], confidence: list[int], unset_count: int) -> None:
    """
    Print on stderr which KOD entries are unresolved, the KOD estimate and how to fix entries by hand.

    It is printed without colour: the stderr escaping would show colour codes as text.
    """
    kod_set = {value for entry, value in enumerate(kod) if confidence[entry] > 0}
    unset_entries = ", ".join(f"{entry:02x}" for entry in range(256) if confidence[entry] <= 0)
    unused_values = ", ".join(f"{value:02x}" for value in sorted(set(range(256)).difference(kod_set)))
    lines = [
        f"\nAmbiguous result when cracking. {unset_count:d} entries unsolved. Missing mappings:",
        f"[{unset_entries}] => [{unused_values}]\n",
    ]
    if unset_count == 0:
        lines.append("The forced KOD entries map several entries to the same value, see the duplicates above.\n")
    lines += [
        "KOD estimate:",
        "".join(f"{value:02x}" if confidence[entry] > 0 else "??" for entry, value in enumerate(kod)),
        "\nIf you can provide clues for unresolved KOD entries by looking at the output, pass them via",
        "cronos-extract crack strucrack -f f103=B  -f f10342",
    ]
    print("\n".join(lines), file=sys.stderr)


def derive_kod_from_stru(table: Datafile, args: argparse.Namespace) -> list[int] | None:
    """
    Derive the KOD table from the encrypted records of `table`, CroStru or CroSys, as strucrack's help describes.
    Prints the record dump for finding known text in it, and the KOD when it is resolved; --silent prints only the
    KOD. Returns None when entries stay unresolved. Raises CrackInputError for a --text that does not fit `table`.
    """
    xref = stru_xref(table)

    KOD, KOD_CONFIDENCE = kod_from_xref(xref)

    # Entries the user forced with --fix or --text keep their value when they duplicate another entry
    KOD_FORCED = [False] * 256
    for i, o, c in args.fix or []:
        KOD[i] = (c + o) % 256
        KOD_CONFIDENCE[i] = 255
        KOD_FORCED[i] = True

    # For chunks of text where record and offset is known, set the KOD
    for record, dataoff, text in args.text or []:
        if record >= table.nrofrecords:
            raise CrackInputError(
                f"--text: record {record:d} doesn't exist, the file has records 0 to {table.nrofrecords - 1:d}"
            )
        data = table.readrec(record + 1)
        if not data:
            raise CrackInputError(f"--text: record {record:d} is deleted or empty")
        if dataoff + len(text) > len(data):
            raise CrackInputError(
                f"--text: {len(text):d} bytes at offset {dataoff:d} runs past the end of record {record:d}, "
                f"which has {len(data):d} bytes"
            )
        o = record + 1 + dataoff
        for i, c in enumerate(text):
            d = data[dataoff + i]
            KOD[d] = (c + o + i) % 256
            KOD_CONFIDENCE[d] = 255
            KOD_FORCED[d] = True

    fill_single_gap(KOD, KOD_CONFIDENCE)

    # Show duplicates that may arise by the user forcing KOD entries from command line
    kod_set = [v for o, v in enumerate(KOD) if KOD_CONFIDENCE[o] > 0]
    duplicates = [(o, v) for o, v in enumerate(KOD) if kod_set.count(v) > 1 and KOD_CONFIDENCE[o] > 0]
    duplicates = sorted(duplicates, key=lambda x: x[1])

    for o, _v in duplicates:
        if not KOD_FORCED[o]:
            KOD_CONFIDENCE[o] = -1

    kod = koddecoder.new(KOD, KOD_CONFIDENCE)

    known_strings = [
        (b"USERINFO", 4, b"\x08USERINFO", -1),
        (b"Version", 4, b"\x07Version", -1),
        (b"\x08BankName", 5, b"\x08BankName", 0),
        (
            as1251("Системный номер"),
            6,
            b"\x00\x00\x00\x00\x00\x00\x0f" + as1251("Системный номер") + b"\x01\x00\x00\x00\x00",
            -7,
        ),
    ]

    # The KOD is resolved when every entry has a positive confidence and it is a permutation of 0..255,
    # because a KOD with duplicate values can't decode the database.
    unset_count = len([o for o in KOD_CONFIDENCE if o <= 0])
    is_resolved = kod_is_resolved(KOD, KOD_CONFIDENCE)
    if not is_resolved and args.noninteractive:
        if not args.silent:
            print(
                f"Automatic cracking failed: {unset_count:d} entries unsolved. "
                "Run cronos-extract crack strucrack without --noninteractive to resolve them.",
                file=sys.stderr,
            )
        return None

    force_color = args.color

    # Dump partially decoded stru records for the user to try to spot patterns
    w = args.width
    records = () if args.silent else readable_records(table)
    for recno, data in records:
        if not data:
            continue
        i = recno - 1

        print(f"Processing record number {i:d}")

        candidate, candidate_confidence = kod.try_decode(i + 1, data)

        for s, min_matching, deststring, destoffset in known_strings:
            incomplete_matches = match_with_mismatches(candidate, candidate_confidence, s, min_matching)
            for ofix in incomplete_matches:
                do = ofix[0]
                print(f"Found {asasc(candidate[do : do + len(s)])} which looks a lot like {asasc(s)} ")
                print("Add the following switches to your command line to fix the decoder box:\n    ", end="")
                for o, c in enumerate(deststring):
                    # the known string can reach before or past this record, where there is no byte to fix
                    pos = do + o + destoffset
                    if not 0 <= pos < len(data):
                        continue
                    print(f"-f {data[pos]:02x}{(pos + i + 1) % 256:02x}{c:02x} ", end="")
                print("\n")

        candidate_chunks = [candidate[j : j + w] for j in range(0, len(candidate), w)]
        for ofs, chunk in enumerate(candidate_chunks):
            confidence = candidate_confidence[ofs * w : ofs * w + w]
            text = asasc(chunk, confidence)
            hexed = asambigoushex(chunk, confidence)

            forced = [KOD_FORCED[b] for b in data[ofs * w : ofs * w + w]]

            colored = "".join(color_code(c, confidence[o], forced[o], force_color) for o, c in enumerate(text))
            colored_hexed = "".join(
                color_code(c, confidence[o >> 1], forced[o >> 1], force_color) for o, c in enumerate(hexed)
            )
            fix_helper = " ".join(
                f"{b:02x}{(w * ofs + i + 1 + o) % 256:02x}={color_code(text[o], confidence[o], forced[o], force_color)}"
                for o, b in enumerate(data[ofs * w : ofs * w + w])
            )

            # Can't use left padding in format string, because we have color escape codes,
            # so do manual padding
            padding = " " * (w - len(chunk))

            print(f"{w * ofs:05d} {colored + padding} : {colored_hexed + padding * 2} : {fix_helper}")
        print()

    if len(duplicates) and not args.silent:
        print(
            "\nDuplicates found:\n"
            + ", ".join(
                color_code(f"[{o:02x}=>{v:02x} ({KOD_CONFIDENCE[o]:d})]", KOD_CONFIDENCE[o], KOD_FORCED[o], force_color)
                for o, v in duplicates
            )
        )

    # If the KOD is not completely resolved, show the missing mappings. Entries with a duplicate value
    # count as unresolved.
    if not is_resolved:
        if not args.silent:
            print_unresolved(KOD, KOD_CONFIDENCE, unset_count)
        return None

    if not args.silent:
        print(KEY_MESSAGE, file=sys.stderr)
    print(tohex(bytes(KOD)))

    return KOD


def derive_kod_from_bank_and_index(bank: Datafile, index: Datafile, args: argparse.Namespace) -> list[int] | None:
    """
    Derive the KOD table from the encrypted CroBank and CroIndex records, as dbcrack's help describes.

    Most records of both are compressed and start with a uint16 size, 0x08 and 0x00, so the fourth byte of each
    decodes to zero, which gives the KOD entry for that byte at the record's shift. Prints the KOD when it is
    resolved; returns None, printing why on stderr unless --silent, when it is not.
    """
    KOD, KOD_CONFIDENCE = kod_from_xref(bank_and_index_xref(bank, index))

    # Rows that found no data, or lost their byte to another row, leave entries unresolved.
    unset_count = len([o for o in KOD_CONFIDENCE if o <= 0])
    if not kod_is_resolved(KOD, KOD_CONFIDENCE):
        if not args.silent:
            print(
                f"Ambiguous result when cracking. {unset_count:d} entries unsolved: too few CroBank/CroIndex records",
                file=sys.stderr,
            )
        return None

    print(tohex(bytes(KOD)))
    return KOD
