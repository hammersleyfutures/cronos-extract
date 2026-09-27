# cronos-extract

cronos-extract reads most databases of the [CronosPro](https://www.cronos.ru/) database software. It exports their
tables to CSV, PostgreSQL or JSON Lines. It also shows their internal structures, and it recovers the KOD of an
encrypted database.

CronosPro is popular among Russian public offices, companies and police agencies.

cronos-extract continues [cronodump](https://github.com/alephdata/cronodump) by Willem Hengeveld and Dirk Engling.
The Organized Crime and Corruption Reporting Project (OCCRP) published cronodump. cronos-extract starts from the
`master` branch of cronodump, together with the assisted KOD recovery of
[alephdata/cronodump#13](https://github.com/alephdata/cronodump/pull/13). This repository keeps the full history of
cronodump. The [changelog](https://github.com/hammersleyfutures/cronos-extract/blob/main/CHANGELOG.md) tells what is
different in cronos-extract.


## Install

cronos-extract needs Python 3.12 or later. It has no other dependencies. The package on PyPI is `cronos-extract`.

To install the `cronos-extract` command, use one of these commands:

- With uv: `uv tool install cronos-extract`
- With pipx: `pipx install cronos-extract`
- With pip, in a virtual environment: `pip install cronos-extract`

To make sure that the command is installed, show its version:

```bash
cronos-extract --version
```

The command prints its name and version, for example `cronos-extract 1.0.0`.

In a clone of this repository, you can use `uv run cronos-extract` in place of `cronos-extract`. The examples that
name `test_data` use the test database of the repository. They work only in a clone.


## Quick start

To export each table of the test database to a CSV file, use this command:

```bash
cronos-extract export --csv test_data/all_field_types
```

The command creates the directory `cronos-extract-YYYY-mm-dd-HH-MM-SS-ffffff/` in the current directory. This
directory holds:

- A CSV file for each table.
- `Files-<abbreviation>/` (the Files table's abbreviation, `Files-FL/` for the test database), with each file that
  the database stores. This includes the files that no record refers to.
- `Files-Referenced/`, with the files that the records refer to, under their own names.

`Files-Referenced/` appears at the first record of a table with a file field. It also appears for a record whose
file field is empty.

To give the directory a different name, use `-o DIR`. The directory must not exist, because the export never
overwrites a file or a directory.

If the export stops with an error about the database definition or the KOD, the database is probably encrypted with
its own KOD. If the output is unreadable, the same is probably true. In both cases, refer to "Recover the KOD of an
encrypted database" below.


## Export

`cronos-extract export` writes every table of a database in one of three formats: `--csv`, `--postgres` or
`--jsonl`.

### Diagnostics

The export continues after each problem that it survives, for example a corrupt record. For each such problem, it
writes one `warning:` line on stderr at the time that the problem occurs. This line is a diagnostic. The last line
of stderr gives the number of diagnostics of each kind:

```text
warning: corrupt_record: CroBank.dat record 88: CroBank record 88 is corrupt and is skipped: EOFError

1 diagnostic: 1 corrupt_record
```

The export keeps a compressed record whose CRC-32 does not agree with its data. It reports this record as
`checksum_mismatch`. If a record decompresses to more than 256 MiB, the export skips it and reports it as
`corrupt_record`.

The `.tad` file of CroBank can list deleted records. The export does not write deleted records. It writes one
`note:` line with their number on stderr, before the first table:

```text
note: CroBank.tad lists 85 deleted records, which are not exported; inspect crodump shows what remains of them
```

This note is not a diagnostic, and it does not change the exit status.

### Exit status

The export exits with one of these statuses:

- 0: The export is complete, with or without diagnostics.
- 1: The export failed, for example because it cannot read the database. The last line on stderr is one `Error:`
  line.
- 2: The options or arguments are not correct, or the output exists already.
- 130: The export stopped because you pressed Ctrl-C.

If the export stops after it created its output, the `Error:` line tells where the partial output is.

If the export gets `--strict` and reports a diagnostic, it exits with 1. It writes all of the output first. The test
database reports that its table definitions have an unexpected layout. Thus `--strict` exits with 1 for it:

```bash
cronos-extract export --csv --strict -o strict test_data/all_field_types   # exits 1, because of the diagnostics
```

The header of a v4 Cro file shows when a KOD is not the KOD of the database. If the header rejects the KOD, the
export stops and exits with 1. Its `Error:` line names the `export --crack` method that can recover the correct KOD.
If the database definition cannot be decoded, the `Error:` line names `cronos-extract crack strucrack`.

### Terminal safety

The names and values of a database can hold characters that a terminal interprets. For this reason, do not write
the PostgreSQL or JSON Lines export to a terminal. Write it to a file with `-o FILE`. The file must not exist.

The command escapes all text that it writes on stderr. Thus stderr is safe for a terminal.

### CSV

`--csv` creates a directory with one `<table name>.csv` file for each table. The files are UTF-8 without a byte order
mark. The first row holds the field names. The first field is the system number.

`--delimiter ';'` sets a different delimiter. The default delimiter is a comma. `--no-files` does not write the two
file directories.

In a file name, the export replaces path separators with underscores. It also replaces the characters that no file
system accepts. Each file name is unique in the directory and at most 255 bytes long.

The cells hold exactly what the database holds. This includes text that a spreadsheet reads as a formula.

Open a CSV file with the CSV import of the spreadsheet, as UTF-8. Do not open it with a double-click.

### PostgreSQL

`--postgres` writes a `CREATE TABLE` statement for each table and an `INSERT` statement for each record. Each column
has the type `TEXT`, the system number included. Thus every record loads, also a record with a value that does not
agree with its field type.

The export writes each value as it decodes it: dates as `YYYY-MM-DD`, times as `HH:MM`, and empty values as `NULL`.
If you need types, cast the columns in SQL, for example `"Entry #4"::date`.

The output starts with `SET standard_conforming_strings = on;`. Thus its string literals load correctly with each
setting of the server. PostgreSQL text cannot hold a NUL character. The export writes a NUL in a value as U+FFFD and
reports it as `replaced_nul`.

The PostgreSQL export does not include the stored files. Use `--csv` for them.

### JSON Lines

`--jsonl` writes one JSON object on each line:

- A `table` line before the records of each table.
- A `record` line for each record.
- A `diagnostic` line for each diagnostic, at the position where it occurred.
- A `deleted_records` line before the first table, with the number of deleted records that CroBank lists.

If CroBank lists no deleted records, the `deleted_records` line is not there.

Thus a script can find the records with diagnostics. It does not have to read stderr.

```json
{"type": "table", "table": "Люди", "table_id": 1, "abbreviation": "ЛЮ", "fields": [{"name": "Системный номер", "type": 0}, {"name": "ФИО", "type": 2}]}
{"type": "record", "table": "Люди", "table_id": 1, "record": 12, "fields": [{"name": "Системный номер", "value": "3"}, {"name": "ФИО", "value": "Иванов"}]}
{"type": "diagnostic", "kind": "invalid_value", "message": "the value is not a date; it is kept as text", "file": "CroBank.dat", "table": "Люди", "record": 13, "field": "Дата"}
```

Each record line names its table and its fields, in the order that the table defines them. Thus you can read each
line alone. The `value` of a field is one of these:

- `null` for an empty field.
- A date as `"1985-04-02"`. A date with only its year is `"1985-00-00"`.
- A time as `"14:30"`.
- `{"name": …, "extension": …, "record": …}` for a stored file.
- The text of the field for all other fields.

The JSON Lines export does not include the stored files. Use `--csv` for them.

```bash
cronos-extract export --jsonl -o people.jsonl test_data/all_field_types
jq -r 'select(.type == "record") | .fields[] | select(.name == "Entry #1") | .value' people.jsonl
```

### Large databases

The `.tad` files of a very large database can use gigabytes of memory. `--compact` reads the `.tad` files of CroStru
and CroBank from the disk, in place of memory. With `--compact`, the export is approximately 15% slower. Use
`--compact` for a very large database.


## Survey

`cronos-extract survey` tells which CronosPro version each database uses. It reads only the 19-byte header of each
`Cro*.dat` file. It does not read records or file contents. Thus you can survey databases before you export them.

```bash
cronos-extract survey /path/to/databases            # a block of text for each database
cronos-extract survey --counts /path/to/databases   # totals only, with no directory names
cronos-extract survey --jsonl /path/to/databases    # one JSON object for each database, for scripts
```

`--counts` gives the number of files of each version and generation. If the survey cannot read a header, `--counts`
also gives an `unreadable files: N` line at the end.

To survey databases in different directories as one group, do these steps:

1. Write the paths of the directories in a text file, one path on each line.
2. Give this file to `survey` with `--list`.

```bash
cronos-extract survey --list /path/to/list.txt --counts
```

The survey ignores blank lines and lines that start with `#`. A relative path starts from the current directory. If
a path is not a directory, the survey reports it on stderr and skips it. It does the same for a directory that it
cannot list. The survey reports a database under two of the paths only one time.

Versions `01.02` to `01.05` are v3. Versions `01.11`, `01.13` and `01.14` are v4. Version `01.19` is v7. The survey
reports each version that it finds, also v7 and the versions that it does not know. The `export` and `inspect`
commands read v3 and v4, but not v7.


## Inspect

`cronos-extract inspect` shows what the export does not show, for a study of the file format. Experience with binary
dumps is helpful, because some parts of the format are not known.

The `inspect` subcommands write the names and bytes of the database to stdout without escapes. If the database is
untrusted, write their output to a file or to a pager. Do not write it to a terminal.

```bash
cronos-extract inspect strudump -v -a test_data/all_field_types   # the database and table definitions, as text
cronos-extract inspect crodump -v test_data/all_field_types        # each Cro file, one byte range after the other
cronos-extract inspect recdump test_data/all_field_types           # a hexdump of each CroBank record
```

`recdump --stru`, `--index` or `--sys` dumps the records of that file in place of CroBank. `destruct` decodes a
definition that it gets as hex on stdin. `kodump` KOD-decodes a byte range of a file. Each subcommand shows its
options with `--help`.


## Recover the KOD of an encrypted database

CronosPro can protect a database with a password. The database is then encrypted with its own KOD, in place of the
default KOD. `cronos-extract crack` recovers this KOD from the encrypted records, without the password. Its two
methods are statistical. They do not always find every entry of the KOD.

### dbcrack

`crack dbcrack` reads the fourth byte of the CroBank and CroIndex records. This byte decodes to zero in a compressed
record. With `--silent`, dbcrack prints only the KOD. If dbcrack cannot find every entry, it exits with 1.

```bash
KOD=$(cronos-extract crack dbcrack --silent /path/to/database)
cronos-extract export --csv --kod "$KOD" /path/to/database
```

### strucrack

`crack strucrack` reads CroStru, because most bytes of CroStru are zero. If strucrack cannot find every entry, it
shows the records as far as it can decode them. It suggests `-f` switches where it recognizes known text. Then it
writes the missing entries and its estimate of the KOD on stderr.

To find the missing entries, do these steps:

1. Add the suggested `-f` switches to the command.
2. If you can read text in a record, add `--text record:line:offset:plaintext` for this text.
3. Run strucrack again.
4. If strucrack does not print the KOD, do steps 1 to 3 again.

```bash
cronos-extract crack strucrack /path/to/database
cronos-extract crack strucrack -f f103=B -f f10342 /path/to/database
```

If strucrack gets `--noninteractive` and cannot find every entry, it exits with 1. Without `--noninteractive`, it
exits with 0 in this case.

### The KOD options

`--kod HEX` gives the KOD as 512 hex digits. cronos-extract uses this KOD only for a file that is encrypted with its
own KOD. These files are versions `01.04`, `01.05` and all v4 versions. `--nokod` reads the records without KOD
decoding.

`export --crack dbcrack` or `export --crack strucrack` recovers the KOD and exports with it in one step. If the method
cannot recover the KOD, the export exits with 1. The `strudump`, `recdump` and `crodump` subcommands of `inspect` also
take `--crack`.


## Python library

cronos-extract is also a Python library. The `export` command uses this library.

```python
import cronos_extract

with cronos_extract.open("path/to/database") as bank:
    for table in bank.tables:
        for record in table.records():
            print(record["Entry #4"].value)
    print(bank.diagnostic_counts)
```

`open()` takes `kod=` (a `cronos_extract.Kod`, or `None` for no KOD decoding), `compact=True` for very large
databases, and `on_diagnostic=`. `on_diagnostic` is a function that receives each diagnostic. The library never
prints. It skips each record that it cannot read, and it reports the record as a diagnostic.

For a database that it cannot read, `open()` raises a `cronos_extract.CronosError` or an `OSError`.
`cronos_extract.crack_kod(path, "strucrack")` or `"dbcrack"` recovers the KOD of a database that is encrypted with its
own KOD.

The [API reference](https://github.com/hammersleyfutures/cronos-extract/blob/main/docs/api.md) documents each public
name, each diagnostic kind and the promises of the API.


## Terminology

cronos-extract uses the usual words for databases, tables, records and fields. CronosPro uses different words:

| cronos-extract | CronosPro in English | CronosPro in Russian |
|:---------------|:---------------------|:---------------------|
| database       | Bank                 | Банк                 |
| table          | Base                 | Базы                 |
| record         | Record               | Записи               |
| field          | Field                | поля                 |
| system number  | System Number        | Системный номер      |


## Development

```bash
uv sync                      # create the virtual environment with the development tools
uv run pre-commit install    # lint, format, type-check and test before each commit
uv run pytest -q             # run the tests
uv run ruff check && uv run ruff format --check && uv run ty check
```

The characterisation tests in `tests/test_cli_characterisation.py` compare the output of the commands with the files
in `tests/golden/`. After a deliberate change of the output, run `uv run pytest --update-golden`. Then examine the
changes to the golden files before you commit them.

`tests/test_readme.py` runs each `cronos-extract` command in the `bash` blocks of this README. If a link in this
README is not an absolute URL, the test fails. PyPI shows this README, and a relative link does not work there.


## License

The [MIT license](https://github.com/hammersleyfutures/cronos-extract/blob/main/LICENSE) applies to cronos-extract.
The license keeps the copyright notice of cronodump.


## References

cronodump used the [documentation of the file format in older versions of Cronos](http://sergsv.narod.ru/cronos.htm).
It also used the [parser for the old file format](https://github.com/occrp/cronosparser) that came after this
documentation. That parser guesses offsets and obfuscation parameters with heuristics. cronodump replaced these
guesses with a stricter parser.

The [research notes](https://github.com/hammersleyfutures/cronos-extract/blob/main/docs/cronos-research.md) of this
repository document the file format.
