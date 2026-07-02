"""Exception types. Everything raised on purpose derives from Uad36Error."""

from __future__ import annotations


class Uad36Error(Exception):
    """Base class for all uad36 errors."""


class MalformedXmlError(Uad36Error):
    """The document is not well-formed XML (parse failed outright)."""


class PackageError(Uad36Error):
    """The UCDP ZIP is unreadable or does not contain a URAR XML."""


class SchemaNotAvailableError(Uad36Error):
    """Schema validation was requested but no fetched GSE subschema was found.

    Run ``uad36 fetch-schemas`` (or :func:`uad36.fetch.fetch_schemas`) first.
    This package never bundles schema files — see the README licensing note.
    """


class FetchError(Uad36Error):
    """A download from the GSE URLs failed."""
