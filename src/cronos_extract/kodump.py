# ABOUTME: kodump subcommand: KOD-decodes and hexdumps a byte range from a file or stdin.
# ABOUTME: Can try every shift value, which helps find the right one when reverse-engineering.
"""
This module has the functions for the 'inspect kodump' subcommand of cronos-extract.
"""

import io
import struct

from ._format.files import open_regular_file
from .hexdump import hexdump, toout, unhex


def decode_kod(kod, args, data):
    """
    various methods of hexdumping KOD decoded data.
    """
    if args.nokod:
        # plain hexdump, no KOD decode
        hexdump(args.offset, data, args)

    elif args.shift:
        # explicitly specified shift.
        args.shift = int(args.shift, 0)
        enc = kod.decode(args.shift, data)
        hexdump(args.offset, enc, args)
    elif args.increment:

        def incdata(data, s):
            """
            add 's' to each byte.
            This is useful for finding the correct shift from an incorrectly shifted chunk.
            """
            return b"".join(struct.pack("<B", (_ + s) & 0xFF) for _ in data)

        # explicitly specified shift.
        for s in range(256):
            enc = incdata(data, s)
            print(f"{s:02x}: {toout(args, enc)}")
    else:
        # output with all possible 'shift' values.
        for s in range(256):
            enc = kod.encode(s, data) if args.invkod else kod.decode(s, data)
            print(f"{s:02x}: {toout(args, enc)}")


def kod_hexdump(kod, args):
    """
    handle the `kodump` subcommand, KOD decode a section of a data file

    This function is mostly useful for reverse-engineering the database format.
    """
    args.offset = int(args.offset, 0)
    if args.length:
        args.length = int(args.length, 0)
    elif args.endofs:
        args.endofs = int(args.endofs, 0)
        args.length = args.endofs - args.offset

    if args.width:
        args.width = int(args.width, 0)
    else:
        args.width = 64 if args.ascdump else 16

    if args.filename:
        with open_regular_file(args.filename) as fh:
            if args.length is None:
                fh.seek(0, io.SEEK_END)
                filesize = fh.tell()
                args.length = filesize - args.offset
            fh.seek(args.offset)
            data = fh.read(args.length)
            decode_kod(kod, args, data)
    else:
        # no filename -> read from stdin.
        import sys

        data = sys.stdin.buffer.read()
        if args.unhex:
            data = unhex(data)
        decode_kod(kod, args, data)
