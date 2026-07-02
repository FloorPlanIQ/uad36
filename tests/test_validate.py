"""Structural validation against the fetched GSE subschema."""

from __future__ import annotations

from pathlib import Path

import pytest

import uad36
from uad36.fetch import find_schema_xsd


def test_gse_samples_validate(all_sample_xml: list[Path], schemas_root: Path) -> None:
    """Every published GSE scenario conforms to the published subschema."""
    for path in all_sample_xml:
        result = uad36.validate_xml(path, schemas_root=schemas_root)
        assert result.valid, f"{path.name}: {[str(f) for f in result.findings[:3]]}"


def test_malformed_is_reported_not_raised(schemas_root: Path) -> None:
    result = uad36.validate_xml(b"<MESSAGE><unclosed>", schemas_root=schemas_root)
    assert not result.well_formed
    assert not result.valid
    assert result.findings[0].severity == "fatal"
    assert result.summary() == "not well-formed XML"


def test_schema_violation_yields_readable_finding(sf2_xml: Path, schemas_root: Path) -> None:
    # inject an element the subschema does not allow
    mutated = sf2_xml.read_bytes().replace(
        b"<RoomType>Den</RoomType>", b"<RoomType>Den</RoomType><NotARealElement/>"
    )
    result = uad36.validate_xml(mutated, schemas_root=schemas_root)
    assert result.well_formed and result.schema_checked
    assert not result.valid
    finding = result.findings[0]
    assert finding.line is not None
    assert "NotARealElement" in finding.message
    # namespace clutter stripped for readability
    assert "{http://www.mismo.org" not in finding.message


def test_bad_enum_value_is_caught(sf2_xml: Path, schemas_root: Path) -> None:
    mutated = sf2_xml.read_bytes().replace(
        b"<RoomType>Kitchen</RoomType>", b"<RoomType>Kitchenette</RoomType>"
    )
    result = uad36.validate_xml(mutated, schemas_root=schemas_root)
    assert not result.valid
    assert any("Kitchenette" in f.message for f in result.findings)


def test_missing_schema_degrades_when_allowed(sf2_xml: Path, tmp_path: Path) -> None:
    result = uad36.validate_xml(sf2_xml, schemas_root=tmp_path, require_schema=False)
    assert result.well_formed
    assert not result.schema_checked
    assert result.summary() == "well-formed (schema not checked)"


def test_missing_schema_raises_by_default(sf2_xml: Path, tmp_path: Path) -> None:
    with pytest.raises(uad36.SchemaNotAvailableError, match="fetch-schemas"):
        uad36.validate_xml(sf2_xml, schemas_root=tmp_path)


def test_schema_discovery_prefers_root_xsd(schemas_root: Path) -> None:
    xsd = find_schema_xsd(schemas_root)
    assert xsd is not None
    assert "xlink" not in xsd.name
    assert xsd.name.startswith("GSE_UAD_")
