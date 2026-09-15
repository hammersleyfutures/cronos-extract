# ABOUTME: Database: opens the Cro*.dat/.tad file pairs found in a CronosPro database directory.
# ABOUTME: Decodes the database and table definitions from CroStru and enumerates tables, records and files.
import base64
import os
import re
import struct
import sys
from binascii import b2a_hex
from contextlib import ExitStack

from . import koddecoder
from .Datafile import Datafile
from .Datamodel import Record, TableDefinition, describe_error
from .hexdump import ashex, strescape, toout
from .readers import ByteReader


class Database:
    """represent the entire database, consisting of Stru, Index and Bank files"""

    # The number of records enumerate_records yielded with fields that could not be decoded.
    incomplete_records = 0

    def __init__(self, dbdir, compact, kod=koddecoder.new()):
        """
        `dbdir` is the directory containing the Cro*.dat and Cro*.tad files.
        `compact` if set, the .tad file is not cached in memory, making dumps 15 % slower
        `kod` is optionally a KOD coder object.
              by default the v3 KOD coding will be used.
        """
        self.dbdir = dbdir
        self.compact = compact
        self.kod = kod

        # Stru+Index+Bank for the components for most databases
        self.stru = self.getfile("Stru")
        self.index = self.getfile("Index")
        self.bank = self.getfile("Bank")

        # the Sys file resides in the "Program Files\Cronos" directory, and
        # contains an index of all known databases.
        self.sys = self.getfile("Sys")

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
        When no such files exist, or only one, then None is returned.

        `name` is matched case insensitively
        """
        try:
            datname = self.getname(name, "dat")
            tadname = self.getname(name, "tad")
            if datname and tadname:
                return self.opendatafile(name, datname, tadname)
        except OSError:
            return

    def opendatafile(self, name, datname, tadname):
        """
        Open a .dat/.tad pair as a Datafile, closing both files again if it can't be read.
        """
        with ExitStack() as stack:
            dat = stack.enter_context(open(datname, "rb"))
            tad = stack.enter_context(open(tadname, "rb"))
            datafile = Datafile(name, dat, tad, self.compact, self.kod)
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

    def strudump(self, args):
        """
        prints all info found in the CroStru file.
        """
        if not self.stru:
            sys.exit(f"Error: {self.missing_stru_message()}")
        self.dump_db_table_defs(args)

    def missing_stru_message(self):
        """
        Returns the message that explains that the database directory has no CroStru files.
        """
        return f"no CroStru.dat and CroStru.tad found in {self.dbdir}, which hold the table definitions"

    def decode_db_definition(self, data):
        """
        decode the 'bank' / database definition
        """
        rd = ByteReader(data)

        d = dict()
        while not rd.eof():
            keyname = rd.readname()
            if keyname in d:
                print(f"WARN: duplicate key: {keyname}", file=sys.stderr)

            index_or_length = rd.readdword()
            if index_or_length >> 31:
                d[keyname] = rd.readbytes(index_or_length & 0x7FFFFFFF)
            else:
                refdata = self.stru.readrec(index_or_length)
                if refdata[:1] != b"\x04":
                    print("WARN: expected refdata to start with 0x04", file=sys.stderr)
                d[keyname] = refdata[1:]
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

    def dump_db_table_defs(self, args):
        """
        decode the table defs from recid #1, which always has table-id #3
        Note that I don't know if it is better to refer to this by recid, or by table-id.

        other table-id's found in CroStru:
            #4  -> large values referenced from tableid#3
        """
        dbinfo = self.stru.readrec(1)
        if dbinfo[:1] != b"\x03":
            print("WARN: expected dbinfo to start with 0x03", file=sys.stderr)
        dbdef = self.decode_db_definition(dbinfo[1:])
        self.dump_db_definition(args, dbdef)

        for k, v in dbdef.items():
            if k.startswith("Base") and k[4:].isnumeric():
                print(f"== {k} ==")
                tbdef = TableDefinition(v, dbdef.get("BaseImage" + k[4:], b""))
                tbdef.dump(args)
            elif k == "NS1":
                self.dump_ns1(v)

    def dump_ns1(self, data):
        if len(data) < 2:
            print("NS1 is unexpectedly short", file=sys.stderr)
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
            print("NS1 is unexpectedly short", file=sys.stderr)
            return
        (
            serial,
            unk2,
            pwlen,
        ) = struct.unpack_from("<LLL", decoded_data, 0)
        password = decoded_data[12 : 12 + pwlen].decode("cp1251")

        print(f"== NS1: ({unk1:02x},{sh:02x}) -> {serial:6d}, {unk2:d}, {pwlen:d}:'{password}'")

    def enumerate_tables(self, files=False):
        """
        yields a TableDefinition object for all `BaseNNN` entries found in CroStru
        """
        if not self.stru:
            raise FileNotFoundError(self.missing_stru_message())
        dbinfo = self.stru.readrec(1)
        if dbinfo[:1] != b"\x03":
            print("WARN: expected dbinfo to start with 0x03", file=sys.stderr)
        try:
            dbdef = self.decode_db_definition(dbinfo[1:])
        except Exception as e:
            print(f"ERROR decoding db definition: {e}", file=sys.stderr)
            print(
                "This could possibly mean that you need to try     crodump strucrack     "
                "to deduct the database key first",
                file=sys.stderr,
            )
            return

        for k, v in dbdef.items():
            if k.startswith("Base") and k[4:].isnumeric():
                if files and k[4:] == "000":
                    yield TableDefinition(v)
                if not files and k[4:] != "000":
                    yield TableDefinition(v, dbdef.get("BaseImage" + k[4:], b""))

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

    def readbankrec(self, recno):
        """
        Read record `recno` from CroBank.
        Returns None when the record is deleted, or when it is corrupt, after printing a warning.
        """
        try:
            return self.bank.readrec(recno)
        except (ValueError, struct.error) as e:
            print(f"Warning: skipping CroBank record {recno:d}, which is corrupt: {describe_error(e)}", file=sys.stderr)
            return None

    def get_record(self, index, asbase64=False):
        """
        Retrieve a single record from CroBank with record number `index`.
        Returns None when `index` is not the number of a record in CroBank, or that record is deleted.
        """
        try:
            recno = int(index)
        except ValueError:
            return None
        if not 1 <= recno <= self.bank.nrofrecords:
            return None
        data = self.readbankrec(recno)
        if data is None:
            return None
        if asbase64:
            return base64.b64encode(data[1:]).decode("utf-8")
        else:
            return data[1:]

    def recdump(self, args):
        """
        Function for outputing record contents of the various .dat files.

        This function is mostly useful for reverse-engineering the database format.
        """
        if args.index:
            dbfile = self.index
        elif args.sys:
            dbfile = self.sys
        elif args.stru:
            dbfile = self.stru
        else:
            dbfile = self.bank

        if not dbfile:
            print(".dat not found", file=sys.stderr)
            return
        nerr = 0
        nr_recnone = 0
        nr_recempty = 0
        tabidxref = [0] * 256
        bytexref = [0] * 256
        for i in range(1, args.maxrecs + 1):
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
            except IndexError:
                break
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
