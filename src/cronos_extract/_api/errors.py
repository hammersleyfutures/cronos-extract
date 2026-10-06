# ABOUTME: The exceptions the cronos_extract API raises for a database it cannot read at all.
# ABOUTME: Problems it can survive, such as one corrupt record, are diagnostics instead.


class CronosError(Exception):
    """The base class of the errors cronos_extract raises for a database it cannot read."""


class NotACronosFile(CronosError):
    """A CroStru or CroBank file is missing, cannot be opened, is not a regular file or is not a Cronos file."""


class UnsupportedVersion(CronosError):
    """CroStru or CroBank is a CronosPro version this release does not read."""


class DatabaseDefinitionError(CronosError):
    """The database definition in CroStru record 1 is missing or cannot be decoded."""


class WrongKod(CronosError):
    """
    The header of a KOD-encoded v4 CroStru or CroBank shows that the KOD given, or the default, is not its KOD; or,
    with strict_kod, CroStru or CroBank is read with a KOD it reports as mismatched_kod.
    """
