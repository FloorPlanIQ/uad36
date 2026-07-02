"""PII awareness and redaction for UAD 3.6 URAR data.

A URAR is nonpublic personal information (NPI) about a consumer of a
financial institution: it names the borrower, pinpoints their home, and in
context reveals their finances. Under the Gramm-Leach-Bliley Act and the
FTC Safeguards Rule those obligations flow down by contract to any vendor
that touches the data. If you are building on appraisal data, the safe
default is to never hold more PII than you need.

This module gives you three things:

* :data:`PII_FIELDS` — a documented map of which UAD 3.6 elements carry PII
  and why;
* :func:`iter_pii` — enumerate the PII actually present in a document;
* :func:`redact` / :func:`redact_package` — produce a de-identified copy
  that preserves the analytically useful structure (room inventory, level
  areas, condition/quality ratings, the sales grid) while stripping
  identity and precise location.

What redaction removes vs. keeps, by default:

=====================  ==============================================
Removed / masked        All individual names (borrower, owner, seller,
                        contacts, appraiser); street address, unit,
                        city, county, postal code; GPS coordinates;
                        license numbers; client/file identifiers.
Kept                    State code (coarse geography); every room,
                        level, area, rating, adjustment, and amount;
                        dates; company names of institutions.
Caveat                  Free-text comments are KEPT by default and can
                        contain incidental PII ("per the owner, Mr.
                        Smith…"). Pass ``redact_free_text=True`` to
                        blank them too.
=====================  ==============================================
"""

from __future__ import annotations

import posixpath
import zipfile
from dataclasses import dataclass
from os import PathLike
from typing import IO

from lxml import etree

from . import _xml as x
from .parse import XmlSource, parse_xml_tree

REDACTED = "REDACTED"


@dataclass(frozen=True)
class PiiField:
    """Documentation for one PII-bearing element."""

    element: str
    category: str
    rationale: str


PII_FIELDS: tuple[PiiField, ...] = (
    PiiField("FirstName", "identity", "Individual given name (borrower, owner, seller, contact, appraiser)."),
    PiiField("MiddleName", "identity", "Individual middle name."),
    PiiField("LastName", "identity", "Individual family name."),
    PiiField("SuffixName", "identity", "Individual name suffix."),
    PiiField("FullName", "identity", "Party full name; may be an individual (e.g. the property owner)."),
    PiiField("AddressLineText", "location", "Street address of the subject/comp — identifies the home."),
    PiiField("AddressUnitIdentifier", "location", "Unit number."),
    PiiField("CityName", "location", "City; combined with other fields, re-identifying."),
    PiiField("CountyName", "location", "County."),
    PiiField("PostalCode", "location", "ZIP code; small-area geography."),
    PiiField("LatitudeIdentifier", "location", "Precise GPS latitude — equivalent to the address."),
    PiiField("LongitudeIdentifier", "location", "Precise GPS longitude — equivalent to the address."),
    PiiField("LicenseIdentifier", "identity", "Appraiser/supervisor license number — identifies an individual."),
    PiiField("AdditionalValuationIdentifier", "identifier", "Client / vendor file numbers — linkable to loan files."),
    PiiField("DataSourceIdentifier", "identifier", "MLS or similar source id — can resolve back to the listing/address."),
    PiiField("AssessorParcelIdentifier", "identifier", "Parcel/APN — public-record key to the property."),
    PiiField("TaxParcelIdentifier", "identifier", "Tax parcel id."),
)
"""Elements treated as PII, with rationale. Matching is by element local name."""

FREE_TEXT_SUFFIXES = ("CommentText", "CommentDescription", "Description", "Text")
"""Element-name suffixes treated as free text under ``redact_free_text=True``."""

_MASKS: dict[str, str] = {
    "PostalCode": "00000",
    "LatitudeIdentifier": None,  # type: ignore[dict-item]  # element removed
    "LongitudeIdentifier": None,  # type: ignore[dict-item]
}

_PII_NAMES = {f.element for f in PII_FIELDS}


@dataclass(frozen=True)
class PiiHit:
    """One PII value found in a document."""

    element: str
    category: str
    value: str
    path: str


def iter_pii(source: XmlSource) -> list[PiiHit]:
    """List every PII value present in *source* (see :data:`PII_FIELDS`)."""
    tree = parse_xml_tree(source)
    by_name = {f.element: f for f in PII_FIELDS}
    hits: list[PiiHit] = []
    for el in tree.getroot().iter():
        if not isinstance(el.tag, str):
            continue
        name = x.local_name(el)
        if name in by_name and (value := x.text_of(el)):
            hits.append(
                PiiHit(element=name, category=by_name[name].category, value=value, path=x.element_path(el))
            )
    return hits


def redact(
    source: XmlSource,
    *,
    keep_state: bool = True,
    redact_free_text: bool = False,
) -> bytes:
    """Return a de-identified copy of a URAR XML document.

    Structure is preserved: the result re-parses with :func:`uad36.load_report`
    and keeps the full room inventory, level areas, ratings, and sales grid.
    ``StateCode`` survives unless ``keep_state=False``. Free-text comments
    survive unless ``redact_free_text=True`` (see the module caveat).

    Note: redacted documents are for analysis and data sharing, not for
    UCDP submission — masked values may violate the GSEs' conditionality
    rules even though the XML stays subschema-shaped.
    """
    tree = parse_xml_tree(source)
    root = tree.getroot()
    to_remove: list[etree._Element] = []
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        name = x.local_name(el)
        if name in _PII_NAMES:
            if name in _MASKS and _MASKS[name] is None:
                to_remove.append(el)
            elif x.text_of(el) is not None:
                el.text = _MASKS.get(name, REDACTED)
        elif name == "StateCode" and not keep_state:
            el.text = REDACTED
        elif redact_free_text and name.endswith(FREE_TEXT_SUFFIXES) and x.text_of(el) is not None:
            el.text = REDACTED
    for el in to_remove:
        parent = el.getparent()
        if parent is not None:
            parent.remove(el)
    return etree.tostring(tree, xml_declaration=True, encoding="UTF-8", pretty_print=False)


def redact_package(
    source: str | PathLike[str] | IO[bytes],
    dest: str | PathLike[str],
    *,
    keep_floor_plans: bool = True,
    keep_other_images: bool = False,
    keep_pdf: bool = False,
    keep_state: bool = True,
    redact_free_text: bool = False,
) -> list[str]:
    """Write a de-identified copy of a UCDP delivery ZIP to *dest*.

    This is the "geometry-only extract": the XML is redacted with
    :func:`redact`, floor-plan/sketch exhibits are kept (they carry the
    layout and are the point of sharing), while property photos and the PDF
    — both full of faces, addresses, and signatures — are dropped unless
    explicitly kept. Returns the member names written.
    """
    from .models import FLOOR_PLAN_CATEGORIES
    from .package import UcdpPackage

    written: list[str] = []
    with UcdpPackage.open(source) as pkg:
        keep_members: set[str] = set()
        if keep_floor_plans:
            for ref in pkg.report.exhibits.floor_plans():
                member = pkg.resolve_image(ref)
                if member:
                    keep_members.add(member)
        if keep_other_images:
            for ref in pkg.report.exhibits.images:
                if ref.category not in FLOOR_PLAN_CATEGORIES:
                    member = pkg.resolve_image(ref)
                    if member:
                        keep_members.add(member)
        if keep_pdf:
            keep_members.update(pkg.pdf_names)

        redacted_xml = redact(
            pkg.read_xml(), keep_state=keep_state, redact_free_text=redact_free_text
        )
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as out:
            out.writestr(posixpath.basename(pkg.xml_name), redacted_xml)
            written.append(posixpath.basename(pkg.xml_name))
            for member in sorted(keep_members):
                out.writestr(member, pkg.read(member))
                written.append(member)
    return written
