"""PII enumeration and redaction."""

from __future__ import annotations

from pathlib import Path

import pytest

import uad36


def test_iter_pii_finds_identity_and_location(sf2_xml: Path) -> None:
    hits = uad36.iter_pii(sf2_xml)
    values = {h.value for h in hits}
    assert "Betty" in values  # borrower first name
    assert "1234 Anywhere Pl" in values  # subject street
    categories = {h.category for h in hits}
    assert {"identity", "location"} <= categories
    assert all(h.path.startswith("/") for h in hits)


def test_redact_strips_pii_and_preserves_structure(sf2_xml: Path) -> None:
    redacted = uad36.redact(sf2_xml)
    assert b"Betty" not in redacted
    assert b"1234 Anywhere Pl" not in redacted
    assert b"LatitudeIdentifier" not in redacted  # coordinates removed outright

    original = uad36.load_report(sf2_xml)
    round_tripped = uad36.load_report(redacted)
    assert len(round_tripped.rooms) == len(original.rooms)
    assert len(round_tripped.areas) == len(original.areas)
    assert len(round_tripped.sales_comparison.comparables) == len(
        original.sales_comparison.comparables
    )
    assert round_tripped.areas.gross_living_area_sqft == original.areas.gross_living_area_sqft
    # coarse geography survives; street does not
    assert round_tripped.subject.address.state == "MD"
    assert round_tripped.subject.address.street == "REDACTED"
    assert round_tripped.subject.address.postal_code == "00000"


def test_redacted_output_still_validates(sf2_xml: Path, schemas_root: Path) -> None:
    """Masked values keep the document subschema-shaped."""
    result = uad36.validate_xml(uad36.redact(sf2_xml), schemas_root=schemas_root)
    assert result.valid, [str(f) for f in result.findings[:3]]


def test_redact_keeps_free_text_by_default(sf2_xml: Path) -> None:
    redacted = uad36.redact(sf2_xml)
    report = uad36.load_report(redacted)
    assert report.subject.primary_unit.summary.valuation_comment not in (None, "REDACTED")


def test_redact_free_text_option(sf2_xml: Path) -> None:
    redacted = uad36.redact(sf2_xml, redact_free_text=True)
    report = uad36.load_report(redacted)
    assert report.subject.primary_unit.summary.valuation_comment == "REDACTED"


def test_redact_no_pii_left_behind(sf2_xml: Path) -> None:
    """iter_pii on redacted output finds only placeholder values."""
    hits = uad36.iter_pii(uad36.redact(sf2_xml))
    leftovers = {h.value for h in hits} - {"REDACTED", "00000"}
    assert leftovers == set()


def test_redact_package_is_geometry_only(sf2_package: Path, tmp_path: Path) -> None:
    out = tmp_path / "redacted.zip"
    members = uad36.redact_package(sf2_package, out)
    # exactly: the redacted XML + the floor-plan/sketch exhibit(s); no photos, no PDF
    assert members[0].endswith(".xml")
    image_members = [m for m in members[1:]]
    assert image_members == ["Images/SF2_Sketch.png"]

    with uad36.UcdpPackage.open(out) as pkg:
        report = pkg.report
        assert len(report.rooms) == 15
        assert report.subject.address.street == "REDACTED"
        assert pkg.resolve_image(report.exhibits.floor_plans()[0]) is not None


def test_redact_package_optional_keeps(sf2_package: Path, tmp_path: Path) -> None:
    out = tmp_path / "with_pdf.zip"
    members = uad36.redact_package(sf2_package, out, keep_pdf=True, keep_other_images=True)
    assert any(m.endswith(".pdf") for m in members)
    assert sum(m.startswith("Images/") for m in members) > 1


def test_pii_field_docs_are_complete() -> None:
    for field in uad36.PII_FIELDS:
        assert field.element and field.category and field.rationale
        assert field.category in {"identity", "location", "identifier"}
