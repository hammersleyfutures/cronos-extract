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
- Iteration is lazy: ``Table.records()`` and ``Bank.files()`` read one CroBank record per step. Each
  ``records()`` call walks all of CroBank.
- A ``Bank`` is not thread-safe. Generators from one bank may be interleaved on one thread.
- The library never prints. Problems reading survives are ``Diagnostic``s: ``bank.diagnostics`` keeps the first
  1,000, ``bank.diagnostic_counts`` counts every one, and ``on_diagnostic`` receives every one. Diagnostics from
  decoding a record are recorded each time the record is decoded. Later versions may add ``DiagnosticKind`` members.
- ``Field.value`` is ``str``, ``datetime.date``, ``datetime.time``, ``FileReference`` or ``None``; later versions may
  add types. Numbers are ``str``. A date stored with only its year is ``str``, such as ``"1985-00-00"``.
- ``compact=True`` reads the CroStru and CroBank indexes from disk instead of memory, for very large databases.
- ``from cronos_extract import *`` replaces the built-in ``open``; use ``import cronos_extract``.
"""

from ._api.bank import Bank, Table, open
from ._api.crack import crack_kod
from ._api.diagnostics import Diagnostic, DiagnosticKind
from ._api.errors import CronosError, DatabaseDefinitionError, NotACronosFile, UnsupportedVersion
from ._api.info import FileInfo
from ._api.kod import Kod
from ._api.values import EmbeddedFile, Field, FieldDefinition, FileReference, Record

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
    "Kod",
    "NotACronosFile",
    "Record",
    "Table",
    "UnsupportedVersion",
    "crack_kod",
    "open",
]
