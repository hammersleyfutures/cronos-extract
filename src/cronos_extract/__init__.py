# ABOUTME: The cronos_extract library API: open a CronosPro database and read its tables, records and files.
# ABOUTME: Every public name is re-exported here and listed in __all__; everything else in the package is private.
"""
Read CronosPro databases.

    import cronos_extract

    with cronos_extract.open("path/to/database") as bank:
        for table in bank.tables:
            for record in table.records():
                print(record["Entry #4"].value)

This API promises:

- Only the names in ``__all__`` are public. Other modules and names in the package are private and may change.
- Iteration is lazy: each step of ``Table.records()`` and ``Bank.files()`` reads CroBank only up to the table's next
  record. CroBank is scanned once for all tables together; each table then reads only its own records.
  ``Bank.records()`` reads every table's records in one sequential pass, decoding each record once.
- A ``Bank`` is not thread-safe. Generators from one bank may be interleaved on one thread.
- The library never prints. Problems that reading survives are ``Diagnostic``s: ``bank.diagnostics`` keeps the first
  1,000, ``bank.diagnostic_counts`` counts every one, and ``on_diagnostic`` receives every one. Diagnostics from
  decoding a record are recorded each time the record is decoded. Later versions may add ``DiagnosticKind`` members.
- Deleted records are not read. ``bank.deleted_records`` is the number CroBank's ``.tad`` header lists; a header
  listing more than the ``.tad`` has entries is reported as ``unexpected_structure``, and the count is then the
  number of entries.
- A database ``open()`` cannot read raises a ``CronosError``: ``NotACronosFile``, ``UnsupportedVersion``,
  ``WrongKod`` (a KOD-encoded v4 CroStru or CroBank whose header shows that the KOD given, or the default, is not
  its KOD) or ``DatabaseDefinitionError``. With ``strict_kod=True``, ``open()`` also raises ``WrongKod`` when CroStru or
  CroBank reports ``mismatched_kod``, and ``DatabaseDefinitionError`` when the definition yields no table.
- ``Field.value`` is ``str``, ``datetime.date``, ``datetime.time``, ``FileReference`` or ``None``; later versions may
  add types. Numbers are ``str``. A date stored with only its year is ``str``, such as ``"1985-00-00"``.
- ``compact=True`` reads the CroStru and CroBank indexes from disk instead of memory, for very large databases. The
  table index of CroBank holds about 4 bytes per live CroBank record (8 where 4 cannot hold its record numbers),
  whether or not ``compact`` is set.
- ``from cronos_extract import *`` replaces the built-in ``open``; use ``import cronos_extract``.
"""

from ._api.bank import Bank, Table, open
from ._api.crack import crack_kod
from ._api.diagnostics import Diagnostic, DiagnosticKind
from ._api.errors import CronosError, DatabaseDefinitionError, NotACronosFile, UnsupportedVersion, WrongKod
from ._api.info import FileInfo
from ._api.kod import Kod
from ._api.values import EmbeddedFile, Field, FieldDefinition, FileReference, Record
from ._format.header import Generation

__all__ = [
    "Bank",
    "CronosError",
    "DatabaseDefinitionError",
    "Diagnostic",
    "DiagnosticKind",
    "EmbeddedFile",
    "Field",
    "FieldDefinition",
    "FileInfo",
    "FileReference",
    "Generation",
    "Kod",
    "NotACronosFile",
    "Record",
    "Table",
    "UnsupportedVersion",
    "WrongKod",
    "crack_kod",
    "open",
]
