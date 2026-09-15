# ABOUTME: Example script that prints table definitions and the first records of one or more databases.
# ABOUTME: Shows how to enumerate tables and records with the Database API.
"""
`dumpdbfields` demonstrates how to enumerate tables and records.
"""

import os
import os.path

from .crodump import crack_kod
from .Database import Database
from .hexdump import unhex


def processargs(args):
    for dbpath in args.dbdirs:
        if args.recurse:
            for path, _, files in os.walk(dbpath):
                # check if there is a crostru file in this directory.
                if any(_ for _ in files if _.lower() == "crostru.dat"):
                    yield path
        else:
            yield dbpath


def main():
    import argparse

    parser = argparse.ArgumentParser(description="db field dumper")
    parser.add_argument("--kod", type=str, help="specify custom KOD table")
    parser.add_argument("--strucrack", action="store_true", help="infer the KOD sbox from CroStru.dat")
    parser.add_argument("--dbcrack", action="store_true", help="infer the KOD sbox from CroIndex.dat+CroBank.dat")
    parser.add_argument("--nokod", "-n", action="store_true", help="don't KOD decode")
    parser.add_argument("--maxrecs", "-m", type=int, default=100)
    parser.add_argument("--recurse", "-r", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("dbdirs", type=str, nargs="*")
    args = parser.parse_args()

    for path in processargs(args):
        try:
            from . import koddecoder

            if args.kod:
                if len(args.kod) != 512:
                    raise Exception("--kod should have a 512 hex digit argument")
                kod = koddecoder.new(list(unhex(args.kod)))
            elif args.nokod:
                kod = None
            elif args.strucrack or args.dbcrack:
                cracked = crack_kod("strucrack" if args.strucrack else "dbcrack", path, False)
                if not cracked:
                    return
                kod = koddecoder.new(cracked)
            else:
                kod = koddecoder.new()

            db = Database(path, False, kod)
            for tab in db.enumerate_tables():
                tab.dump(args)
                print(f"nr of records: {db.bank.nrofrecords:d}")
                for i, rec in enumerate(db.enumerate_records(tab), start=1):
                    if i > args.maxrecs:
                        break
                    for field, fielddef in zip(rec.fields, tab.fields, strict=True):
                        print(f">> {fielddef} -- {field.content}")
        except Exception as e:
            print(f"ERROR: {e}")


if __name__ == "__main__":
    main()
