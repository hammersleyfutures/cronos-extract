# Changelog

This file lists the changes in each release of cronos-extract.

## 1.1.0

### Additions

- `open(path, strict_kod=True)` raises an exception for each KOD problem that `open()` otherwise survives. If CroStru
  or CroBank reports `mismatched_kod`, `open()` raises `WrongKod`. An example is a v3 file that is encrypted with its
  own KOD (`01.04` or `01.05`) and is read with the default KOD. If the database definition gives no table that the
  library can read, `open()` raises `DatabaseDefinitionError`. Without `strict_kod`, these records decode as garbage,
  and only a diagnostic tells you.
- `Bank.records()` gives the records of all tables as `(Table, Record)` pairs, in one sequential read of CroBank. It
  reads and decodes each record one time. Before, a program that read all tables read CroBank again for each table
  after the first, in an order that is not sequential.
- `test_data/sample_bank` is a small test database with live records: dates, times, Cyrillic text, a compressed
  record, a stored file and a file reference with no record number. The Quick start of the README exports it.
  `test_data/all_field_types` has no live records, so its export holds no rows.

### Changes

- The internal modules `Database`, `Datafile`, `Datamodel`, `koddecoder`, `readers` and `hexdump` moved from the root
  of the package to the private package `cronos_extract._core`. `survey` and `kodump` moved to
  `cronos_extract._cli`. These modules were always private, but their names made them look public. If you imported
  them, import the public names of `cronos_extract` in their place.

### Fixes

- `crack_kod()` examines the v4 headers of both CroStru and CroBank. Thus `open()` does not raise `WrongKod` for a KOD
  from `crack_kod()`. Before, `"strucrack"` could return the default KOD of a v3 CroStru when CroBank was v4 and
  encrypted with its own KOD.
- If `export --crack strucrack` cannot recover the KOD, the `Error:` line also tells you to try `--crack dbcrack`.
- The API reference tells what a `FileReference` without a record number means: the database does not store the
  file, but the name and the extension of the reference are correct.
- The library reads each record from the `.dat` file with `os.pread()`, where the system has it. Thus it reads only the
  bytes of the record. Before, each read of a record outside the buffer of the file filled the full buffer. On a
  network file system with a buffer of 128 KiB, this read about 2,600 times more bytes than the records held. On
  Windows, which has no `os.pread()`, the library reads as before. The library also reads no more bytes than the file
  holds for a record with a corrupt length.

## 1.0.0

cronos-extract 1.0 is the first release of cronos-extract. It continues
[cronodump](https://github.com/alephdata/cronodump) from its `master` branch. It has one command with four
subcommands, three export formats and a documented Python API. The library never prints. It reports each problem that
it survives as a diagnostic.

### Breaking changes

- Use the `cronos-extract` command in place of `crodump` and `croconvert`. These two commands are removed, and no
  alias replaces them. The subcommands of `cronos-extract` are `export`, `inspect`, `crack` and `survey`. The table
  after this list gives the replacement for each cronodump command.
- Use `export --csv`, `export --postgres` or `export --jsonl` in place of the HTML export. The HTML export, the
  `--template` option and the Jinja2 templates are removed. cronos-extract has no dependencies.
- If you need typed columns, cast them in SQL. Each column of the PostgreSQL export has the type `TEXT`, the system
  number included. Thus every record loads, also a record with a value that does not agree with its field type.
- Import `cronos_extract` in place of `crodump`. Open a database with `cronos_extract.open()`, which returns a `Bank`
  of tables, records and fields. The `Database`, `Datafile` and `Datamodel` classes are private. Only the names in
  `cronos_extract.__all__` are public. The
  [API reference](https://github.com/hammersleyfutures/cronos-extract/blob/main/docs/api.md) documents them.
- Use Python 3.12 or later. cronodump needed Python 3.7 or later.

| cronodump                                                           | cronos-extract                                 |
|:--------------------------------------------------------------------|:-----------------------------------------------|
| `croconvert --csv DB`                                               | `cronos-extract export --csv DB`               |
| `croconvert --template postgres DB`                                 | `cronos-extract export --postgres DB`          |
| `croconvert --outputdir DIR`                                        | `cronos-extract export -o DIR`                 |
| `crodump strudump`, `recdump`, `crodump`, `destruct` or `kodump`    | `cronos-extract inspect` with the same name    |
| `crodump sysdump DB`                                                | `cronos-extract inspect recdump --sys DB`      |
| `crodump strucrack` or `crodump dbcrack`                            | `cronos-extract crack` with the same name      |
| `--strucrack` or `--dbcrack`                                        | `--crack strucrack` or `--crack dbcrack`       |

### Additions

- `cronos-extract export --jsonl` writes JSON Lines, with one line for each table, record and diagnostic.
- `cronos-extract survey` tells which CronosPro version each database uses. It reads only the 19-byte header of each
  `Cro*.dat` file.
- `export --crack strucrack` and `export --crack dbcrack` recover the KOD and export with it in one step. The
  `strudump`, `recdump` and `crodump` subcommands of `inspect` also take `--crack`.
- Each problem that the export survives is a diagnostic. The export writes one `warning:` line on stderr for each
  diagnostic. At the end, it writes the number of diagnostics of each kind.
- If the export reports a diagnostic, `export --strict` exits with 1.
- The exit status tells the result: 0 for a complete run, 1 for a failure, 2 for a usage error and 130 for Ctrl-C. A
  failure writes one `Error:` line on stderr, with no traceback.
- If the `.tad` file of CroBank lists deleted records, the export tells how many.
- `cronos-extract --version` prints the version.
- The library examines the CRC-32 of each compressed record. It keeps a record whose CRC-32 does not agree with its
  data, and it reports the record as `checksum_mismatch`.
- The header of a KOD-encoded v4 file shows when a KOD is not its KOD. If the header of CroStru or CroBank rejects the
  KOD, `open()` raises `WrongKod`. `crack_kod()` does not return a KOD that the header of the file rejects.
- If a file does not use the KOD that the library got, the library reports `unused_kod`. If the KOD is not correct
  for a file, the library reports `mismatched_kod`.
- KOD decoding is about 13 times faster for a record of 1 KiB. A database of 100,000 KOD-encoded records of about
  1 KiB reads in about half the time.
- The library reads CroBank one time for all tables. Before, it read all of CroBank again for each table.

### Fixes

- A v4 record that the `.tad` file marks as deleted is not exported. Before, the export read it as a live record.
- A v4 record that the `.tad` file marks as extended is read as an extended record.
- If a record decompresses to more than 256 MiB, the library skips it and reports it as `corrupt_record`.
- The export escapes all text that it writes on stderr. Thus the names and values of a database cannot control the
  terminal.
- In a CSV file name, the export replaces path separators and the characters that no file system accepts. Each file
  name is unique in its directory.
- The PostgreSQL export starts with `SET standard_conforming_strings = on;`. It writes a NUL in a value as U+FFFD and
  reports it as `replaced_nul`.
- The byte `0x98`, which CP-1251 does not define, decodes to U+FFFD in all text.
- The CSV export writes each referenced file while it reads the records. Before, it kept all of these files in
  memory until the end.
