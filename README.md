# cronos-extract

cronos-extract parses most of the databases created by the [CronosPro](https://www.cronos.ru/) database software
and dumps them to several output formats.

The software is popular among Russian public offices, companies and police agencies.

cronos-extract is a successor to [cronodump](https://github.com/alephdata/cronodump) by Willem Hengeveld and
Dirk Engling, published by the Organized Crime and Corruption Reporting Project. It continues from cronodump's
`master` branch together with the assisted KOD recovery work from
[alephdata/cronodump#13](https://github.com/alephdata/cronodump/pull/13). The full history of the original project
is kept in this repository.


# Quick start

```bash
uv tool install git+https://github.com/hammersleyfutures/cronos-extract
cronos-extract export --csv test_data/all_field_types
```

This creates a `cronos-extract-YYYY-mm-dd-HH-MM-SS-ffffff/` directory holding a CSV file for each table, a
`Files-FL/` directory holding every file stored in the database, whether or not a record still refers to it, and,
once a record of a table with a file field is written, a `Files-Referenced/` directory holding the files the
records refer to, under their own names; it appears at that first record, even when its file field is empty.
`-o DIR` names the directory instead; it must not exist, because an export never overwrites anything.

If the export stops with an error about the database definition, or its output is unreadable, the database is
probably encrypted with its own KOD; see [Recovering the KOD](#recovering-the-kod-of-an-encrypted-database).


# Exporting

`cronos-extract export` writes every table of a database in one of three formats: `--csv`, `--postgres` or
`--jsonl`. Every problem it meets while reading, such as a corrupt record, is printed on stderr as it happens, one
line each, and the export carries on. The last line of stderr counts them by kind:

```
warning: corrupt_record: CroBank.dat record 88: CroBank record 88 is corrupt and is skipped: EOFError

1 diagnostic: 1 corrupt_record
```

The export exits with status 0 when it finished, whatever it reported; with 1 when the database cannot be read at
all, with one `Error:` line last on stderr; and with 2 for a mistake in the command. `--strict` makes it exit 1 when
anything was reported, after writing the whole export. The databases in `test_data` report that their table
definitions are laid out unexpectedly, so `--strict` exits 1 for them.

Write the PostgreSQL and JSON Lines exports to a file with `-o FILE`, which must not exist, rather than to a
terminal: a database's names and values can hold characters that a terminal interprets. stderr is safe: everything
the command prints there is escaped.

## CSV

`--csv` creates a directory holding `<table name>.csv` for each table, UTF-8 without a byte order mark. The first row
holds the field names, starting with the system number. `--delimiter ';'` changes the delimiter, and `--no-files`
leaves out the two file directories. Names have the characters no file system allows, and path separators, replaced
with underscores; they are unique within the directory and at most 255 bytes long.

The cells hold exactly what the database holds, including text that a spreadsheet reads as a formula. Open a CSV
file through the spreadsheet's CSV import, as UTF-8, never by double-clicking it.

## PostgreSQL

`--postgres` writes a `CREATE TABLE` statement per table and an `INSERT` statement per record. Every column is
declared `TEXT`, the system number included, so every record loads even when a value does not match its field type.
Values are written exactly as they are decoded: dates as `YYYY-MM-DD`, times as `HH:MM`, and empty values as `NULL`.
Cast columns in SQL when you need types, for example `"Entry #4"::date`. The output starts with
`SET standard_conforming_strings = on;`, so its string literals load correctly whatever the server's setting.
PostgreSQL text cannot hold a NUL character, so a NUL in a value is written as U+FFFD and reported as `replaced_nul`.
Stored files are not included; use `--csv` for them.

## JSON Lines

`--jsonl` writes one JSON object per line: a `table` line before the table's records, a `record` line per record,
and a `diagnostic` line for each problem, where it happened, so a script can tell which records had problems
without reading stderr.

```json
{"type": "table", "table": "Люди", "table_id": 1, "abbreviation": "ЛЮ", "fields": [{"name": "Системный номер", "type": 0}, {"name": "ФИО", "type": 2}]}
{"type": "record", "table": "Люди", "table_id": 1, "record": 12, "fields": [{"name": "Системный номер", "value": "3"}, {"name": "ФИО", "value": "Иванов"}]}
{"type": "diagnostic", "kind": "invalid_value", "message": "the value is not a date; it is kept as text", "file": "CroBank.dat", "table": "Люди", "record": 13, "field": "Дата"}
```

Each record line names its table and its fields, in the order the table defines them, so it can be read on its own.
A field's `value` is `null` when the field is empty, a date as `"1985-04-02"` (or `"1985-00-00"` when only the year is
stored), a time as `"14:30"`, `{"name": …, "extension": …, "record": …}` for a stored file, and otherwise the text.
Stored files are not included; use `--csv` for them.

```bash
cronos-extract export --jsonl -o people.jsonl test_data/all_field_types
jq -r 'select(.type == "record") | .fields[] | select(.name == "Entry #1") | .value' people.jsonl
```

## Large databases

`--compact` reads the indexes from disk instead of memory. Use it for a very large database, whose CroBank index can
take gigabytes of memory; it is about 15% slower.


# Surveying databases

Before exporting anything, `cronos-extract survey` reports which CronosPro version each database uses. It reads only
the 19-byte header of every `Cro*.dat` file: no records, no file contents.

```bash
cronos-extract survey /path/to/databases            # a block per database
cronos-extract survey --counts /path/to/databases   # totals only, naming no directories
cronos-extract survey --jsonl /path/to/databases    # one JSON object per database, for scripts
```

`--counts` totals the files found for each version and generation, and ends with an `unreadable files: N` line when
any header could not be read.

To survey databases kept in several places, name them in a text file, one path per line, and survey them as one
group. Blank lines and lines starting with `#` are ignored, and a relative path is taken from the current
directory. A path that is no longer a directory, and a directory that cannot be listed, are each reported on stderr
and skipped. A database found under two of the paths is reported once.

```bash
cronos-extract survey --list /path/to/list.txt --counts
```

Versions `01.02`–`01.05` are v3, `01.11`, `01.13` and `01.14` are v4, and `01.19` is v7. The survey reports whichever
version it finds, including v7 and versions it does not recognise. The export and inspection commands read v3 and v4,
and do not read v7 yet.


# Inspection

`cronos-extract inspect` shows what the export hides, for studying the file format. Some experience with binary
dumps helps: not all of the format is understood yet. It prints the database's names and bytes to stdout
unescaped, so write it to a file or pipe it into a pager rather than a terminal when the database is untrusted.

```bash
cronos-extract inspect strudump -v -a test_data/all_field_types   # the database and table definitions, as text
cronos-extract inspect crodump -v test_data/all_field_types        # every Cro file, byte range by byte range
cronos-extract inspect recdump test_data/all_field_types           # a hexdump of every CroBank record
```

`recdump --stru`, `--index` or `--sys` dumps that file's records instead. `destruct` decodes a definition given as
hex on stdin, and `kodump` KOD-decodes a byte range of any file. Each takes `--help`.


# Recovering the KOD of an encrypted database

CronosPro can protect a database with a password, which encrypts it with its own KOD table in place of the default
one. `cronos-extract crack` recovers that KOD from the encrypted records without the password. Both methods are
statistical and may not find every entry.

`crack dbcrack` reads the fourth byte of the CroBank and CroIndex records, which decodes to zero when a record is
compressed:

```bash
KOD=$(cronos-extract crack dbcrack --silent /path/to/database)
cronos-extract export --csv --kod "$KOD" /path/to/database
```

`crack strucrack` reads CroStru, most of whose bytes are zero. When it cannot resolve every entry, it shows the
records as far as it can decode them, suggests `-f` switches where it recognises known text, and prints the missing
entries and its estimate on stderr. Add the switches, or `--text record:line:offset:plaintext` for text you can read,
and run it again until it prints the KOD:

```bash
cronos-extract crack strucrack /path/to/database
cronos-extract crack strucrack -f f103=B -f f10342 /path/to/database
```

`export --crack dbcrack` or `--crack strucrack` recovers the KOD first and exports with it in one step, and exits 1
when the method cannot.


# Python API

cronos-extract is also a library. The command line is being rebuilt on it.

```python
import cronos_extract

with cronos_extract.open("path/to/database") as bank:
    for table in bank.tables:
        for record in table.records():
            print(record["Entry #4"].value)
    print(bank.diagnostic_counts)
```

`open` takes `kod=` (a `cronos_extract.Kod`, or `None` to read without KOD decoding), `compact=True` for very large
databases, and `on_diagnostic=` for a function to call with each problem found while reading. The library never
prints: records it cannot read are skipped and reported as diagnostics, and a database it cannot read at all raises
a `cronos_extract.CronosError`. `cronos_extract.crack_kod(path, "strucrack")` or `"dbcrack"` recovers the KOD of a
database encrypted with its own. The module docstring (`help(cronos_extract)`) lists what the API promises.


# Installing

cronos-extract requires Python 3.12 or later and has no other dependencies.

 * Install the `cronos-extract` command with `uv tool install git+https://github.com/hammersleyfutures/cronos-extract`.
 * Or run it from a clone of this repository with `uv run cronos-extract ...`.


# Development

```bash
uv sync                      # create the virtual environment with the dev tools
uv run pre-commit install    # lint, format, type-check and test before each commit
uv run pytest -q             # run the tests
uv run ruff check && uv run ruff format --check && uv run ty check
```

The characterisation tests in `tests/test_cli_characterisation.py` compare command output with the files in
`tests/golden/`. After a deliberate output change, run `uv run pytest --update-golden` and review the diff of the
golden files before committing.


# Terminology

We decided to use the more common terminology for database, tables, records, etc.
Here is a table showing how cronos calls these:

| what | cronos english | cronos russian
|:------ |:------ |:------ 
| Database  |  Bank   | Банк 
| Table     |  Base   | Базы
| Record    |  Record | Записи
| Field     |  Field  | поля
| recid     |  System Number | Системный номер


# License

cronos-extract is released under the [MIT license](LICENSE), which retains the copyright notice of the original
cronodump project.


# References

cronodump built upon [documentation of the file format found in older versions of Cronos](http://sergsv.narod.ru/cronos.htm) and
the [subsequent implementation of a parser for the old file format](https://github.com/occrp/cronosparser) but dropped the heuristic
approach to guess offsets and obfuscation parameters for a more rigid parser. Refer to [the docs](docs/cronos-research.md) for further
details.
