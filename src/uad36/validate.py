"""Structural validation: well-formedness + GSE subschema conformance.

Scope — deliberately narrow. This module answers one question: *is this
document structurally a UAD 3.6 URAR?* It checks that the XML parses and
that it conforms to the GSE-published UAD 3.6 subschema (fetched at runtime
by ``uad36 fetch-schemas``; never bundled).

It does NOT reimplement the GSEs' 800+ UAD compliance rules (conditionality,
cross-field logic, business rules). Fannie Mae and Freddie Mac each expose
those for free through their UAD Compliance APIs, which validate exactly
what UCDP will enforce at submission — see "Validating for UCDP submission"
in the README for how the two layers fit together.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from .errors import MalformedXmlError
from .fetch import require_schema_xsd
from .parse import XmlSource, parse_xml_tree

_schema_cache: dict[Path, etree.XMLSchema] = {}


@dataclass(frozen=True)
class Finding:
    """One validation problem, with enough context to act on it."""

    severity: str
    """``fatal`` (not XML at all) or ``error`` (schema violation)."""
    message: str
    line: int | None = None
    column: int | None = None

    def __str__(self) -> str:
        loc = f"line {self.line}" if self.line else "document"
        return f"[{self.severity}] {loc}: {self.message}"


@dataclass
class ValidationResult:
    """Outcome of :func:`validate_xml`."""

    well_formed: bool
    schema_checked: bool
    findings: list[Finding] = field(default_factory=list)
    schema_path: Path | None = None

    @property
    def valid(self) -> bool:
        """Well-formed, schema-checked, and free of findings."""
        return self.well_formed and self.schema_checked and not self.findings

    def summary(self) -> str:
        if not self.well_formed:
            return "not well-formed XML"
        if not self.schema_checked:
            return "well-formed (schema not checked)"
        if self.findings:
            return f"well-formed, {len(self.findings)} schema finding(s)"
        return "valid against the GSE UAD 3.6 subschema"


def _readable(message: str) -> str:
    """Strip namespace clutter from lxml's error messages."""
    return (
        message.replace("{http://www.mismo.org/residential/2009/schemas}", "")
        .replace("{http://www.datamodelextension.org}", "gse:")
        .replace("{http://www.w3.org/1999/xlink}", "xlink:")
    )


def load_schema(schemas_root: Path | None = None) -> tuple[etree.XMLSchema, Path]:
    """Compile (and cache) the fetched GSE subschema.

    Raises :class:`~uad36.errors.SchemaNotAvailableError` if it has not been
    fetched yet.
    """
    xsd_path = require_schema_xsd(schemas_root)
    if xsd_path not in _schema_cache:
        _schema_cache[xsd_path] = etree.XMLSchema(etree.parse(str(xsd_path)))
    return _schema_cache[xsd_path], xsd_path


def validate_xml(
    source: XmlSource,
    *,
    schemas_root: Path | None = None,
    require_schema: bool = True,
) -> ValidationResult:
    """Validate a URAR XML document structurally.

    With ``require_schema=False``, a missing fetched schema degrades to a
    well-formedness-only check instead of raising.
    """
    try:
        tree = parse_xml_tree(source)
    except MalformedXmlError as exc:
        return ValidationResult(
            well_formed=False,
            schema_checked=False,
            findings=[Finding(severity="fatal", message=str(exc))],
        )

    try:
        schema, xsd_path = load_schema(schemas_root)
    except Exception:
        if require_schema:
            raise
        return ValidationResult(well_formed=True, schema_checked=False)

    findings: list[Finding] = []
    if not schema.validate(tree):
        for err in schema.error_log:
            findings.append(
                Finding(
                    severity="error",
                    message=_readable(err.message),
                    line=err.line if err.line > 0 else None,
                    column=err.column if err.column > 0 else None,
                )
            )
    return ValidationResult(
        well_formed=True,
        schema_checked=True,
        findings=findings,
        schema_path=xsd_path,
    )
