# ABOUTME: croconvert command: converts a CronosPro database to CSV files or to Jinja2 template output.
# ABOUTME: Selects the KOD table from --kod, --nokod, --strucrack or --dbcrack before converting.
"""
Commandline tool which convert a cronos database to .csv, .sql or .html.

python3 croconvert.py -t html chechnya_proverki_ul_2012/
"""

import base64
import csv
import re
import sys
from datetime import datetime
from itertools import chain, count
from os import chdir, mkdir
from os.path import abspath, dirname, join
from sys import exit, stdout

from .crodump import CRACK_FAILED_MESSAGE, crack_kod
from .Database import Database
from .hexdump import unhex


def referenced_file(db, tablename, recno, field, asbase64=False):
    """
    Return the content of the stored file that the file reference `field` of record `recno` refers to.
    Prints a warning and returns None when that file can't be read, so the export can skip it.
    """
    try:
        return db.get_record(field.filedatarecord, asbase64)
    except LookupError as e:
        print(
            f'Warning: skipping file "{field.filename}.{field.extname}" of record {recno} in table "{tablename}": {e}',
            file=sys.stderr,
        )
        return None


def open_database(kod, args):
    """Open the database in args.dbdir, exiting with an error message when it has no CroStru files."""
    db = Database(args.dbdir, args.compact, kod)
    if not db.stru:
        db.close()
        exit(f"Error: {db.missing_stru_message()}")
    return db


def report_incomplete_records(db):
    """Print how many records had fields that could not be decoded, when there were any."""
    if db.incomplete_records:
        records = "record" if db.incomplete_records == 1 else "records"
        print(
            f"Warning: {db.incomplete_records} {records} had fields that could not be decoded; "
            "those fields are empty in the output",
            file=sys.stderr,
        )


def template_convert(kod, args):
    """looks up template to convert to, parses the database and passes it to jinja2"""
    try:
        from jinja2 import Environment, FileSystemLoader
    except ImportError:
        exit("Fatal: Jinja templating engine not found. Install using pip install jinja2")

    template_dir = join(dirname(abspath(__file__)), "templates")
    # Only HTML output is escaped; SQL output quotes its values itself and must not contain HTML entities.
    j2_env = Environment(loader=FileSystemLoader(template_dir), autoescape=lambda name: name == "html.j2")
    j2_templ = j2_env.get_template(args.template + ".j2")
    with open_database(kod, args) as db:
        stdout.writelines(
            j2_templ.generate(
                db=db,
                base64=base64,
                referenced_file=referenced_file,
                unique_sql_table_name=unique_sql_table_name,
                unique_sql_column_names=unique_sql_column_names,
                sql_value=sql_value,
            )
        )
        report_incomplete_records(db)


def safepathname(name):
    """Replace the characters that can't appear in a file name on Linux, macOS or Windows with underscores."""
    return re.sub(r'[\x00-\x1f<>:"/\\|?*]', "_", name)


# The longest file name, in bytes, that Linux, macOS and Windows file systems accept.
MAX_FILE_NAME_BYTES = 255
# The longest file name extension kept in full, in bytes, dot included.
MAX_EXTENSION_BYTES = 64
# The longest identifier, in bytes, that PostgreSQL keeps without truncating it.
POSTGRES_IDENTIFIER_BYTES = 63


def truncate_utf8(text, max_bytes):
    """Return the longest start of `text` that is at most `max_bytes` long in UTF-8, cut at a character boundary."""
    return text.encode("utf-8")[:max_bytes].decode("utf-8", "ignore")


def unique_name(stem, extension, number, used_names, max_bytes):
    """
    Return `stem` followed by `extension` when no other output uses that name, or None when the thing
    numbered `number` already has it. A name already used by something else gets "-<number>" appended
    to its stem, and a counter after that if needed. The stem is shortened so that the whole name fits
    in `max_bytes` UTF-8 bytes.
    `used_names` maps each name given so far, compared case-insensitively, to its number.
    """
    for suffix in chain(["", f"-{number}"], (f"-{number}-{n}" for n in count(2))):
        room = max_bytes - len(suffix.encode("utf-8")) - len(extension.encode("utf-8"))
        name = truncate_utf8(stem, room) + suffix + extension
        key = name.casefold()
        if key not in used_names:
            used_names[key] = number
            return name
        if used_names[key] == number:
            return None


def unique_file_name(stem, extension, number, used_names):
    """
    Return a file name made from `stem` and `extension` that no other output file uses, or None when
    the thing numbered `number` already has a file.

    `stem` and `extension` are made safe with safepathname, and a stem that is empty or only dots is
    replaced by `number`. The extension is cut to MAX_EXTENSION_BYTES and the stem is shortened so that
    the name fits in MAX_FILE_NAME_BYTES. See unique_name for how names are kept unique.
    """
    stem = safepathname(stem)
    if not stem.strip("."):
        stem = str(number)
    extension = truncate_utf8("." + safepathname(extension), MAX_EXTENSION_BYTES) if extension else ""
    return unique_name(stem, extension, number, used_names, MAX_FILE_NAME_BYTES)


def unique_sql_table_name(table, used_names):
    """
    Return the name to give `table` in SQL output, or None when a table with the same name and table id
    is already written. Double quotes become underscores, an empty name becomes the table id, and the name
    fits in POSTGRES_IDENTIFIER_BYTES. See unique_name for how names are kept unique.
    """
    name = table.tablename.replace('"', "_") or str(table.tableid)
    return unique_name(name, "", table.tableid, used_names, POSTGRES_IDENTIFIER_BYTES)


def unique_sql_column_names(table):
    """
    Return the names to give the columns of `table` in SQL output, in the order of its fields.
    Double quotes become underscores, an empty name becomes the column number, counting the system number
    as column 0, and every name is unique within the table and fits in POSTGRES_IDENTIFIER_BYTES.
    See unique_name for how names are kept unique.
    """
    used_names = {}
    return [
        unique_name(field.name.replace('"', "_") or str(number), "", number, used_names, POSTGRES_IDENTIFIER_BYTES)
        for number, field in enumerate(table.fields)
    ]


def sql_value(fielddef, field):
    """
    Return the content of `field` as a PostgreSQL literal for a column defined by `fielddef`.
    An empty value is NULL in a column that is not text, where '' is not a valid value.
    Single quotes are doubled, which is correct with standard_conforming_strings on.
    """
    if not field.content and not fielddef.sqltype().startswith(("TEXT", "VARCHAR")):
        return "NULL"
    return "'" + field.content.replace("'", "''") + "'"


def csv_output(kod, args):
    """creates a directory with the current timestamp and in it a set of CSV or TSV
    files with all the tables found and an extra directory with all the files"""
    with open_database(kod, args) as db:
        mkdir(args.outputdir)
        chdir(args.outputdir)

        filereferences = []

        # first dump all non-file tables
        table_names = {}
        for table in db.enumerate_tables(files=False):
            tablesafename = unique_file_name(table.tablename, "csv", table.tableid, table_names)
            if tablesafename is None:
                # a table with this name and table id is already written, and would hold the same records
                continue

            with open(tablesafename, "w", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile, delimiter=args.delimiter, escapechar="\\")
                writer.writerow([field.name for field in table.fields])

                # Record should be iterable over its fields, so we could use writerows
                for record in db.enumerate_records(table):
                    writer.writerow([field.content for field in record.fields])

                    filereferences.extend(
                        [(table.tablename, record.recno, field) for field in record.fields if field.typ == 6]
                    )

        if args.nofiles:
            report_incomplete_records(db)
            return

        # Write all files from the file table. This is useful for unreferenced files
        for table in db.enumerate_tables(files=True):
            filedir = "Files-" + safepathname(table.abbrev)
            mkdir(filedir)

            for system_number, content in db.enumerate_files(table):
                with open(join(filedir, str(system_number)), "wb") as binfile:
                    binfile.write(content)

        if len(filereferences):
            filedir = "Files-Referenced"
            mkdir(filedir)

        # Write all referenced files with their filename and extension intact, as far as that is safe and unique
        referenced_names = {}
        for tablename, recno, reffile in filereferences:
            if reffile.content:  # only print when file is not NULL
                content = referenced_file(db, tablename, recno, reffile)
                if content is None:
                    continue
                filesafename = unique_file_name(
                    reffile.filename, reffile.extname, int(reffile.filedatarecord), referenced_names
                )
                if filesafename is None:
                    continue
                with open(join("Files-Referenced", filesafename), "wb") as binfile:
                    binfile.write(content)

        report_incomplete_records(db)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="CRONOS database converter")
    parser.add_argument("--template", "-t", type=str, default="html", help="output template to use for conversion")
    parser.add_argument("--csv", "-c", action="store_true", help="create output in .csv format")
    parser.add_argument("--delimiter", "-d", default=",", help="delimiter used in csv output")
    parser.add_argument("--outputdir", "-o", type=str, help="directory to create the dump in")
    parser.add_argument("--kod", type=str, help="specify custom KOD table")
    parser.add_argument(
        "--compact",
        action="store_true",
        help="save memory by not caching the index, note: increases convert time by factor 1.15",
    )
    parser.add_argument("--strucrack", action="store_true", help="infer the KOD sbox from CroStru.dat")
    parser.add_argument("--dbcrack", action="store_true", help="infer the KOD sbox from CroIndex.dat+CroBank.dat")
    parser.add_argument("--nokod", "-n", action="store_true", help="don't KOD decode")
    parser.add_argument("--nofiles", "-F", action="store_true", help="don't export files with .csv export")
    parser.add_argument("dbdir", type=str)
    args = parser.parse_args()

    from . import koddecoder

    if args.kod:
        if len(args.kod) != 512:
            raise Exception("--kod should have a 512 hex digit argument")
        kod = koddecoder.new(list(unhex(args.kod)))
    elif args.nokod:
        kod = None
    elif args.strucrack or args.dbcrack:
        cracked = crack_kod("strucrack" if args.strucrack else "dbcrack", args.dbdir, args.compact)
        if not cracked:
            exit(CRACK_FAILED_MESSAGE)
        kod = koddecoder.new(cracked)
    else:
        kod = koddecoder.new()

    if args.csv:
        if not args.outputdir:
            args.outputdir = "cronodump" + datetime.now().strftime("-%Y-%m-%d-%H-%M-%S-%f")
        csv_output(kod, args)
    else:
        template_convert(kod, args)


if __name__ == "__main__":
    main()
