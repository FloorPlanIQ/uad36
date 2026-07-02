"""UCDP delivery ZIP handling."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

import uad36


def test_open_and_locate_members(sf2_package: Path) -> None:
    with uad36.UcdpPackage.open(sf2_package) as pkg:
        assert pkg.xml_name.endswith(".xml")
        assert pkg.pdf_names and pkg.pdf_names[0].endswith(".pdf")
        assert pkg.image_names, "delivery should contain images"
        assert not pkg.exceeds_ucdp_size_limit


def test_report_parses_from_zip(sf2_package: Path) -> None:
    with uad36.UcdpPackage.open(sf2_package) as pkg:
        report = pkg.report
        assert len(report.rooms) == 15
        assert report.pdf_reference == "SF2_Appraisal_v1.4.pdf"
        # every image the XML references must resolve to a ZIP member,
        # despite the Windows-style backslash paths in the XML
        assert pkg.missing_images() == []


def test_extract_floor_plans(sf2_package: Path, tmp_path: Path) -> None:
    with uad36.UcdpPackage.open(sf2_package) as pkg:
        written = pkg.extract_floor_plans(tmp_path)
    assert [p.name for p in written] == ["SF2_Sketch.png"]
    assert written[0].stat().st_size > 0


def test_extract_by_category(condo1_package: Path, tmp_path: Path) -> None:
    with uad36.UcdpPackage.open(condo1_package) as pkg:
        written = pkg.extract_exhibits(tmp_path, categories=("FloorPlan",))
    assert len(written) == 1


def test_all_sample_packages_open(all_sample_packages: list[Path]) -> None:
    for path in all_sample_packages:
        with uad36.UcdpPackage.open(path) as pkg:
            assert pkg.report.subject is not None, path.name
            assert pkg.pdf_names, path.name


def test_not_a_zip_raises(tmp_path: Path) -> None:
    bogus = tmp_path / "not_a_zip.zip"
    bogus.write_bytes(b"definitely not a zip")
    with pytest.raises(uad36.PackageError, match="not a readable ZIP"):
        uad36.UcdpPackage.open(bogus)


def test_zip_without_xml_raises() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("report.pdf", b"%PDF-1.4 fake")
    buffer.seek(0)
    with pytest.raises(uad36.PackageError, match="no XML data file"):
        uad36.UcdpPackage.open(buffer)


def test_zip_with_malformed_xml_raises_readably() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("broken.xml", b"<MESSAGE><oops>")
    buffer.seek(0)
    pkg = uad36.UcdpPackage.open(buffer)
    with pytest.raises(uad36.MalformedXmlError, match="broken.xml"):
        _ = pkg.report
