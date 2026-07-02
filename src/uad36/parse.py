"""Extract typed models from UAD 3.6 URAR XML.

Everything here is tolerant by design: lookups are namespace-agnostic and a
missing container yields empty models rather than an exception, so partial
or in-progress files still load. The only hard failure is XML that does not
parse at all (:class:`uad36.errors.MalformedXmlError`).
"""

from __future__ import annotations

import io
from os import PathLike
from pathlib import Path
from typing import BinaryIO

from lxml import etree

from . import _xml as x
from .errors import MalformedXmlError
from .models import (
    Address,
    Adjustment,
    Assignment,
    Comparable,
    Exhibits,
    ImageRef,
    Level,
    LevelAreas,
    Party,
    PropertyNotUsed,
    PropertyUnit,
    Report,
    Room,
    RoomInventory,
    SalesComparisonGrid,
    SubjectProperty,
    UnitAreas,
    UnitSummary,
)

XmlSource = str | PathLike[str] | bytes | BinaryIO


def parse_xml_tree(source: XmlSource) -> etree._ElementTree:
    """Parse *source* (path, bytes, or binary file object) into an lxml tree.

    Raises :class:`MalformedXmlError` with the underlying position info when
    the document is not well-formed.
    """
    parser = etree.XMLParser(resolve_entities=False, huge_tree=True)
    try:
        if isinstance(source, bytes):
            return etree.parse(io.BytesIO(source), parser)
        if isinstance(source, (str, PathLike)):
            return etree.parse(str(Path(source)), parser)
        return etree.parse(source, parser)
    except etree.XMLSyntaxError as exc:
        raise MalformedXmlError(str(exc)) from exc


def load_report(source: XmlSource) -> Report:
    """Parse a UAD 3.6 URAR XML document into a :class:`Report`.

    For a full UCDP delivery ZIP, use :class:`uad36.UcdpPackage` instead —
    it locates the XML for you and can resolve image references.
    """
    tree = parse_xml_tree(source)
    return report_from_tree(tree)


def report_from_tree(tree: etree._ElementTree) -> Report:
    root = tree.getroot()
    properties = list(x.iter_descendants(root, "PROPERTY"))

    subject: SubjectProperty | None = None
    comparables: list[Comparable] = []
    not_used: list[PropertyNotUsed] = []
    for prop in properties:
        use_type = prop.get("ValuationUseType")
        if use_type == "SubjectProperty":
            subject = _subject(prop)
        elif use_type == "SalesComparable":
            comparables.append(_comparable(prop))
        elif use_type == "PropertyAnalyzedNotUsed":
            not_used.append(_property_not_used(prop))
    comparables.sort(key=lambda c: (c.ordinal is None, c.ordinal))
    not_used.sort(key=lambda p: (p.ordinal is None, p.ordinal))

    grid = SalesComparisonGrid(
        subject=subject,
        comparables=comparables,
        analyzed_not_used=not_used,
        indicated_value=_first_decimal(root, "ValueIndicatedBySalesComparisonAmount"),
        comment=x.descendant_text(root, "SalesComparisonCommentDescription"),
    )

    return Report(
        mismo_reference_model=root.get("MISMOReferenceModelIdentifier"),
        about_versions=[
            t for el in x.iter_descendants(root, "AboutVersionIdentifier") if (t := x.text_of(el))
        ],
        assignment=_assignment(root),
        subject=subject,
        sales_comparison=grid,
        exhibits=_exhibits(root),
        pdf_reference=_pdf_reference(root),
    )


# --------------------------------------------------------------------------
# Pieces
# --------------------------------------------------------------------------


def _first_decimal(root: etree._Element, name: str) -> float | None:
    raw = x.descendant_text(root, name)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _address(el: etree._Element) -> Address | None:
    """ADDRESS (+ sibling GEOSPATIAL_INFORMATION) directly under *el*."""
    addr_el = x.find_child(el, "ADDRESS")
    if addr_el is None:
        return None
    geo = x.find_descendant(el, "GEOSPATIAL_INFORMATION")
    return Address(
        street=x.child_text(addr_el, "AddressLineText"),
        unit_designator=x.child_text(addr_el, "AddressUnitDesignatorType"),
        unit=x.child_text(addr_el, "AddressUnitIdentifier"),
        city=x.child_text(addr_el, "CityName"),
        county=x.child_text(addr_el, "CountyName"),
        state=x.child_text(addr_el, "StateCode"),
        postal_code=x.child_text(addr_el, "PostalCode"),
        latitude=x.child_text(geo, "LatitudeIdentifier") if geo is not None else None,
        longitude=x.child_text(geo, "LongitudeIdentifier") if geo is not None else None,
    )


def _image(el: etree._Element) -> ImageRef | None:
    raw = x.child_text(el, "ImageFileLocationIdentifier")
    if raw is None:
        return None
    return ImageRef(
        file_name=x.normalize_object_path(raw),
        raw_location=raw,
        mime_type=x.child_text(el, "MIMETypeIdentifier"),
        caption=x.child_text(el, "ImageCaptionCommentDescription"),
        category=x.child_text(el, "ImageCategoryType"),
        taken_at=x.child_text(el, "ImageDatetime"),
    )


def _room(el: etree._Element) -> Room:
    detail = x.find_child(el, "ROOM_DETAIL")
    images = [img for i in x.iter_descendants(el, "IMAGE") if (img := _image(i))]
    if detail is None:
        return Room(images=images)
    return Room(
        room_type=x.child_text(detail, "RoomType"),
        level_type=x.child_text(detail, "LevelType"),
        condition_status=x.child_text(detail, "RoomConditionStatusType"),
        condition_comment=x.child_text(detail, "RoomConditionAdditionalDescription"),
        quality_comment=x.child_text(detail, "RoomQualityDescription"),
        update_status=x.child_text(detail, "RoomUpdateStatusType"),
        images=images,
    )


def _level(el: etree._Element) -> Level:
    finished = x.find_child(el, "LevelFinishedAreaMeasure")
    unfinished = x.find_child(el, "LevelUnfinishedAreaMeasure")
    unit = None
    for measure in (finished, unfinished):
        if measure is not None and measure.get("AreaUnitOfMeasureType"):
            unit = measure.get("AreaUnitOfMeasureType")
            break

    def _num(measure: etree._Element | None) -> float | None:
        raw = x.text_of(measure)
        if raw is None:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    return Level(
        level_type=x.child_text(el, "LevelType"),
        grade_level_type=x.child_text(el, "GradeLevelType"),
        finished_area_sqft=_num(finished),
        unfinished_area_sqft=_num(unfinished),
        area_unit=unit,
        access_type=x.child_text(el, "AccessType"),
        below_grade_exterior_access=x.child_text(el, "BelowGradeExteriorAccessType"),
    )


def _unit_areas(el: etree._Element) -> UnitAreas | None:
    area_el = x.find_child(el, "PROPERTY_UNIT_AREA")
    if area_el is None:
        return None
    return UnitAreas(
        standard_above_grade_finished=x.child_decimal(area_el, "UnitStandardAboveGradeFinishedAreaMeasure"),
        nonstandard_above_grade_finished=x.child_decimal(area_el, "UnitNonStandardAboveGradeFinishedAreaMeasure"),
        above_grade_unfinished=x.child_decimal(area_el, "UnitAboveGradeUnfinishedAreaMeasure"),
        standard_below_grade_finished=x.child_decimal(area_el, "UnitStandardBelowGradeFinishedAreaMeasure"),
        nonstandard_below_grade_finished=x.child_decimal(area_el, "UnitNonStandardBelowGradeFinishedAreaMeasure"),
        below_grade_unfinished=x.child_decimal(area_el, "UnitBelowGradeUnfinishedAreaMeasure"),
    )


def _unit_summary(el: etree._Element) -> UnitSummary | None:
    detail = x.find_child(el, "PROPERTY_UNIT_DETAIL")
    if detail is None:
        return None
    adu = x.child_text(detail, "AccessoryDwellingUnitIndicator")
    return UnitSummary(
        bedroom_count=x.child_int(detail, "BedroomCount"),
        full_bathroom_count=x.child_int(detail, "FullBathroomCount"),
        half_bathroom_count=x.child_int(detail, "HalfBathroomCount"),
        level_count=x.child_int(detail, "LevelCount"),
        interior_condition_rating=x.child_text(detail, "InteriorConditionRatingCode"),
        interior_quality_rating=x.child_text(detail, "InteriorQualityRatingCode"),
        occupancy=x.child_text(detail, "UnitOccupancyType"),
        is_adu=None if adu is None else adu.lower() == "true",
        valuation_comment=x.child_text(detail, "UnitValuationCommentText"),
    )


def _property_unit(el: etree._Element) -> PropertyUnit:
    rooms_el = x.find_child(el, "ROOMS")
    levels_el = x.find_child(el, "LEVELS")
    return PropertyUnit(
        label=el.get(f"{{{x.XLINK_NS}}}label"),
        summary=_unit_summary(el),
        rooms=RoomInventory(
            rooms=[_room(r) for r in x.iter_children(rooms_el, "ROOM")] if rooms_el is not None else []
        ),
        areas=LevelAreas(
            levels=[_level(lv) for lv in x.iter_children(levels_el, "LEVEL")] if levels_el is not None else [],
            unit_areas=_unit_areas(el),
        ),
    )


def _property_units(prop: etree._Element) -> list[PropertyUnit]:
    return [_property_unit(u) for u in x.iter_descendants(prop, "PROPERTY_UNIT")]


def _subject(prop: etree._Element) -> SubjectProperty:
    return SubjectProperty(address=_address(prop), units=_property_units(prop))


def _comparable(prop: etree._Element) -> Comparable:
    detail = x.find_descendant(prop, "COMPARABLE_DETAIL")
    listing = x.find_descendant(prop, "LISTING_INFORMATION_DETAIL")
    sales_history = x.find_descendant(prop, "SALES_HISTORY")
    units = _property_units(prop)

    proximity = None
    direction = None
    ordinal = None
    adjusted = None
    per_sqft = None
    net_total = None
    weight = None
    if detail is not None:
        ordinal = x.child_int(detail, "PropertyOrdinalNumber")
        adjusted = x.child_decimal(detail, "AdjustedSalesPriceAmount")
        per_sqft = x.child_decimal(detail, "PricePerTotalStandardAboveGradeFinishedAreaAmount")
        net_total = x.child_decimal(detail, "SalePriceNetTotalAdjustmentAmount")
        weight = x.child_text(detail, "ComparableWeightType")
        direction = x.child_text(detail, "ComparableToSubjectDirectionType")
        proximity = x.child_decimal(detail, "ProximityToSubjectDistanceLinearMeasure")

    adjustments = [
        Adjustment(
            adjustment_type=x.child_text(adj, "ComparableAdjustmentType"),
            amount=x.child_decimal(adj, "ComparableAdjustmentAmount"),
            description=x.child_text(adj, "ComparableAdjustmentTypeOtherDescription"),
        )
        for adj in x.iter_descendants(prop, "COMPARABLE_ADJUSTMENT")
    ]

    return Comparable(
        ordinal=ordinal,
        address=_address(prop),
        sale_price=(
            x.child_decimal(sales_history, "OwnershipTransferTransactionAmount")
            if sales_history is not None
            else None
        ),
        adjusted_sale_price=adjusted,
        price_per_gla_sqft=per_sqft,
        net_adjustment_total=net_total,
        proximity_miles=proximity,
        direction_from_subject=direction,
        weight=weight,
        listing_status=x.child_text(listing, "ListingStatusType") if listing is not None else None,
        sales_contract_date=x.descendant_text(prop, "SalesContractDate"),
        ownership_transfer_date=(
            x.child_text(sales_history, "OwnershipTransferDate") if sales_history is not None else None
        ),
        unit=units[0] if units else None,
        adjustments=adjustments,
    )


def _property_not_used(prop: etree._Element) -> PropertyNotUsed:
    detail = x.find_descendant(prop, "PROPERTY_NOT_USED_DETAIL")
    listing = x.find_descendant(prop, "LISTING_INFORMATION_DETAIL")
    consideration = x.child_text(detail, "ConsiderationRequestedIndicator") if detail is not None else None
    return PropertyNotUsed(
        ordinal=x.child_int(d, "PropertyOrdinalNumber")
        if (d := x.find_descendant(prop, "COMPARABLE_DETAIL")) is not None
        else None,
        address=_address(prop),
        reasons=[
            t for el in x.iter_descendants(prop, "ReasonPropertyNotUsedType") if (t := x.text_of(el))
        ],
        explanation=(
            x.child_text(detail, "AdditionalPropertyAnalyzedNotUsedText") if detail is not None else None
        ),
        consideration_requested=None if consideration is None else consideration.lower() == "true",
        listing_status=x.child_text(listing, "ListingStatusType") if listing is not None else None,
    )


def _exhibits(root: etree._Element) -> Exhibits:
    images: list[ImageRef] = []
    seen: set[str] = set()
    for el in x.iter_descendants(root, "IMAGE"):
        img = _image(el)
        if img is None:
            continue
        key = img.raw_location + "|" + (img.category or "")
        if key in seen:
            continue
        seen.add(key)
        images.append(img)
    return Exhibits(images=images)


def _pdf_reference(root: etree._Element) -> str | None:
    for obj in x.iter_descendants(root, "FOREIGN_OBJECT"):
        url = x.child_text(obj, "ObjectURL")
        mime = x.child_text(obj, "MIMETypeIdentifier")
        if url and (mime is None or "pdf" in mime.lower()):
            return x.normalize_object_path(url)
    return None


def _party(el: etree._Element) -> Party:
    name_el = x.find_descendant(el, "NAME")
    individual_name = None
    if name_el is not None:
        parts = [
            x.child_text(name_el, "FirstName"),
            x.child_text(name_el, "MiddleName"),
            x.child_text(name_el, "LastName"),
            x.child_text(name_el, "SuffixName"),
        ]
        individual_name = " ".join(p for p in parts if p) or None

    legal = x.find_descendant(el, "LEGAL_ENTITY_DETAIL")
    company = x.child_text(legal, "FullName") if legal is not None else None
    company = company or x.descendant_text(el, "AppraiserCompanyName")

    license_detail = x.find_descendant(el, "LICENSE_DETAIL")
    return Party(
        roles=[t for r in x.iter_descendants(el, "PartyRoleType") if (t := x.text_of(r))],
        individual_name=individual_name,
        company_name=company,
        license_id=x.child_text(license_detail, "LicenseIdentifier") if license_detail is not None else None,
        license_state=(
            x.child_text(license_detail, "LicenseIssuingAuthorityStateCode")
            if license_detail is not None
            else None
        ),
    )


def _assignment(root: etree._Element) -> Assignment:
    parties = [_party(p) for p in x.iter_descendants(root, "PARTY")]
    signed = None
    for sig in x.iter_descendants(root, "SIGNATORY"):
        signed = x.descendant_text(sig, "ExecutionDate") or signed
    return Assignment(
        assignment_type=x.descendant_text(root, "ValuationAssignmentType"),
        effective_date=x.descendant_text(root, "AppraisalReportEffectiveDate"),
        signed_date=signed,
        opinion_of_value=_first_decimal(root, "OpinionOfValueAmount"),
        parties=parties,
    )
