# Test databases

The tests and the examples of the README use these CronosPro databases.

## all_field_types

A database made with CronosPro. Its table `erdgeist` has a field of each field type. Its CroStru, CroBank and CroIndex
are version `01.02` (v3). CroStru is KOD-encoded with the default KOD, and CroBank and CroIndex are not KOD-encoded.
CroBank lists 85 deleted records and holds no live record. Thus an export of it writes the tables and no records.
The subdirectory `Voc` holds a second database of the same layout.

The database definition and the table definitions of each database that `tests/cronos_builder.py` writes come from
this database.

## sample_bank

A database that `tests/cronos_builder.py` writes with `write_sample_bank`. It has the table definitions of
`all_field_types`. Its CroStru and CroBank are version `01.02` (v3), KOD-encoded with the default KOD. The table
`erdgeist` holds three live records:

| Record | Contents |
|---|---|
| 1 | Text in Latin and Cyrillic letters, the date 2024-03-15, the time 09:30, and a reference to the stored file `notes.txt` |
| 2 | Two text fields and a date with only its year (`1985-00-00`). The record is compressed. |
| 3 | The time 17:45, and a reference to the file `scan.jpg`, which has no record number: the database does not store this file |

Record 4 is the one record of the Files table. It holds `notes.txt`.

To write `sample_bank` again after a change to the builder, run
`uv run pytest --update-golden tests/test_sample_bank.py`. Then `git diff test_data` must show only the intended
change.
