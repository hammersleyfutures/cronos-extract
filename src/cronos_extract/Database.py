# ABOUTME: Database: opens the Cro*.dat/.tad file pairs found in a CronosPro database directory.
# ABOUTME: Decodes the database and table definitions from CroStru.
import argparse
import os
import re
import struct
from binascii import b2a_hex
from collections.abc import Collection
from contextlib import ExitStack
from typing import Self

from . import koddecoder
from ._diagnostic import STRU_FILE, Diagnostic, DiagnosticKind, Reporter, for_table_definition
from ._format.files import open_regular_file
from .Datafile import Datafile
from .Datamodel import TableDefinition, undecodable_table
from .hexdump import strescape, toout
from .koddecoder import KODcoding
from .readers import ByteReader, decode_cp1251

# Printed after a database definition error: a KOD that isn't the database's own decodes the definition as garbage.
KOD_HINT = (
    "If the KOD used to read this database is not its own, the definition decodes as garbage; "
    "cronos-extract crack strucrack can derive the database's KOD."
)

# The files a Database opens unless told otherwise.
ALL_FILES = ("Stru", "Index", "Bank", "Sys")


class StoppingReporter:
    """
    A Reporter that passes each Diagnostic to `report` and remembers the first exception `report` raises.

    The readers catch broad exceptions, so they can swallow a callback's request to stop. Once an exception is
    remembered, every later call raises it again without calling `report`, and raise_remembered raises it for the
    caller to check after a reader returns or raises.
    """

    def __init__(self, report: Reporter) -> None:
        self._report = report
        self._error: BaseException | None = None

    def __call__(self, diagnostic: Diagnostic) -> None:
        self.raise_remembered()
        try:
            self._report(diagnostic)
        except BaseException as e:
            self._error = e
            raise

    def raise_remembered(self) -> None:
        """Raise the exception `report` raised, if it raised one."""
        if self._error is not None:
            raise self._error


class Database:
    """represent the entire database, consisting of Stru, Index and Bank files"""

    def __init__(
        self,
        dbdir: str,
        compact: bool,
        kod: KODcoding | None,
        report: Reporter,
        files: Collection[str] = ALL_FILES,
    ) -> None:
        """
        `dbdir` is the directory containing the Cro*.dat and Cro*.tad files.
        `compact` if set, the .tad file is not cached in memory, making dumps 15 % slower
        `kod` is a KOD coder object, or None to read the records without KOD decoding.
        `report` receives a Diagnostic for each problem that reading survives, such as a part of the database
        definition that is not laid out as expected.
        `files` names the components to open, from ALL_FILES; the others are None.
        """
        self.dbdir = dbdir
        self.compact = compact
        self.kod = kod
        self.files = files
        self.report = report

        # Stru+Index+Bank for the components for most databases
        self.stru = self.getfile("Stru")
        self.index = self.getfile("Index")
        self.bank = self.getfile("Bank")

        # the Sys file resides in the "Program Files\Cronos" directory, and
        # contains an index of all known databases.
        self.sys = self.getfile("Sys")

    @classmethod
    def from_datafiles(
        cls, dbdir: str, compact: bool, kod: KODcoding | None, stru: Datafile, bank: Datafile, report: Reporter
    ) -> Self:
        """
        Make a Database of the CroStru and CroBank Datafiles `stru` and `bank`, which the caller has opened.
        Closing the Database closes them.
        """
        db = cls(dbdir, compact, kod, report, files=())
        db.stru = stru
        db.bank = bank
        return db

    def close(self) -> None:
        """
        Close the files of every component of the database.
        """
        for datafile in (self.stru, self.index, self.bank, self.sys):
            if datafile:
                datafile.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def getfile(self, name: str) -> Datafile | None:
        """
        Returns a Datafile object for `name`.
        this function expects a `Cro<name>.dat` and a `Cro<name>.tad` file.
        When no such files exist, only one of them does, or one cannot be opened or is not a regular file,
        then None is returned.

        A component not named in `files` is not opened, and None is returned.

        `name` is matched case insensitively
        """
        if name not in self.files:
            return None
        try:
            datname = self.getname(name, "dat")
            tadname = self.getname(name, "tad")
            if datname and tadname:
                return self.opendatafile(name, datname, tadname)
        except OSError:
            return None
        return None

    def opendatafile(self, name: str, datname: str, tadname: str) -> Datafile:
        """
        Open a .dat/.tad pair as a Datafile, closing both files again if it can't be read.
        """
        with ExitStack() as stack:
            dat = stack.enter_context(open_regular_file(datname))
            tad = stack.enter_context(open_regular_file(tadname))
            datafile = Datafile(name, dat, tad, self.compact, self.kod, self.report)
            stack.pop_all()
        return datafile

    def getname(self, name: str, ext: str) -> str | None:
        """
        Get a case-insensitive filename match for 'name.ext'.
        Returns None when no matching file was not found.
        """
        basename = f"Cro{name}.{ext}"
        for fn in os.listdir(self.dbdir):
            if basename.lower() == fn.lower():
                return os.path.join(self.dbdir, fn)
        return None

    def dump(self, args: argparse.Namespace) -> None:
        """
        Calls the `dump` method on all database components.
        """
        if self.stru:
            self.stru.dump(args)
        if self.index:
            self.index.dump(args)
        if self.bank:
            self.bank.dump(args)
        if self.sys:
            self.sys.dump(args)

    def missing_stru_message(self) -> str:
        """
        Returns the message that explains that the database directory has no CroStru files.
        """
        return f"no CroStru.dat and CroStru.tad found in {self.dbdir}, which hold the table definitions"

    def report_structure(self, message: str, record: int | None = None) -> None:
        """
        Report `message` as an unexpected_structure Diagnostic about CroStru, at `record` when it is given.
        """
        self.report(Diagnostic(DiagnosticKind.UNEXPECTED_STRUCTURE, message, file=STRU_FILE, record=record))

    def decode_db_definition(self, data: bytes) -> dict[str, bytes]:
        """
        decode the 'bank' / database definition

        Raises ValueError when a key stored by reference names a CroStru record that is not open, out of range,
        deleted, or when the definition is cut off.
        """
        rd = ByteReader(data)

        d: dict[str, bytes] = dict()
        try:
            while not rd.eof():
                keyname = rd.readname()
                if keyname in d:
                    self.report_structure(f"duplicate key: {keyname}", record=1)

                index_or_length = rd.readdword()
                if index_or_length >> 31:
                    d[keyname] = rd.readbytes(index_or_length & 0x7FFFFFFF)
                else:
                    if self.stru is None:
                        raise ValueError(
                            f'key "{keyname}" refers to CroStru record {index_or_length}, but CroStru is not open'
                        )
                    if not 1 <= index_or_length <= self.stru.nrofrecords:
                        raise ValueError(
                            f'key "{keyname}" refers to CroStru record {index_or_length}, '
                            f"which CroStru does not hold ({self.stru.nrofrecords} records)"
                        )
                    refdata = self.stru.readrec(index_or_length)
                    if refdata is None:
                        raise ValueError(
                            f'key "{keyname}" refers to CroStru record {index_or_length}, which is deleted'
                        )
                    if refdata[:1] != b"\x04":
                        self.report_structure("expected refdata to start with 0x04", record=index_or_length)
                    d[keyname] = refdata[1:]
        except EOFError as e:
            raise ValueError(f"the database definition is cut off after {len(d)} keys") from e
        return d

    def dump_db_definition(self, args: argparse.Namespace, dbdict: dict[str, bytes]) -> None:
        """
        decode the 'bank' / database definition
        """
        for k, v in dbdict.items():
            if re.search(b"[^\x0d\x0a\x09\x20-\x7e\xc0-\xff]", v):
                print(f"{k:<20} - {toout(args, v)}")
            else:
                print(f'{k:<20} - "{strescape(v)}"')

    def read_db_definition(self) -> dict[str, bytes]:
        """
        Read and decode the database definition from CroStru record 1.
        Raises ValueError when CroStru is not open, has no record 1, when it is deleted, or when it can't be
        decoded.
        """
        if self.stru is None:
            raise ValueError("CroStru is not open, so it has no database definition")
        if self.stru.nrofrecords < 1:
            raise ValueError("CroStru holds no records, so it has no database definition")
        dbinfo = self.stru.readrec(1)
        if dbinfo is None:
            raise ValueError("CroStru record 1, which holds the database definition, is deleted")
        if dbinfo[:1] != b"\x03":
            self.report_structure("expected dbinfo to start with 0x03", record=1)
        return self.decode_db_definition(dbinfo[1:])

    def dump_db_table_defs(self, args: argparse.Namespace) -> None:
        """
        decode the table defs from recid #1, which always has table-id #3
        Note that I don't know if it is better to refer to this by recid, or by table-id.

        other table-id's found in CroStru:
            #4  -> large values referenced from tableid#3
        """
        dbdef = self.read_db_definition()
        self.dump_db_definition(args, dbdef)

        report = StoppingReporter(self.report)
        for k, v in dbdef.items():
            if k.startswith("Base") and k[4:].isnumeric():
                print(f"== {k} ==")
                try:
                    tbdef = TableDefinition(
                        v, dbdef.get("BaseImage" + k[4:], b""), report=for_table_definition(report, k)
                    )
                except Exception as e:
                    report.raise_remembered()
                    report(undecodable_table(k, e))
                    continue
                report.raise_remembered()
                tbdef.dump(args)
            elif k == "NS1":
                self.dump_ns1(v)

    def dump_ns1(self, data: bytes) -> None:
        if len(data) < 2:
            self.report_structure("NS1 is unexpectedly short")
            return
        (
            unk1,
            sh,
        ) = struct.unpack_from("<BB", data, 0)

        # NS1 is encoded with the default KOD table,
        # so we are not using stru.kod here.
        ns1kod = koddecoder.new()
        decoded_data = ns1kod.decode(sh, data[2:])

        if len(decoded_data) < 12:
            self.report_structure("NS1 is unexpectedly short")
            return
        (
            serial,
            unk2,
            pwlen,
        ) = struct.unpack_from("<LLL", decoded_data, 0)
        password = decode_cp1251(decoded_data[12 : 12 + pwlen])

        print(f"== NS1: ({unk1:02x},{sh:02x}) -> {serial:6d}, {unk2:d}, {pwlen:d}:'{password}'")

    def recdump(self, args: argparse.Namespace) -> None:
        """
        Function for outputing record contents of the various .dat files.

        This function is mostly useful for reverse-engineering the database format.
        Raises ValueError naming the file when the chosen file is not open.
        """
        if args.index:
            name = "Index"
        elif args.sys:
            name = "Sys"
        elif args.stru:
            name = "Stru"
        else:
            name = "Bank"
        # Each component is kept in the attribute named after it: index, sys, stru and bank.
        dbfile = getattr(self, name.lower())

        if not dbfile:
            raise ValueError(f"no Cro{name}.dat and Cro{name}.tad in {self.dbdir}")
        nerr = 0
        nr_recnone = 0
        nr_recempty = 0
        tabidxref = [0] * 256
        bytexref = [0] * 256
        for i in range(1, min(args.maxrecs, dbfile.nrofrecords) + 1):
            try:
                data = dbfile.readrec(i)
                if args.find1d:
                    if data and (data.find(b"\x1d") > 0 or data.find(b"\x1b") > 0):
                        print(f"record with '1d': {i:d} -> {b2a_hex(data)}")
                        break

                elif not args.stats:
                    if data is None:
                        print(f"{i:5d}: <deleted>")
                    else:
                        print(f"{i:5d}: {toout(args, data)}")
                else:
                    if data is None:
                        nr_recnone += 1
                    elif not len(data):
                        nr_recempty += 1
                    else:
                        tabidxref[data[0]] += 1
                        for b in data[1:]:
                            bytexref[b] += 1
                nerr = 0
            except Exception as e:
                print(f"{i:5d}: <{e}>")
                if args.debug:
                    raise
                nerr += 1
                if nerr > 5:
                    break

        if args.stats:
            print(f"-- table-id stats --, {nr_recnone:d} * none, {nr_recempty:d} * empty")
            for k, v in enumerate(tabidxref):
                if v:
                    print(f"{v:5d} * {k:02x}")
            print("-- byte stats --")
            for k, v in enumerate(bytexref):
                if v:
                    print(f"{v:5d} * {k:02x}")
