# ABOUTME: crodump command: subcommands for inspecting CronosPro databases and recovering KOD tables.
# ABOUTME: Includes strucrack and dbcrack, which derive the KOD substitution table statistically.
import argparse
import sys

from .Database import Database
from .Datamodel import TableDefinition
from .hexdump import as1251, asambigoushex, asasc, tohex, unhex
from .koddecoder import match_with_mismatches
from .kodump import kod_hexdump
from .readers import ByteReader


def destruct_sys3_def(rd):
    # todo
    pass


def destruct_sys4_def(rd):
    """
    decode type 4 of the records found in CroSys.

    This function is only useful for reverse-engineering the CroSys format.
    """
    n = rd.readdword()
    for _ in range(n):
        marker = rd.readdword()
        description = rd.readlongstring()
        path = rd.readlongstring()
        marker2 = rd.readdword()

        print(f"{marker:08x};{marker2:08x}: {path:<50} : {description}")


def destruct_sys_definition(args, data):
    """
    Decode the 'sys' / dbindex definition

    This function is only useful for reverse-engineering the CroSys format.
    """
    rd = ByteReader(data)

    systype = rd.readbyte()
    if systype == 3:
        return destruct_sys3_def(rd)
    elif systype == 4:
        return destruct_sys4_def(rd)
    else:
        raise Exception("unsupported sys record")


def cro_dump(kod, args):
    """handle 'crodump' subcommand"""
    if args.maxrecs:
        args.maxrecs = int(args.maxrecs, 0)
    else:
        # an arbitrarily large number.
        args.maxrecs = 0xFFFFFFFF

    db = Database(args.dbdir, args.compact, kod)
    db.dump(args)


def stru_dump(kod, args):
    """handle 'strudump' subcommand"""
    db = Database(args.dbdir, args.compact, kod)
    db.strudump(args)


def sys_dump(kod, args):
    """hexdump all CroSys records"""
    # an arbitrarily large number.
    args.maxrecs = 0xFFFFFFFF

    db = Database(args.dbdir, args.compact, kod)
    if db.sys:
        db.sys.dump(args)


def rec_dump(kod, args):
    """hexdump all records of the specified CroXXX.dat file."""
    if args.maxrecs:
        args.maxrecs = int(args.maxrecs, 0)
    else:
        # an arbitrarily large number.
        args.maxrecs = 0xFFFFFFFF

    db = Database(args.dbdir, args.compact, kod)
    db.recdump(args)


def destruct(kod, args):
    """
    decode the index#1 structure information record
    Takes hex input from stdin.
    """
    import sys

    data = sys.stdin.buffer.read()
    data = unhex(data)

    if args.type == 1:
        # create a dummy db object
        db = Database(".", args.compact)
        db.dump_db_definition(args, data)
    elif args.type == 2:
        tbdef = TableDefinition(data)
        tbdef.dump(args)
    elif args.type == 3:
        destruct_sys_definition(args, data)


def color_code(c, confidence, force):
    from sys import stdout

    is_a_tty = hasattr(stdout, "isatty") and stdout.isatty()
    if not force and not is_a_tty:
        return c

    if confidence < 0:
        return "\033[96m" + c + "\033[0m"
    if confidence == 0:
        return "\033[31m" + c + "\033[0m"
    if confidence == 255:
        return "\033[32m" + c + "\033[0m"
    if confidence > 3:
        return "\033[93m" + c + "\033[0m"
    return "\033[94m" + c + "\033[0m"


FIX_FORMAT = "use xxyy=C or xxyycc, with the encrypted byte xx, the shift yy and the plaintext C or cc"


def parse_fix(value):
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
    return i, o, c


def strucrack(kod, args):
    """
    This function derives the KOD key from the assumption that most bytes in
    the CroStru records will be zero, given a sufficient number of CroStru
    items, statistically the most common bytes will encode to '0x00'
    """

    # start without 'KOD' table, so we will get the encrypted records
    with Database(args.dbdir, args.compact, None) as db:
        return derive_kod_from_stru(db, args)


def kod_from_xref(xref):
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
        #       print("%02x :: %02x :: %d" % (i, k, v))
        KOD[k] = i
        KOD_CONFIDENCE[k] = v
    return KOD, KOD_CONFIDENCE


def derive_kod_from_stru(db, args):
    """
    Derive the KOD table from the encrypted CroStru or CroSys records of `db`, as strucrack describes.
    """
    if args.sys:
        table = db.sys
        if not db.sys:
            if not args.silent:
                print(f"no CroSys.dat file found in {args.dbdir}")
            return
    else:
        table = db.stru
        if not db.stru:
            if not args.silent:
                print(f"no CroStru.dat file found in {args.dbdir}")
            return

    xref = [[0] * 256 for _ in range(256)]
    for i, data in enumerate(table.enumrecords()):
        if not data:
            continue
        for ofs, byte in enumerate(data):
            xref[(ofs + i + 1) % 256][byte] += 1

    KOD, KOD_CONFIDENCE = kod_from_xref(xref)

    #       Test deducted KOD against the default one, for debugging purposes
    #        if KOD[k] != INITIAL_KOD[k]:
    #            print("# KOD[%02x] == %02x, should be %02x" % (i, KOD[i], INITIAL_KOD[i]))
    #            KOD[k] = -1

    for i, o, c in args.fix or []:
        KOD[i] = (c + o) % 256
        KOD_CONFIDENCE[i] = 255
        # print("%02x %02x %02x" % ((c + o) % 256, i, o))

    # For chunks of text where record and offset is known, set the KOD
    for fix in args.text or []:
        record, line, offset, text = fix.split(":", 3)
        data = table.readrec(int(record) + 1)
        dataoff = int(line) + int(offset)
        o = int(record) + 1 + int(line) + int(offset)
        for i, c in enumerate(text):
            d = data[dataoff + i]
            KOD[d] = (int.from_bytes(as1251(c), "little") + o + i) % 256
            KOD_CONFIDENCE[d] = 255

    kod_set = set([v for o, v in enumerate(KOD) if KOD_CONFIDENCE[o] > 0])
    unset_entries = [o for o, v in enumerate(KOD) if KOD_CONFIDENCE[o] == 0]
    unused_values = [v for v in sorted(set(range(0, 256)).difference(kod_set))]

    # if there's only one mapping missing in KOD and only one value not used, we
    # just assume those to belong together with a low confidence
    if len(unset_entries) == 1 and len(unused_values) == 1:
        entry = unset_entries[0]
        KOD[entry] = unused_values[0]
        KOD_CONFIDENCE[entry] = 1

    # Show duplicates that may arise by the user forcing KOD entries from command line
    kod_set = [v for o, v in enumerate(KOD) if KOD_CONFIDENCE[o] > 0]
    duplicates = [(o, v) for o, v in enumerate(KOD) if kod_set.count(v) > 1 and KOD_CONFIDENCE[o] > 0]
    duplicates = sorted(duplicates, key=lambda x: x[1])

    for o, _v in duplicates:
        if KOD_CONFIDENCE[o] < 255:
            KOD_CONFIDENCE[o] = -1

    from . import koddecoder

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

    force_color = args.color

    # Dump partially decoded stru records for the user to try to spot patterns
    w = args.width
    records = [] if args.silent else table.enumrecords()
    for i, data in enumerate(records):
        if not data:
            continue

        print(f"Processing record number {i:d}")

        candidate, candidate_confidence = kod.try_decode(i + 1, data)

        for s, min_matching, deststring, destoffset in known_strings:
            incomplete_matches = match_with_mismatches(candidate, candidate_confidence, s, min_matching)
            # print(sisnm)
            for ofix in incomplete_matches:
                do = ofix[0]
                print(f"Found {asasc(candidate[do : do + len(s)])} which looks a lot like {asasc(s)} ")
                print("Add the following switches to your command line to fix the decoder box:\n    ", end="")
                for o, c in enumerate(deststring):
                    print(
                        f"-f {data[do + o + destoffset]:02x}{(do + i + 1 + o + destoffset) % 256:02x}{c:02x} ",
                        end="",
                    )
                print("\n")

        candidate_chunks = [candidate[j : j + w] for j in range(0, len(candidate), w)]
        for ofs, chunk in enumerate(candidate_chunks):
            confidence = candidate_confidence[ofs * w : ofs * w + w]
            text = asasc(chunk, confidence)
            hexed = asambigoushex(chunk, confidence)

            colored = "".join(color_code(c, confidence[o], force_color) for o, c in enumerate(text))
            colored_hexed = "".join(color_code(c, confidence[o >> 1], force_color) for o, c in enumerate(hexed))
            fix_helper = " ".join(
                f"{b:02x}{(w * ofs + i + 1 + o) % 256:02x}={color_code(text[o], confidence[o], force_color)}"
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
                color_code(f"[{o:02x}=>{v:02x} ({KOD_CONFIDENCE[o]:d})]", KOD_CONFIDENCE[o], force_color)
                for o, v in duplicates
            )
        )

    # If the KOD is not completely resolved, show the missing mappings. Entries with a duplicate value
    # count as unresolved, and a KOD that is not a permutation of 0..255 can't decode the database.
    unset_count = len([o for o in KOD_CONFIDENCE if o <= 0])
    if unset_count > 0 or sorted(KOD) != list(range(256)):
        if args.noninteractive:
            return
        if not args.silent:
            kod_set = set([v for o, v in enumerate(KOD) if KOD_CONFIDENCE[o] > 0])
            unset_entries = ", ".join([f"{o:02x}" for o, v in enumerate(KOD) if KOD_CONFIDENCE[o] <= 0])
            unused_values = ", ".join([f"{v:02x}" for v in sorted(set(range(0, 256)).difference(kod_set))])
            print(f"\nAmbigous result when cracking. {unset_count:d} entries unsolved. Missing mappings:")
            print(f"[{unset_entries}] => [{unused_values}]\n")
            if unset_count == 0:
                print("The forced KOD entries map several entries to the same value, see the duplicates above.\n")
            print("KOD estimate:")
            print(
                "".join(
                    color_code(f"{c:02x}" if KOD_CONFIDENCE[o] > 0 else "??", KOD_CONFIDENCE[o], force_color)
                    for o, c in enumerate(KOD)
                )
            )

            print("\nIf you can provide clues for unresolved KOD entries by looking at the output, pass them via")
            print("crodump strucrack -f f103=B  -f f10342")
        return None

    if not args.silent:
        print(
            "Use the following database key to decrypt the database with crodump or croconvert with the --kod option:"
        )
        print(tohex(bytes(KOD)))

    return KOD


def dbcrack(kod, args):
    """
    This function derives the KOD key from the assumption that most records in CroIndex
    and CroBank will be compressed, and start with:
      uint16 size
      byte  0x08
      byte  0x00

    So because the fourth byte in each record will be 0x00 when kod-decoded, I can
    use this as the inverse of the KOD table, adjusting for record-index.

    """
    # start without 'KOD' table, so we will get the encrypted records
    with Database(args.dbdir, args.compact, None) as db:
        return derive_kod_from_bank_and_index(db, args)


def derive_kod_from_bank_and_index(db, args):
    """
    Derive the KOD table from the encrypted CroBank and CroIndex records of `db`, as dbcrack describes.
    """
    xref = [[0] * 256 for _ in range(256)]

    for dbfile in db.bank, db.index:
        if not dbfile:
            if not args.silent:
                print(f"no data file found in {args.dbdir}")
            return
        for i in range(1, min(10000, dbfile.nrofrecords)):
            rec = dbfile.readrec(i)
            if rec and len(rec) > 11:
                xref[(i + 3) % 256][rec[3]] += 1

    KOD, KOD_CONFIDENCE = kod_from_xref(xref)

    # Rows that found no data, or lost their byte to another row, leave entries unresolved.
    unset_count = len([o for o in KOD_CONFIDENCE if o <= 0])
    if unset_count > 0 or sorted(KOD) != list(range(256)):
        if not args.silent:
            print(f"Ambigous result when cracking. {unset_count:d} entries unsolved: too few CroBank/CroIndex records")
        return None

    if not args.silent:
        print(tohex(bytes(KOD)))

    return KOD


def build_parser():
    """
    Build the argument parser for the crodump command and its subcommands.
    """
    parser = argparse.ArgumentParser(description="CRO hexdumper")
    subparsers = parser.add_subparsers(
        title="commands", help="Use the --help option for the individual sub commands for more details"
    )
    parser.set_defaults(handler=lambda *args: parser.print_help())
    parser.add_argument("--debug", action="store_true", help="break on exceptions")
    parser.add_argument("--kod", type=str, help="specify custom KOD table")
    parser.add_argument("--strucrack", action="store_true", help="infer the KOD sbox from CroStru.dat")
    parser.add_argument("--dbcrack", action="store_true", help="infer the KOD sbox from CroBank.dat + CroIndex.dat")
    parser.add_argument("--nokod", "-n", action="store_true", help="don't KOD decode")
    parser.add_argument(
        "--compact",
        action="store_true",
        help="save memory by not caching the index, note: increases convert time by factor 1.15",
    )

    p = subparsers.add_parser("kodump", help="KOD/hex dumper")
    p.add_argument("--offset", "-o", type=str, default="0")
    p.add_argument("--length", "-l", type=str)
    p.add_argument("--width", "-w", type=str)
    p.add_argument("--endofs", "-e", type=str)
    p.add_argument("--nokod", "-n", action="store_true", help="don't KOD decode")
    p.add_argument("--unhex", "-x", action="store_true", help="assume the input contains hex data")
    p.add_argument("--shift", "-s", type=str, help="KOD decode with the specified shift")
    p.add_argument(
        "--increment",
        "-i",
        action="store_true",
        help="assume data is already KOD decoded, but with wrong shift -> dump alternatives.",
    )
    p.add_argument("--ascdump", "-a", action="store_true", help="CP1251 asc dump of the data")
    p.add_argument("--invkod", "-I", action="store_true", help="KOD encode")
    p.add_argument("filename", type=str, nargs="?", help="dump either stdin, or the specified file")
    p.set_defaults(handler=kod_hexdump)

    p = subparsers.add_parser("crodump", help="CROdumper")
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--ascdump", "-a", action="store_true")
    p.add_argument("--maxrecs", "-m", type=str, help="max nr or recots to output")
    p.add_argument("--nodecompress", action="store_false", dest="decompress", default="true")
    p.add_argument("dbdir", type=str)
    p.set_defaults(handler=cro_dump)

    p = subparsers.add_parser("sysdump", help="SYSdumper")
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--ascdump", "-a", action="store_true")
    p.add_argument("--nodecompress", action="store_false", dest="decompress", default="true")
    p.add_argument("dbdir", type=str)
    p.set_defaults(handler=sys_dump)

    p = subparsers.add_parser("recdump", help="record dumper")
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--ascdump", "-a", action="store_true")
    p.add_argument("--maxrecs", "-m", type=str, help="max nr or recots to output")
    p.add_argument("--find1d", action="store_true", help="Find records with 0x1d in it")
    p.add_argument(
        "--stats",
        action="store_true",
        help="calc table stats from the first byte of each record",
    )
    p.add_argument("--index", action="store_true", help="dump CroIndex")
    p.add_argument("--stru", action="store_true", help="dump CroStru")
    p.add_argument("--bank", action="store_true", help="dump CroBank")
    p.add_argument("--sys", action="store_true", help="dump CroSys")
    p.add_argument("dbdir", type=str)
    p.set_defaults(handler=rec_dump)

    p = subparsers.add_parser("strudump", help="STRUdumper")
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--ascdump", "-a", action="store_true")
    p.add_argument("dbdir", type=str)
    p.set_defaults(handler=stru_dump)

    p = subparsers.add_parser("destruct", help="Stru dumper")
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--ascdump", "-a", action="store_true")
    p.add_argument("--type", "-t", type=int, help="what type of record to destruct")
    p.set_defaults(handler=destruct)

    p = subparsers.add_parser("strucrack", help="Crack v4 KOD encrypion, bypassing the need for the database password.")
    p.add_argument("--sys", action="store_true", help="Use CroSys for cracking")
    p.add_argument("--silent", action="store_true", help="no output")
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
        help="add fixed bytes to decoder box by providing whole strings for a position in a record, "
        "format is record:line:offset:plaintext",
    )
    p.add_argument("--width", "-w", type=int, help="max number of decoded characters on screen", default=24)

    p.add_argument("dbdir", type=str)
    p.set_defaults(handler=strucrack)

    p = subparsers.add_parser("dbcrack", help="Crack v4 KOD encrypion, bypassing the need for the database password.")
    p.add_argument("--silent", action="store_true", help="no output")
    p.add_argument("dbdir", type=str)
    p.set_defaults(handler=dbcrack)

    return parser


CRACK_FAILED_MESSAGE = (
    "Can't automatically crack the database password. Try using   crodump strucrack   "
    "and pass the database key (KOD) using --kod"
)


def crack_kod(method, dbdir, compact):
    """
    Derive the KOD table of the database in `dbdir` with the `strucrack` or `dbcrack` method, without output.

    The options are parsed by the method's own subcommand parser, so every option has its default value.
    Returns None when the table can't be derived automatically.
    """
    argv = ["--compact"] if compact else []
    argv += [method, "--silent"]
    if method == "strucrack":
        argv.append("--noninteractive")
    args = build_parser().parse_args([*argv, dbdir])
    return args.handler(None, args)


def main():
    args = build_parser().parse_args()

    from . import koddecoder

    if args.kod:
        if len(args.kod) != 512:
            raise Exception("--kod should have a 512 hex digit argument")
        kod = koddecoder.new(list(unhex(args.kod)))
    elif args.nokod:
        kod = None
    elif args.strucrack or args.dbcrack:
        if not hasattr(args, "dbdir"):
            sys.exit("--strucrack and --dbcrack need a subcommand that reads a database directory")
        cracked = crack_kod("strucrack" if args.strucrack else "dbcrack", args.dbdir, args.compact)
        if not cracked:
            sys.exit(CRACK_FAILED_MESSAGE)
        kod = koddecoder.new(cracked)
    else:
        kod = koddecoder.new()

    if args.handler:
        args.handler(kod, args)


if __name__ == "__main__":
    main()
