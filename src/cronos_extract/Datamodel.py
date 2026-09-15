# ABOUTME: Decodes CronosPro table definitions, field definitions and records.
# ABOUTME: Turns raw field bytes into presentable content such as dates, times, file references and text.
# -*- coding: utf-8 -*-
import sys
from typing import override

from .hexdump import ashex, tohex
from .readers import ByteReader


class FieldDefinition:
    """
    Contains the properties for a single field in a record.
    """

    def __init__(self, data):
        self.decode(data)

    def decode(self, data):
        self.defdata = data

        rd = ByteReader(data)
        self.typ = rd.readword()
        self.idx1 = rd.readdword()
        self.name = rd.readname()
        self.flags = rd.readdword()
        self.minval = rd.readbyte()  # Always 1
        if self.typ:
            self.idx2 = rd.readdword()
            self.maxval = rd.readdword()  # max value or length
            self.unk4 = rd.readdword()  # Always 0x00000009 or 0x0001000d
        else:
            self.idx2 = 0
            self.maxval = self.unk4 = None
        self.remaining = rd.readbytes()

    @override
    def __str__(self):
        if self.typ:
            quoted_name = f"'{self.name}'"
            return (
                f"Type: {self.typ:2d} ({self.idx1:2d}/{self.idx2:2d}) "
                f"{self.flags:04x},({self.minval:d}-{self.maxval:4d}),"
                f"{self.unk4:04x} - {quoted_name:<40} -- {tohex(self.remaining)}"
            )
        else:
            return f"Type: {self.typ:2d} {self.idx1:2d}    {self.flags:d},{self.minval:d}       - '{self.name}'"

    def sqltype(self):
        return {
            0: "INTEGER PRIMARY KEY",
            1: "INTEGER",
            2: "VARCHAR(" + str(self.maxval) + ")",
            3: "TEXT",  # dictionaray
            4: "DATE",
            5: "TIMESTAMP",
            6: "TEXT",  # file reference
        }.get(self.typ, "TEXT")


class TableImage:
    def __init__(self, data):
        self.decode(data)

    def decode(self, data):
        if not len(data):
            self.filename = "none"
            self.data = b""
            return

        rd = ByteReader(data)

        _ = rd.readbyte()
        namelen = rd.readdword()
        self.filename = rd.readbytes(namelen).decode("cp1251", "ignore")

        imagelen = rd.readdword()
        self.data = rd.readbytes(imagelen)


class TableDefinition:
    def __init__(self, data, image=""):
        self.decode(data, image)

    def decode(self, data, image):
        """
        decode the 'base' / table definition
        """
        rd = ByteReader(data)

        self.unk1 = rd.readword()
        self.version = rd.readbyte()
        if self.version > 1:
            _ = rd.readbyte()  # always 0 anyway

        # if this is not 5 (but 9), there's another 4 bytes inserted, this could be a length-byte.
        self.unk2 = rd.readbyte()

        self.unk3 = rd.readbyte()
        if self.unk2 > 5:  # seen only 5 and 9 for now with 9 implying an extra dword
            _ = rd.readdword()
        self.unk4 = rd.readdword()

        self.tableid = rd.readdword()

        self.tablename = rd.readname()
        self.abbrev = rd.readname()
        self.unk7 = rd.readdword()
        nrfields = rd.readdword()

        self.headerdata = data[: rd.o]

        # There's (at least) two blocks describing fields, ended when encountering ffffffff
        self.fields = []
        for _ in range(nrfields):
            deflen = rd.readword()
            fielddef = rd.readbytes(deflen)
            self.fields.append(FieldDefinition(fielddef))

        # Between the first and the second block, there's some byte strings inbetween, count
        # given in first dword
        self.extraunkdatastrings = rd.readdword()

        for _ in range(self.extraunkdatastrings):
            datalen = rd.readword()
            rd.readbytes(datalen)

        try:
            # Then there's another unknow dword and then (probably section indicator) 02 byte
            self.unk8_ = rd.readdword()
            if rd.readbyte() != 2:
                print("Warning: FieldDefinition Section 2 not marked with a 2", file=sys.stderr)
            self.unk9 = rd.readdword()

            # Then there's the amount of extra fields in the second section
            nrextrafields = rd.readdword()

            for _ in range(nrextrafields):
                deflen = rd.readword()
                fielddef = rd.readbytes(deflen)
                self.fields.append(FieldDefinition(fielddef))
        except Exception as e:
            print(f"Warning: Error '{e}' parsing FieldDefinitions", file=sys.stderr)

        try:
            self.terminator = rd.readdword()
        except EOFError:
            print("Warning: FieldDefinition section not terminated", file=sys.stderr)
        except Exception as e:
            print(f"Warning: Error '{e}' parsing Tabledefinition", file=sys.stderr)

        self.fields.sort(key=lambda field: field.idx2)

        self.remainingdata = rd.readbytes()

        self.tableimage = TableImage(image)

    @override
    def __str__(self):
        return (
            f"{self.unk1:d},{self.version:d}<{self.unk2:d},{self.unk3:d},{self.unk4:d}>{self.tableid:d}  "
            f"{self.unk7:d},{len(self.fields):d} '{self.tablename}'  '{self.abbrev}'  "
            f"[TableImage({len(self.tableimage.data):d} bytes): {self.tableimage.filename}]"
        )

    def dump(self, args):
        if args.verbose:
            print(f"table: {tohex(self.headerdata)}")

        print(str(self))

        for i, field in enumerate(self.fields):
            if args.verbose:
                print(f"field#{i:2d}: {len(field.defdata):04x} - {tohex(field.defdata)}")
            print(str(field))
        if args.verbose:
            print(f"remaining: {tohex(self.remainingdata)}")


class Field:
    """
    Contains a single fully decoded value.
    """

    def __init__(self, fielddef, data):
        self.decode(fielddef, data)

    def decode(self, fielddef, data):
        self.typ = fielddef.typ
        self.data = data

        if not data:
            self.content = ""
            return
        elif self.typ == 0:
            # typ 0 is the recno, or as cronos calls this: Системный номер, systemnumber.
            # just convert this to string for presentation
            self.content = str(data)

        elif self.typ == 4:
            # typ 4 is DATE, formatted like: <year-1900:signedNumber><month:2digits><day:2digits>
            try:
                data = data.rstrip(b"\x00")
                y, m, d = 1900 + int(data[:-4]), int(data[-4:-2]), int(data[-2:])
                self.content = f"{y:04d}-{m:02d}-{d:02d}"
            except ValueError:
                self.content = str(data)

        elif self.typ == 5:
            # typ 5 is TIME, formatted like: <hour:2digits><minute:2digits>
            try:
                data = data.rstrip(b"\x00")
                h, m = int(data[-4:-2]), int(data[-2:])
                self.content = f"{h:02d}:{m:02d}"
            except ValueError:
                self.content = str(data)

        elif self.typ == 6:
            # decode internal file reference
            rd = ByteReader(data)
            self.flag = rd.readdword()
            self.remlen = rd.readdword()
            self.filename = rd.readtoseperator(b"\x1e").decode("cp1251", "ignore")
            self.extname = rd.readtoseperator(b"\x1e").decode("cp1251", "ignore")
            self.filedatarecord = rd.readtoseperator(b"\x1e").decode("cp1251", "ignore")
            self.content = " ".join([self.filename, self.extname, self.filedatarecord])

        elif self.typ == 7 or self.typ == 8 or self.typ == 9:
            # just hexdump foreign keys
            self.content = ashex(data)

        else:
            # currently assuming everything else to be strings, which is wrong
            self.content = data.rstrip(b"\x00").decode("cp1251", "ignore")


class Record:
    """
    Contains a single fully decoded record.
    """

    def __init__(self, recno, tabledef, data):
        self.decode(recno, tabledef, data)

    def decode(self, recno, tabledef, data):
        """
        decode the fields in a record
        """
        self.data = data
        self.recno = recno
        self.table = tabledef

        # start with the record number, or as Cronos calls this:
        # the system number, in russian: Системный номер.
        self.fields = [Field(tabledef[0], str(recno))]

        # (field name, description of the error) for every field that could not be decoded.
        # Those fields are kept with empty content, so the record still has one field per field definition.
        self.errors = []

        rd = ByteReader(data)
        for fielddef in tabledef[1:]:
            try:
                if not rd.eof() and rd.testbyte(0x1B):
                    # read complex record indicated by b"\x1b"
                    rd.readbyte()
                    size = rd.readdword()
                    fielddata = rd.readbytes(size)
                else:
                    fielddata = rd.readtoseperator(b"\x1e")
            except Exception as e:
                # Without this field's length, the start of the next field is unknown: leave the rest empty too.
                self.errors.append((fielddef.name, f"{describe_error(e)}; the fields after it are left empty too"))
                self.fields.extend(Field(emptydef, b"") for emptydef in tabledef[len(self.fields) :])
                return

            try:
                self.fields.append(Field(fielddef, fielddata))
            except Exception as e:
                self.errors.append((fielddef.name, describe_error(e)))
                self.fields.append(Field(fielddef, b""))


def describe_error(error):
    """Return the type and, when it has one, the message of `error`, such as "EOFError" or "ValueError: bad"."""
    message = str(error)
    return f"{type(error).__name__}: {message}" if message else type(error).__name__
