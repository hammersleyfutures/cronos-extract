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

In its simplest form, the croconvert command creates a [CSV](https://en.wikipedia.org/wiki/Comma-separated_values) representation of all the database's tables and a copy of all files contained in the database:

```bash
uv tool install git+https://github.com/hammersleyfutures/cronos-extract
croconvert --csv test_data/all_field_types
```

By default it creates a `cronodump-YYYY-mm-DD-HH-MM-SS-ffffff/` directory containing CSV files for each table found. It will under this directory also create a `Files-FL/` directory containing all the files stored in the Database, regardless if they are (still) referenced in any data table. All files that are actually referenced (and thus are known by their filename) will be stored under the `Files-Referenced` directory. With the `--outputdir` option you can chose your own dump location.

When you get an error message, or just unreadable data, chances are your database is protected. You may need to look into the `--dbcrack` or `--strucrack` options, explained below.


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


# Templates

The croconvert command uses the [jinja templating framework](https://jinja.palletsprojects.com/) to render more file formats like PostgreSQL and HTML.
The default action for `croconvert` is to convert the database using the `html` template:

```bash
croconvert test_data/all_field_types > test_data.html
```

This dumps an HTML file with all tables found in the database, files listed and ready for download as inlined [data URI](https://en.wikipedia.org/wiki/Data_URI_scheme) and all table images inlined as well. Note that the resulting HTML file can be huge for large databases, causing a lot of load on browsers when trying to open them.


The `-t postgres` command will dump the table schemes and records as valid `CREATE TABLE` and `INSERT INTO` statements to stdout. This dump can then be imported in a PostgreSQL database. Each record becomes its own `INSERT` statement. Every column is declared `TEXT`, the system number included, so every record loads even when a value doesn't match its field type. Values are written exactly as croconvert decodes them: dates as `YYYY-MM-DD`, times as `HH:MM`, and empty values as `NULL`. Cast columns in SQL when you need types, for example `"Entry #4"::date`. Values are written as standard SQL string literals: single quotes are doubled and backslashes are kept as they are. This is correct when the [`standard_conforming_strings`](https://www.postgresql.org/docs/current/runtime-config-compatible.html#GUC-STANDARD-CONFORMING-STRINGS) option is on, which is the default since PostgreSQL 9.1. Do not import the dump with that option turned off.

Pull requests for [more templates supporting other output types](src/cronos_extract/templates) are welcome.


# Inspection

The `crodump` command helps to further investigate databases. This might be useful for extracting metadata like path names of table image files or input and output forms. Not all metadata has yet been completely reverse engineered, so some experience with understanding binary dumps might be required.

The crodump command has a plethora of options but in the most basic for the `strudump` sub command will provide a rich variety of metadata to look further:

```bash
crodump strudump -v -a test_data/all_field_types/
```
The `-a` option tells strudump to output ascii instead of a hexdump.

For a low level dump of the database contents, use:
```bash
crodump crodump -v  test_data/all_field_types/
```
The `-v` option tells crodump to include all unused byte ranges, this may be useful when identifying deleted records.

For a bit higher level dump of the database contents, use:
```bash
crodump recdump  test_data/all_field_types/
```
This will print a hexdump of all records for all tables.


## decoding password protected databases

Cronos v4 and higher are able to password protect databases, the protection works
by modifying the KOD sbox. cronos-extract has two methods of deriving the KOD sbox from
a database:

Both these methods are statistics based operations, it may not always
yield the correct KOD sbox.


### 1. strudump

When the database has a sufficiently large CroStru.dat file,
it is easy to derive the nodified KOD-sbox from the CroStru file, the `--strucrack` option
will do this. 

    crodump --strucrack  recdump <dbpath>

### 2. dbdump

When the Bank and Index files are compressed, we can derive the KOD sbox by inspecting
the fourth byte of each record, which should decode to a zero.

The `--dbcrack` option will do this.

    crodump --dbcrack  recdump <dbpath>


# Installing

cronos-extract requires Python 3.12 or later and installs the `Jinja2` templating engine as its only dependency.

 * Install the `cronos-extract`, `crodump` and `croconvert` commands with `uv tool install git+https://github.com/hammersleyfutures/cronos-extract`.
 * Or run them from a clone of this repository with `uv run cronos-extract ...`, `uv run crodump ...` and `uv run croconvert ...`.


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
