# cronos-extract API reference

This document describes the Python API of cronos-extract 1.1. The API reads CronosPro databases. It does not write
them.

A CronosPro database is a directory of Cro files. Each Cro file is a pair of a `.dat` file and a `.tad` file. CroStru
holds the table definitions. CroBank holds the records of all tables. The Files table in CroBank stores embedded
files. CroIndex and CroSys are optional.

A KOD-encoded Cro file stores its records encrypted with a KOD. This KOD is the default KOD or the own KOD of the
database. A Cro file "encrypted with its own KOD" is a KOD-encoded file that uses the own KOD of the database.

## Read a database

To read the records of a database and the problems in it, do these steps:

1. Import `cronos_extract`.
2. Write a function that receives one `Diagnostic`.
3. Open the database with `cronos_extract.open()`. Give your function as `on_diagnostic`.
4. If `open()` raises `OSError` or a `CronosError`, show the message. Then stop.
5. Use the `Bank` in a `with` statement. The statement closes the database at the end.
6. Read the records of each table in `bank.tables` with `table.records()`.

```python
import cronos_extract


def show(diagnostic: cronos_extract.Diagnostic) -> None:
    print("warning:", diagnostic.kind, diagnostic.message)


try:
    bank = cronos_extract.open("path/to/database", on_diagnostic=show)
except (OSError, cronos_extract.CronosError) as error:
    raise SystemExit(f"cannot read the database: {error}") from error

with bank:
    for table in bank.tables:
        for record in table.records():
            print(table.name, record.number, [field.text for field in record.fields])
```

If the database is encrypted with its own KOD, get the KOD with `crack_kod()` first. Then give it to `open()` as
`kod`.

## Promises

These promises apply to every 1.0 release.

**Public names.** Only the names in `cronos_extract.__all__` are public. Other modules and names in the package are
private. A later version can change them without notice.

**Imports.** `from cronos_extract import *` replaces the built-in `open`. For this reason, the examples use
`import cronos_extract`.

**Lazy reading.** `Table.records()` and `Bank.files()` are generators. Each step reads CroBank records only up to the
next record of its table. The library reads CroBank one time for all tables together. The first generator that reaches a
CroBank record adds it to an index of the records of each table. After that, a table reads only its own records.

**Memory.** The index of CroBank holds about 4 bytes for each live CroBank record. If 4 bytes cannot hold the record
numbers, the index holds 8 bytes for each record. The `compact` parameter of `open()` does not change the size of this
index.

**Threads.** A `Bank` is not thread-safe. On one thread, you can interleave the steps of different generators from one
`Bank`.

**Diagnostics.** The library never prints. It gives each problem that it survives as a `Diagnostic`. The `Bank` keeps
the first 1,000 diagnostics in `bank.diagnostics`. It counts every diagnostic in `bank.diagnostic_counts`. The
`on_diagnostic` function receives every diagnostic.

**Repeated diagnostics.** The library records the diagnostics of a record each time that it decodes the record. If you
read a table two times, its field diagnostics occur two times.

**New kinds.** A later version can add members to `DiagnosticKind`.

**Deleted records.** The library does not read deleted records. `bank.deleted_records` gives their number.

**Values.** `Field.value` is `str`, `datetime.date`, `datetime.time`, `FileReference` or `None`. A later version can
add value types. Numbers are `str`. A date that holds only its year is `str`, for example `"1985-00-00"`.

**Errors.** If `open()` cannot read a database, it raises a `CronosError`, an `OSError` or a `TypeError`. The
subclasses of `CronosError` are `NotACronosFile`, `UnsupportedVersion`, `WrongKod` and `DatabaseDefinitionError`.
`OSError` is for a directory that cannot be read, and `TypeError` is for a `bytes` path.

## open()

```python
def open(
    path: str | os.PathLike[str],
    *,
    kod: Kod | None = Kod.default(),
    compact: bool = False,
    strict_kod: bool = False,
    on_diagnostic: Callable[[Diagnostic], object] | None = None,
) -> Bank: ...
```

`open()` opens the CronosPro database in the directory `path` and returns a `Bank`. It reads the database definition
and the table definitions. It does not read the records.

| Parameter | Meaning |
|---|---|
| `path` | The directory of the database, as `str` or `os.PathLike[str]`. The names of the Cro files match without regard to case. |
| `kod` | The KOD that decodes the records. The default is `Kod.default()`. With `None`, `open()` reads all records without KOD decoding. |
| `compact` | With `True`, `open()` reads the `.tad` index of CroStru and CroBank from the disk for each record. With `False`, it keeps each `.tad` file in memory. `compact=True` is for very large databases. |
| `strict_kod` | With `True`, `open()` raises an exception for each KOD problem that it otherwise survives. The section [Strict KOD](#strict-kod) gives the cases. |
| `on_diagnostic` | A function that receives each diagnostic at the time that the library records it. |

`open()` uses the `kod` only for a Cro file that is encrypted with its own KOD. These files are versions `01.04`,
`01.05` and all v4 versions. For a Cro file that is encrypted with the default KOD, `open()` uses the default KOD. For a
Cro file that is not KOD-encoded, `open()` does not decode KOD. The diagnostics `unused_kod` and `mismatched_kod` tell
you about these decisions.

### Strict KOD

Without `strict_kod`, `open()` refuses a wrong KOD only when the v4 header of CroStru or CroBank shows it. In other
cases, a wrong KOD gives only a `mismatched_kod` diagnostic, and the records decode as garbage. With
`strict_kod=True`, `open()` also raises an exception in these cases:

- CroStru or CroBank records `mismatched_kod`. `open()` raises `WrongKod`. An example is a v3 file that is encrypted
  with its own KOD (version `01.04` or `01.05`), which `open()` reads with the default KOD. Another example is a
  KOD-encoded file with `kod=None`. The header of a v3 file cannot show which KOD encrypted it. Thus `open()` also
  raises `WrongKod` for a `01.04` or `01.05` file that is encrypted with the default KOD. Open such a database without
  `strict_kod`.
- The database definition gives no table that the library can read. `open()` raises `DatabaseDefinitionError`. A
  wrong KOD can decode the definition into data that has the correct layout, but that has no table definitions that
  the library can decode.

Thus, with `strict_kod=True`, one `except` clause for `WrongKod` and `DatabaseDefinitionError` catches all wrong-KOD
cases. Then, you can recover the KOD with `crack_kod()`.

An exception from `on_diagnostic` goes to the code that recorded the diagnostic. This code is `open()`, a generator
step, or `Bank.read_file()`. Thus, `on_diagnostic` can stop the reading with an exception.

`open()` raises these exceptions:

| Exception | Cause |
|---|---|
| `OSError` | `path` does not exist, is not a directory, or cannot be listed. |
| `TypeError` | `path` is `bytes`. |
| `NotACronosFile` | CroStru or CroBank is missing, cannot be opened, or is not a Cronos file. |
| `UnsupportedVersion` | CroStru or CroBank has a version that this release does not read. |
| `WrongKod` | The header of a KOD-encoded v4 CroStru or CroBank shows that `kod` is not its KOD. `open()` examines CroStru first, then CroBank. With `strict_kod=True`, also CroStru or CroBank records `mismatched_kod`. |
| `DatabaseDefinitionError` | The database definition in CroStru cannot be decoded. With `strict_kod=True`, also the definition gives no table that the library can read. |

## Bank

A `Bank` is an open CronosPro database. `open()` returns it. A `Bank` is a context manager. At the end of the `with`
statement, it closes its Cro files.

| Attribute | Meaning |
|---|---|
| `tables` | A tuple of `Table`, in the order of the database definition. The Files table is not in it. |
| `info` | A tuple of `FileInfo`, one for each Cro file that `open()` found, in the order CroStru, CroBank, CroIndex, CroSys. |
| `deleted_records` | The number of deleted records that the `.tad` header of CroBank lists. |
| `diagnostics` | A read-only sequence of the first 1,000 diagnostics. It grows while you read. |
| `diagnostic_counts` | A read-only mapping from each `DiagnosticKind` to the number of its diagnostics. It counts every diagnostic. |
| `files_abbreviation` | The abbreviation of the Files table, or `None` for a database without a Files table. |

If CroIndex or CroSys has no `.dat` file and no `.tad` file, `info` has no entry for it.

If the `.tad` header of CroBank lists more deleted records than the `.tad` file has entries, `open()` records
`unexpected_structure`. Then `deleted_records` is the number of entries.

`bank.diagnostic_counts[kind]` is 0 for a kind that did not occur. But that kind is not `in` the mapping, and it is not
one of its keys.

`files()` is a generator of the files in the Files table, as `EmbeddedFile` objects. It gives them in CroBank order.
Each step reads CroBank records only up to the next record of the Files table. Each `EmbeddedFile` from `files()` has
the name `None`, because the Files table stores no names. If the database has no Files table, `files()` gives nothing.

`read_file(reference)` returns the `EmbeddedFile` that a `FileReference` refers to. The name of the file is
`"name.extension"` from the reference, or only the name without an extension. If the record of the reference is not a
readable record of the Files table, `read_file()` records `unresolved_file_reference` and returns `None`.

`close()` closes the Cro files. A second `close()` does nothing. After `close()`, `records()`, `files()` and
`read_file()` raise `ValueError`. A generator that started before `close()` also raises `ValueError` at its next step.

## Table

A `Table` is one table of the database. `bank.tables` holds them.

| Attribute | Meaning |
|---|---|
| `id` | The table id. The first byte of each CroBank record of the table holds it. |
| `name` | The name of the table. |
| `abbreviation` | The abbreviation of the table. |
| `fields` | A tuple of `FieldDefinition`. The first is the system number. Each describes the field of a `Record` at the same index. |

`records()` is a generator of the records of the table, as `Record` objects. It gives them in CroBank order. Each step
reads CroBank records only up to the next record of the table.

`records()` does not give deleted records. It also does not give a record that it cannot read. It records
`corrupt_record` for that record instead.

If the table id is more than 255, `records()` gives nothing and records `unsupported_table`.

An `OSError` from reading a Cro file goes to the caller of the generator.

## Record

A `Record` is one record of a table.

| Attribute | Meaning |
|---|---|
| `number` | The CroBank record number. Record numbers start at 1. |
| `fields` | A tuple of `Field`, one for each `FieldDefinition` of the table. |
| `diagnostics` | A tuple of the field diagnostics of this record: `undecodable_field` and `invalid_value`. |

`record["name"]` returns the first field with the name `name`. If no field has this name, it raises `KeyError`.

## Field

A `Field` is one field of a record.

| Attribute | Meaning |
|---|---|
| `definition` | The `FieldDefinition` of the field. |
| `value` | The typed value of the field. |
| `text` | The field as text for display. |
| `raw` | The bytes of the field in the record. They do not include the field separator, or the marker and length of a complex field. |

The type of `value` depends on the field type:

| Field | `value` |
|---|---|
| Empty field | `None` |
| Date field (type 4) | `datetime.date` |
| Date field that holds only its year | `str`, for example `"1985-00-00"` |
| Time field (type 5) | `datetime.time` |
| File field (type 6) | `FileReference` |
| Date or time field that does not parse | `str`, the text of the field |
| All other fields, numbers included | `str` |

If a date or time does not parse, the record gets the diagnostic `invalid_value`.

The first field is the system number. Its `value` and `text` are the system number as `str`. Its `raw` is `b""`.

If a field cannot be decoded, the record gets the diagnostic `undecodable_field`, and the field is empty. If the length
of the field cannot be read, all fields after it are also empty.

## FieldDefinition

A `FieldDefinition` describes one field of a table. Two attributes hold the description:

- `name`: the name of the field.
- `type`: the CronosPro field type code, as `int`. For example, 0 is the system number, 4 is a date, 5 is a time
  and 6 is a file.

## FileReference

A `FileReference` is the value of a file field. It refers to a file in the Files table. `Bank.read_file()` takes it and
returns the file.

| Attribute | Meaning |
|---|---|
| `name` | The name of the file. |
| `extension` | The extension of the file. |
| `record` | The CroBank record number of the file. It is `None` for a reference that does not hold a number. |
| `table` | The name of the table that holds the reference. |
| `referrer` | The CroBank record number of the record that holds the reference. |
| `field` | The name of the field that holds the reference. |

If you make a `FileReference` without `table`, `referrer` and `field`, they are `None`. The diagnostic
`unresolved_file_reference` uses them as its location.

## EmbeddedFile

An `EmbeddedFile` is a file from the Files table.

| Attribute | Meaning |
|---|---|
| `record` | The CroBank record number of the file. |
| `data` | The bytes of the file. |
| `name` | `"name.extension"` from `Bank.read_file()`, or `None` from `Bank.files()`. |

## Kod

A `Kod` is a KOD table. A KOD table is a permutation of the numbers 0 to 255. CronosPro uses it to encrypt records. A
`Kod` is immutable. Two `Kod` objects with equal tables are equal.

| Name | Meaning |
|---|---|
| `table` | The table, as a tuple of 256 `int`. |
| `Kod.default()` | The KOD that CronosPro uses for a database without its own KOD. |
| `Kod.from_table(table)` | A `Kod` from a sequence of 256 `int`. |
| `Kod.from_hex(text)` | A `Kod` from 512 hex digits, two for each table entry, in upper or lower case. |
| `kod.hex()` | The table as 512 lower-case hex digits. `Kod.from_hex()` reads this text. |

If a table is not a permutation of 0 to 255, `Kod`, `Kod.from_table()` and `Kod.from_hex()` raise `ValueError`.
`Kod.from_hex()` also raises `ValueError` for text that is not exactly 512 hex digits.

## crack_kod()

```python
def crack_kod(path: str | os.PathLike[str], method: Literal["strucrack", "dbcrack"]) -> Kod | None: ...
```

`crack_kod()` recovers the KOD of the database in the directory `path`. It uses byte statistics of the encrypted
records. It prints nothing.

| Method | What it reads |
|---|---|
| `"strucrack"` | The records of CroStru. |
| `"dbcrack"` | The first 10,000 records of CroBank and of CroIndex. |

`crack_kod()` skips records that it cannot read. It returns `None` in these cases:

- The statistics do not give a permutation of 0 to 255.
- The method is `"dbcrack"`, and the database has no readable CroIndex.
- The v4 header of CroStru or CroBank shows that the permutation is not the KOD of the database. Thus `open()` does
  not raise `WrongKod` for a KOD from `crack_kod()`. Both methods examine the headers of both files. A database can mix
  versions. For example, CroStru can be v3 with the default KOD, and CroBank can be v4 with its own KOD. Then
  `"strucrack"` gets the default KOD from CroStru, and the header of CroBank rejects it.

If CroStru or CroBank cannot be read, `crack_kod()` raises `NotACronosFile` or `UnsupportedVersion`. For an unknown
method, it raises `ValueError`.

To open a database that is encrypted with its own KOD, do these steps:

1. Call `crack_kod(path, "strucrack")`.
2. If the result is `None`, call `crack_kod(path, "dbcrack")`.
3. If this result is also `None`, stop. `crack_kod()` cannot recover the KOD of this database.
4. Give the KOD to `open()` as `kod`.
5. If the KOD came from `"strucrack"` and `open()` raises `WrongKod` or `DatabaseDefinitionError`, call
   `crack_kod(path, "dbcrack")`.
6. If this result is not `None`, do step 4 again with it.

Step 5 is for v3 files that are encrypted with their own KOD. Give `strict_kod=True` to `open()` in step 4. Then a
wrong KOD for these files also raises `WrongKod` or `DatabaseDefinitionError`, and does not decode the records as
garbage.

## FileInfo

A `FileInfo` describes one `Cro*.dat` file, as its header describes it. `Bank.info` holds one `FileInfo` for each Cro
file. A `FileInfo` is immutable.

| Attribute | Meaning |
|---|---|
| `name` | The part of the file name between `Cro` and `.dat`, as the disk spells it, for example `"Stru"`. |
| `path` | The path of the file, as `pathlib.Path`. |
| `version` | The format version as text, for example `"01.02"`. |
| `generation` | The `Generation` of the version. |
| `use64bit` | Whether the `.tad` entries hold 64-bit file offsets. |
| `kod_encoded` | Whether the records are KOD-encoded (bit 0 of the encoding field). |
| `compressed` | Whether the records can be compressed (bit 1 of the encoding field). |
| `own_kod` | Whether the version is `01.04`, `01.05` or v4. The records of these versions use the own KOD of the database, not the default KOD. |
| `problem` | Why the library cannot read the header, or `None`. |

A `FileInfo` has one of two forms:

- `problem` is `None`, and all other attributes have a value.
- `problem` is text, and `version`, `generation`, `use64bit`, `kod_encoded`, `compressed` and `own_kod` are `None`.

For all other combinations, `FileInfo` raises `ValueError`. A file with an unknown or v7 version has the first form.
Its `generation` is `"unknown"` or `"v7"`.

## Generation

`Generation` is the type of `FileInfo.generation`. It is `Literal["v3", "v4", "v7", "unknown"]`.
`typing.get_args(cronos_extract.Generation)` gives the four names.

| Generation | Versions |
|---|---|
| `"v3"` | `01.02`, `01.03`, `01.04`, `01.05` |
| `"v4"` | `01.11`, `01.13`, `01.14` |
| `"v7"` | `01.19` |
| `"unknown"` | All other versions |

This release reads v3 and v4 only.

## Diagnostic

A `Diagnostic` is a problem that the library found and survived. A `Diagnostic` is immutable.

| Attribute | Meaning |
|---|---|
| `kind` | The `DiagnosticKind`. |
| `message` | A description of the problem. |
| `file` | The name of the Cro file, for example `"CroBank.dat"`, or `None`. |
| `table` | The name of the table, or `None`. |
| `record` | The record number in `file`, or `None`. If `table` has a value, it is a CroBank record number. |
| `field` | The name of the field, or `None`. |

If a location attribute does not apply to the problem, it is `None`. The message never holds the content of a CroBank
record. It can hold record numbers.

## DiagnosticKind

`DiagnosticKind` is a `StrEnum`. The name of each member is its value in upper case. Each member is equal to its
value, for example `DiagnosticKind.CORRUPT_RECORD == "corrupt_record"`.

| Value | Meaning |
|---|---|
| `corrupt_record` | A CroBank record cannot be read or decoded. The library skips it. It records this diagnostic one time for each record. |
| `checksum_mismatch` | The CRC-32 of compressed data in a record does not match. The library keeps the record as it decompressed. In CroBank, it records this diagnostic one time for each record. |
| `undecodable_field` | A field of a CroBank record cannot be decoded. The field is empty. If the length of the field cannot be read, all fields after it are also empty. |
| `invalid_value` | A date or time field holds text that is not a valid date or time. The value of the field is its text. |
| `undecodable_table` | A table definition in CroStru cannot be decoded, or does not start with the system number field. The table is not in `bank.tables`. |
| `unsupported_table` | A table has an id of more than 255. `records()` gives nothing for it. The library records this diagnostic one time for each table. |
| `unexpected_structure` | A part of a Cro file does not have the expected layout, but reading continues. The list after this table gives the causes. |
| `unresolved_file_reference` | `Bank.read_file()` cannot find a readable record of the Files table for a `FileReference`. It returns `None`. |
| `unreadable_file` | CroIndex or CroSys has only one of its two files, or its header cannot be read. The `problem` of its `FileInfo` tells why. |
| `unused_kod` | A Cro file does not use the KOD that `open()` got, and this KOD is not the default KOD. The file is not KOD-encoded, or is encrypted with the default KOD. |
| `mismatched_kod` | The KOD for a Cro file is not correct. The cases are in the list after this table. |

The library records `unexpected_structure` in these cases:

- The directory holds two or more Cro files with the same name in different case. `open()` reads the first in sorted
  order.
- The `.tad` header of CroBank lists more deleted records than the `.tad` file has entries.
- A `.tad` file has bytes after its last full entry.
- The database definition or a table definition in CroStru does not have the expected layout.

The library records `mismatched_kod` for CroStru and CroBank in these cases:

- The file is KOD-encoded, but `open()` got `kod=None`.
- The v4 header of the file shows that the KOD is not its KOD. `open()` then raises `WrongKod`.
- The file is encrypted with its own KOD, but `open()` reads it with the default KOD.

With `strict_kod=True`, `open()` raises `WrongKod` in each of these cases.

## Exceptions

### CronosError

`CronosError` is the base class of the exceptions for a database that the library cannot read. It is a subclass of
`Exception`. The four classes below are its subclasses.

### NotACronosFile

`open()` and `crack_kod()` raise `NotACronosFile` for CroStru or CroBank in these cases:

- The `.dat` file or the `.tad` file is missing.
- A file cannot be opened, or is not a regular file.
- The `.dat` header is shorter than 19 bytes, or does not start with the Cronos magic.
- The `.tad` file is shorter than its header.

### UnsupportedVersion

If the version of CroStru or CroBank is not v3 or v4, `open()` and `crack_kod()` raise `UnsupportedVersion`. Version
`01.19` (v7) is an example.

### WrongKod

If the header of a KOD-encoded v4 CroStru or CroBank shows that the KOD is not its KOD, `open()` raises `WrongKod`. This
KOD is the `kod` parameter, or the default KOD. `open()` examines CroStru first, then CroBank. The message names the
`crack_kod()` method that can recover the KOD.

With `strict_kod=True`, `open()` also raises `WrongKod` when CroStru or CroBank records `mismatched_kod`.

### DatabaseDefinitionError

If the database definition in CroStru record 1 is missing or cannot be decoded, `open()` raises
`DatabaseDefinitionError`. A frequent cause is a wrong KOD. In that case, the definition decodes as garbage, and
`crack_kod()` can recover the correct KOD. With `strict_kod=True`, `open()` also raises `DatabaseDefinitionError`
when the definition gives no table that the library can read.

### Other exceptions

The API also raises these standard exceptions:

| Exception | Cause |
|---|---|
| `OSError` | A Cro file cannot be read. |
| `TypeError` | A path is `bytes`. |
| `ValueError` | The `Bank` is closed, a KOD table is not valid, `crack_kod()` got an unknown method, or a `FileInfo` has an invalid combination of attributes. |
| `KeyError` | `record["name"]` finds no field with that name. |
