# ABOUTME: Database: opens the Cro*.dat/.tad file pairs found in a CronosPro database directory.
# ABOUTME: Decodes the database and table definitions from CroStru and enumerates tables, records and files.
import base64
import os
import re
import struct
import sys
from binascii import b2a_hex
from contextlib import ExitStack
from functools import cached_property

from . import koddecoder
from ._diagnostic import STRU_FILE, Diagnostic, DiagnosticKind, for_table_definition
from ._format.files import open_regular_file
from .Datafile import Datafile
from .Datamodel import Record, TableDefinition, describe_error
from .hexdump import ashex, strescape, toout
from .readers import ByteReader, decode_cp1251

# Printed after a database definition error: a KOD that isn't the database's own decodes the definition as garbage.
KOD_HINT = (
    "If the KOD used to read this database is not its own, the definition decodes as garbage; "
    "cronos-extract crack strucrack can derive the database's KOD."
)

# The files a Database opens unless told otherwise.
ALL_FILES = ("Stru", "Index", "Bank", "Sys")


class Database:
    """represent the entire database, consisting of Stru, Index and Bank files"""

    # The number of records enumerate_records yielded with fields that could not be decoded.
    incomplete_records = 0

    def __init__(self, dbdir, compact, kod, report, files=ALL_FILES):
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
    def from_datafiles(cls, dbdir, compact, kod, stru, bank, report):
        """
        Make a Database of the CroStru and CroBank Datafiles `stru` and `bank`, which the caller has opened.
        Closing the Database closes them.
        """
        db = cls(dbdir, compact, kod, report, files=())
        db.stru = stru
        db.bank = bank
        return db

    def close(self):
        """
        Close the files of every component of the database.
        """
        for datafile in (self.stru, self.index, self.bank, self.sys):
            if datafile:
                datafile.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def getfile(self, name):
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

    def opendatafile(self, name, datname, tadname):
        """
        Open a .dat/.tad pair as a Datafile, closing both files again if it can't be read.
        """
        with ExitStack() as stack:
            dat = stack.enter_context(open_regular_file(datname))
            tad = stack.enter_context(open_regular_file(tadname))
            datafile = Datafile(name, dat, tad, self.compact, self.kod, self.report)
            stack.pop_all()
        return datafile

    def getname(self, name, ext):
        """
        Get a case-insensitive filename match for 'name.ext'.
        Returns None when no matching file was not found.
        """
        basename = f"Cro{name}.{ext}"
        for fn in os.listdir(self.dbdir):
            if basename.lower() == fn.lower():
                return os.path.join(self.dbdir, fn)
        return None

    def dump(self, args):
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

    def missing_stru_message(self):
        """
        Returns the message that explains that the database directory has no CroStru files.
        """
        return f"no CroStru.dat and CroStru.tad found in {self.dbdir}, which hold the table definitions"

    def report_structure(self, message, record=None):
        """
        Report `message` as an unexpected_structure Diagnostic about CroStru, at `record` when it is given.
        """
        self.report(Diagnostic(DiagnosticKind.UNEXPECTED_STRUCTURE, message, file=STRU_FILE, record=record))

    def decode_db_definition(self, data):
        """
        decode the 'bank' / database definition
        """
        rd = ByteReader(data)

        d = dict()
        try:
            while not rd.eof():
                keyname = rd.readname()
                if keyname in d:
                    self.report_structure(f"duplicate key: {keyname}", record=1)

                index_or_length = rd.readdword()
                if index_or_length >> 31:
                    d[keyname] = rd.readbytes(index_or_length & 0x7FFFFFFF)
                else:
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

    def dump_db_definition(self, args, dbdict):
        """
        decode the 'bank' / database definition
        """
        for k, v in dbdict.items():
            if re.search(b"[^\x0d\x0a\x09\x20-\x7e\xc0-\xff]", v):
                print(f"{k:<20} - {toout(args, v)}")
            else:
                print(f'{k:<20} - "{strescape(v)}"')

    def read_db_definition(self):
        """
        Read and decode the database definition from CroStru record 1.
        Raises ValueError when CroStru has no record 1, when it is deleted, or when it can't be decoded.
        """
        if self.stru.nrofrecords < 1:
            raise ValueError("CroStru holds no records, so it has no database definition")
        dbinfo = self.stru.readrec(1)
        if dbinfo is None:
            raise ValueError("CroStru record 1, which holds the database definition, is deleted")
        if dbinfo[:1] != b"\x03":
            self.report_structure("expected dbinfo to start with 0x03", record=1)
        return self.decode_db_definition(dbinfo[1:])

    def dump_db_table_defs(self, args):
        """
        decode the table defs from recid #1, which always has table-id #3
        Note that I don't know if it is better to refer to this by recid, or by table-id.

        other table-id's found in CroStru:
            #4  -> large values referenced from tableid#3
        """
        dbdef = self.read_db_definition()
        self.dump_db_definition(args, dbdef)

        for k, v in dbdef.items():
            if k.startswith("Base") and k[4:].isnumeric():
                print(f"== {k} ==")
                tbdef = TableDefinition(
                    v, dbdef.get("BaseImage" + k[4:], b""), report=for_table_definition(self.report, k)
                )
                tbdef.dump(args)
            elif k == "NS1":
                self.dump_ns1(v)

    def dump_ns1(self, data):
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

    def enumerate_tables(self, files=False):
        """
        yields a TableDefinition object for all `BaseNNN` entries found in CroStru
        """
        if not self.stru:
            raise FileNotFoundError(self.missing_stru_message())
        try:
            dbdef = self.read_db_definition()
        except Exception as e:
            print(f"ERROR decoding db definition: {e}", file=sys.stderr)
            print(KOD_HINT, file=sys.stderr)
            return

        for k, v in dbdef.items():
            if k.startswith("Base") and k[4:].isnumeric():
                report = for_table_definition(self.report, k)
                if files and k[4:] == "000":
                    yield TableDefinition(v, report=report)
                if not files and k[4:] != "000":
                    yield TableDefinition(v, dbdef.get("BaseImage" + k[4:], b""), report=report)

    def enumerate_records(self, table):
        """
        Yields a Record object for all records in CroBank matching
        the tableid from `table`

        usage:
        for tab in db.enumerate_tables():
            for rec in db.enumerate_records(tab):
                print(sqlformatter(tab, rec))
        """
        for i in range(self.bank.nrofrecords):
            data = self.readbankrec(i + 1)
            if data and data[0] == table.tableid:
                record = Record(i + 1, table.fields, data[1:])
                if record.errors:
                    self.incomplete_records += 1
                for fieldname, error in record.errors:
                    print(
                        f'Warning: record {i + 1:d} in table "{table.tablename}": field "{fieldname}" could not be '
                        f"decoded ({error}) and is left empty -- {ashex(data)}",
                        file=sys.stderr,
                    )
                yield record
            del data

    def enumerate_files(self, table):
        """
        Yield all file contents found in CroBank for `table`.
        This is most likely the table with id 0.
        """
        for i in range(self.bank.nrofrecords):
            data = self.readbankrec(i + 1)
            if data and data[0] == table.tableid:
                yield i + 1, data[1:]

    def readbankrec_or_raise(self, recno):
        """
        Read record `recno` from CroBank, returning None when the record is deleted.
        Raises LookupError, naming the record, when the record is corrupt.
        """
        try:
            return self.bank.readrec(recno)
        except (ValueError, struct.error) as e:
            raise LookupError(f"CroBank record {recno:d} is corrupt: {describe_error(e)}") from e

    def readbankrec(self, recno):
        """
        Read record `recno` from CroBank.
        Returns None when the record is deleted, or when it is corrupt, after printing a warning.
        """
        try:
            return self.readbankrec_or_raise(recno)
        except LookupError as e:
            print(f"Warning: {e}; skipping it", file=sys.stderr)
            return None

    @cached_property
    def files_tableid(self):
        """
        The table id of the Files table, which holds the stored files, or None when the database has no Files table.
        """
        table = next(self.enumerate_tables(files=True), None)
        return table.tableid if table else None

    def get_record(self, index, asbase64=False):
        """
        Retrieve a stored file's record from CroBank with record number `index`.
        Raises LookupError, naming the reason, when `index` is not the number of a readable record of the Files table.
        """
        try:
            recno = int(index)
        except ValueError:
            raise LookupError(f"{index!r} is not a record number") from None
        if not 1 <= recno <= self.bank.nrofrecords:
            raise LookupError(f"CroBank has no record {recno:d}")
        data = self.readbankrec_or_raise(recno)
        if data is None:
            raise LookupError(f"CroBank record {recno:d} is deleted")
        if not data or data[0] != self.files_tableid:
            raise LookupError(f"CroBank record {recno:d} is not a record of the Files table")
        if asbase64:
            return base64.b64encode(data[1:]).decode("utf-8")
        else:
            return data[1:]

    def recdump(self, args):
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
