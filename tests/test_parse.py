"""Parsing the GSE Appendix D-1 samples into typed models."""

from __future__ import annotations

from pathlib import Path

import pytest

import uad36


@pytest.fixture(scope="module")
def sf2_report(sf2_xml: Path) -> uad36.Report:
    return uad36.load_report(sf2_xml)


@pytest.fixture(scope="module")
def condo1_report(condo1_xml: Path) -> uad36.Report:
    return uad36.load_report(condo1_xml)


class TestSF2:
    """SF2: 5BR/4.5BA four-level single-family with a below-grade level."""

    @pytest.fixture
    def report(self, sf2_report: uad36.Report) -> uad36.Report:
        return sf2_report

    def test_assignment(self, report: uad36.Report) -> None:
        a = report.assignment
        assert a.assignment_type == "Purchase"
        assert a.effective_date == "2019-08-07"
        assert a.opinion_of_value == 880000
        assert a.appraiser is not None and a.appraiser.company_name == "XYZ Appraisal Company"
        assert any(p.individual_name == "Betty Borrower" for p in a.borrowers)

    def test_message_metadata(self, report: uad36.Report) -> None:
        assert report.mismo_reference_model == "3.6.0366"
        assert report.pdf_reference == "SF2_Appraisal_v1.4.pdf"

    def test_room_inventory(self, report: uad36.Report) -> None:
        rooms = report.rooms
        assert len(rooms) == 15
        counts = rooms.counts_by_type()
        assert counts["Bedroom"] == 5
        assert counts["FullBathroom"] == 4
        assert counts["Kitchen"] == 1
        assert len(rooms.on_level("BelowGradeOne")) == 3  # Den, Bedroom, FullBathroom
        kitchen = rooms.of_type("Kitchen")[0]
        assert kitchen.level_type == "LevelOne"

    def test_room_condition_detail(self, report: uad36.Report) -> None:
        bath = report.rooms.of_type("FullBathroom")[0]
        assert bath.condition_status == "TypicalWearAndTear"
        assert bath.update_status == "NotUpdated"
        assert bath.quality_comment is not None

    def test_level_areas(self, report: uad36.Report) -> None:
        areas = report.areas
        assert len(areas) == 4
        by_type = {lv.level_type: lv for lv in areas}
        assert by_type["BelowGradeOne"].finished_area_sqft == 720
        assert by_type["BelowGradeOne"].unfinished_area_sqft == 72
        assert by_type["BelowGradeOne"].grade_level_type == "PartiallyBelowGrade"
        assert by_type["LevelOne"].finished_area_sqft == 1248
        assert areas.gross_living_area_sqft == 3308
        assert areas.total_finished_sqft == 720 + 1248 + 1224 + 836
        assert all(lv.area_unit == "SquareFeet" for lv in areas)

    def test_unit_summary(self, report: uad36.Report) -> None:
        summary = report.subject.primary_unit.summary
        assert summary is not None
        assert summary.bedroom_count == 5
        assert summary.full_bathroom_count == 4
        assert summary.half_bathroom_count == 1
        assert summary.interior_condition_rating == "C3"
        assert summary.interior_quality_rating == "Q2"

    def test_sales_comparison_grid(self, report: uad36.Report) -> None:
        grid = report.sales_comparison
        assert len(grid.comparables) == 5
        assert grid.indicated_value == 880000
        assert [c.ordinal for c in grid.comparables] == [1, 2, 3, 4, 5]
        first = grid.comparables[0]
        assert first.adjusted_sale_price == 870000
        assert first.weight == "Most"
        assert first.proximity_miles == pytest.approx(0.09)
        assert first.adjustments, "comparable should carry adjustment line items"
        assert first.address is not None and first.address.state == "MD"

    def test_exhibits(self, report: uad36.Report) -> None:
        plans = report.exhibits.floor_plans()
        assert [p.category for p in plans] == ["SubjectPropertyImprovementSketch"]
        assert plans[0].file_name == "Images/SF2_Sketch.png"
        # raw value in the XML is Windows-style; normalization is on us
        assert "\\" in plans[0].raw_location


class TestCondo1:
    """Condo1: carries a FloorPlan exhibit and 5 analyzed-but-not-used entries."""

    @pytest.fixture
    def report(self, condo1_report: uad36.Report) -> uad36.Report:
        return condo1_report

    def test_analyzed_not_used(self, report: uad36.Report) -> None:
        entries = report.sales_comparison.analyzed_not_used
        assert len(entries) == 5
        first = entries[0]
        assert first.reasons, "structured ReasonPropertyNotUsedType values expected"
        assert first.explanation is not None
        assert first.address is not None and first.address.street is not None

    def test_floor_plan_exhibit(self, report: uad36.Report) -> None:
        categories = {p.category for p in report.exhibits.floor_plans()}
        assert categories == {"FloorPlan"}

    def test_comparables(self, report: uad36.Report) -> None:
        grid = report.sales_comparison
        assert len(grid.comparables) == 4
        assert grid.comparables[0].sale_price == 778000


def test_all_scenarios_parse(all_sample_xml: list[Path]) -> None:
    """Every published GSE scenario loads: subject, rooms, levels, and a grid."""
    assert len(all_sample_xml) >= 12
    for path in all_sample_xml:
        report = uad36.load_report(path)
        assert report.subject is not None, path.name
        assert len(report.rooms) > 0, path.name
        assert len(report.areas) > 0, path.name
        assert report.sales_comparison.comparables, path.name
        assert report.assignment.effective_date or report.assignment.signed_date, path.name


def test_malformed_xml_raises() -> None:
    with pytest.raises(uad36.MalformedXmlError):
        uad36.load_report(b"<MESSAGE><unclosed>")


def test_non_urar_xml_degrades_gracefully() -> None:
    """Well-formed XML that is not a URAR yields an empty-but-usable Report."""
    report = uad36.load_report(b"<root><child/></root>")
    assert report.subject is None
    assert len(report.rooms) == 0
    assert report.sales_comparison.comparables == []
