# ABOUTME: The inspect subcommands, strudump, recdump, crodump, destruct and kodump, over the internal readers.
# ABOUTME: They show what the API hides, as the readers dump it, and stop only for a file they read that cannot be read.
import argparse
import sys
from collections.abc import Collection
from typing import cast

from .._api.errors import NotACronosFile
from .._api.kod import kod_coder
from ..Database import ALL_FILES, KOD_HINT, Database
from ..Datafile import Datafile
from ..Datamodel import TableDefinition, describe_error
from ..hexdump import unhex
from ..kodump import kod_hexdump
from ..readers import ByteReader
from .options import Subcommands, kod_options, selected_kod
from .report import Failure, Problem, Report

# The number of records dumped when --maxrecs is not given: all of them.
ALL_RECORDS = 0xFFFFFFFF


def destruct_sys3_def(rd: ByteReader) -> None:
    # todo
    pass


def destruct_sys4_def(rd: ByteReader) -> None:
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


def destruct_sys_definition(args: argparse.Namespace, data: bytes) -> None:
    """
    Decode the 'sys' / dbindex definition

    This function is only useful for reverse-engineering the CroSys format.
    """
    rd = ByteReader(data)

    systype = rd.readbyte()
    if systype == 3:
        destruct_sys3_def(rd)
    elif systype == 4:
        destruct_sys4_def(rd)
    else:
        raise Exception("unsupported sys record")


def add_parser(subcommands: Subcommands) -> None:
    """Add the inspect subcommand and its own subcommands to `subcommands`."""
    inspect_parser = subcommands.add_parser(
        "inspect", help="dump a database's internal structures, for studying the file format"
    )
    commands = inspect_parser.add_subparsers(dest="inspect_command", required=True, metavar="SUBCOMMAND")

    p = commands.add_parser("strudump", parents=[kod_options()], help="dump the database and table definitions")
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--ascdump", "-a", action="store_true")
    p.add_argument("dbdir", type=str)
    p.set_defaults(handler=run_strudump, command_parser=p)

    p = commands.add_parser("recdump", parents=[kod_options()], help="dump the records of one Cro file")
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--ascdump", "-a", action="store_true")
    p.add_argument("--maxrecs", "-m", type=str, help="max nr or recots to output")
    p.add_argument("--find1d", action="store_true", help="Find records with 0x1d in it")
    p.add_argument("--stats", action="store_true", help="calc table stats from the first byte of each record")
    p.add_argument("--index", action="store_true", help="dump CroIndex")
    p.add_argument("--stru", action="store_true", help="dump CroStru")
    p.add_argument("--bank", action="store_true", help="dump CroBank")
    p.add_argument("--sys", action="store_true", help="dump CroSys")
    p.add_argument("--debug", action="store_true", help="stop with the traceback of a record that cannot be read")
    p.add_argument("dbdir", type=str)
    p.set_defaults(handler=run_recdump, command_parser=p)

    p = commands.add_parser("crodump", parents=[kod_options()], help="dump every Cro file byte range by byte range")
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--ascdump", "-a", action="store_true")
    p.add_argument("--maxrecs", "-m", type=str, help="max nr or recots to output")
    p.add_argument("--nodecompress", action="store_false", dest="decompress", default="true")
    p.add_argument("dbdir", type=str)
    p.set_defaults(handler=run_crodump, command_parser=p)

    p = commands.add_parser(
        "destruct", parents=[kod_options(crack=False)], help="decode a definition given as hex on stdin"
    )
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--ascdump", "-a", action="store_true")
    p.add_argument("--type", "-t", type=int, help="what type of record to destruct")
    p.add_argument(
        "dbdir", nargs="?", default=".", help="the database whose CroStru holds keys stored by reference (-t 1)"
    )
    p.set_defaults(handler=run_destruct, command_parser=p)

    p = commands.add_parser(
        "kodump", parents=[kod_options(crack=False, compact=False)], help="KOD-decode and hexdump a file or stdin"
    )
    p.add_argument("--offset", "-o", type=str, default="0")
    p.add_argument("--length", "-l", type=str)
    p.add_argument("--width", "-w", type=str)
    p.add_argument("--endofs", "-e", type=str)
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
    p.set_defaults(handler=run_kodump, command_parser=p)


def open_component(db: Database, base: str, *, required: bool) -> Datafile | None:
    """
    Cro<base> of `db` as a Datafile, or None when its .dat or its .tad is absent.

    A file that cannot be read raises NotACronosFile naming it when `required`, and otherwise is reported as an
    unreadable_file warning and left out. OSError from listing the directory propagates.
    """
    datname = db.getname(base, "dat")
    tadname = db.getname(base, "tad")
    if not datname or not tadname:
        return None
    try:
        return cast(Datafile, db.opendatafile(base, datname, tadname))
    except Exception as e:
        # Datafile raises OSError, ValueError, struct.error and a bare Exception for a file it cannot read.
        if required:
            raise NotACronosFile(f"Cro{base}.dat in {db.dbdir} cannot be read: {describe_error(e)}") from e
        Report().problem(
            Problem(
                "unreadable_file",
                f"the file cannot be read and is left out: {describe_error(e)}",
                file=f"Cro{base}.dat",
            )
        )
        return None


def open_database(args: argparse.Namespace, required: Collection[str]) -> Database:
    """
    The database in args.dbdir with the KOD the options select, its Cro files opened through open_component.

    The files named in `required` stop the command when they cannot be read.
    """
    db = Database(args.dbdir, args.compact, kod_coder(selected_kod(args)), files=())
    try:
        for base in ALL_FILES:
            # Database keeps each file in the attribute named after it: stru, index, bank and sys.
            setattr(db, base.lower(), open_component(db, base, required=base in required))
    except BaseException:
        db.close()
        raise
    return db


def max_records(text: str | None) -> int:
    """The number of records --maxrecs asks for, in any base Python reads, or all of them."""
    return int(text, 0) if text else ALL_RECORDS


def run_strudump(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Print the database definition and every table definition in CroStru."""
    with open_database(args, required=("Stru",)) as db:
        if db.stru is None:
            raise NotACronosFile(db.missing_stru_message())
        try:
            db.dump_db_table_defs(args)
        except ValueError as e:
            raise Failure(f"{e}\n{KOD_HINT}") from e
    return 0


def recdump_file(args: argparse.Namespace) -> str:
    """The Cro file recdump dumps, as Database.recdump chooses it."""
    if args.index:
        return "Index"
    if args.sys:
        return "Sys"
    if args.stru:
        return "Stru"
    return "Bank"


def run_recdump(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Hexdump the records of one Cro file."""
    args.maxrecs = max_records(args.maxrecs)
    with open_database(args, required=(recdump_file(args),)) as db:
        db.recdump(args)
    return 0


def run_crodump(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Dump every Cro file present, byte range by byte range."""
    args.maxrecs = max_records(args.maxrecs)
    with open_database(args, required=ALL_FILES) as db:
        db.dump(args)
    return 0


def run_destruct(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Decode the definition given as hex on stdin: a database (-t 1), table (-t 2) or CroSys (-t 3) definition."""
    data = unhex(sys.stdin.buffer.read())
    if args.type == 1:
        with open_database(args, required=()) as db:
            db.dump_db_definition(args, db.decode_db_definition(data))
    elif args.type == 2:
        TableDefinition(data).dump(args)
    elif args.type == 3:
        destruct_sys_definition(args, data)
    return 0


def run_kodump(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """KOD-decode and hexdump a byte range of a file, or of stdin."""
    kod_hexdump(kod_coder(selected_kod(args)), args)
    return 0
