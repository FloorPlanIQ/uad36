"""Typed models for the parsed UAD 3.6 URAR.

Deliberate design notes:

* Enumerated UAD values (``RoomType``, ``LevelType``, condition ratings, …)
  are carried as plain strings, not Python enums. Two reasons: the value
  lists belong to the GSE/MISMO specification (this package ships no
  schema-derived artifacts), and real-world files should degrade gracefully
  rather than explode on an unexpected value. Validate against the fetched
  GSE subschema when you need strictness (see :mod:`uad36.validate`).
* Every model tolerates missing fields (``None``), because partial and
  in-progress URAR XML is a normal thing to hold.
"""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, ConfigDict


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------
# Shared leaf models
# --------------------------------------------------------------------------


class Address(_Model):
    """A property or party address. Most fields here are PII — see uad36.pii."""

    street: str | None = None
    unit_designator: str | None = None
    unit: str | None = None
    city: str | None = None
    county: str | None = None
    state: str | None = None
    postal_code: str | None = None
    latitude: str | None = None
    longitude: str | None = None

    def one_line(self) -> str:
        unit = f" {self.unit_designator or 'Unit'} {self.unit}" if self.unit else ""
        bits = [f"{self.street}{unit}" if self.street else None, self.city, self.state, self.postal_code]
        return ", ".join(b for b in bits if b)


class ImageRef(_Model):
    """A reference from the XML to an image file inside the delivery ZIP."""

    file_name: str
    """ZIP-relative POSIX path (normalized from the raw Windows-style value)."""
    raw_location: str
    """Verbatim ``ImageFileLocationIdentifier`` from the XML."""
    mime_type: str | None = None
    caption: str | None = None
    category: str | None = None
    """``ImageCategoryType`` when present (e.g. ``FloorPlan``, ``PropertyPhoto``)."""
    taken_at: str | None = None


# --------------------------------------------------------------------------
# Room inventory
# --------------------------------------------------------------------------


class Room(_Model):
    """One ``ROOM`` entry: a room type on a level, with condition/quality detail.

    UAD 3.6 gives you the room *inventory* only — there is no geometry,
    no dimensions, and no adjacency anywhere in the XML. The floor plan
    layout itself ships solely as an image exhibit (see :class:`Exhibits`).
    """

    room_type: str | None = None
    level_type: str | None = None
    condition_status: str | None = None
    condition_comment: str | None = None
    quality_comment: str | None = None
    update_status: str | None = None
    images: list[ImageRef] = []


class RoomInventory(_Model):
    """All rooms of one property unit (``PROPERTY_UNIT/ROOMS``)."""

    rooms: list[Room] = []

    def __len__(self) -> int:
        return len(self.rooms)

    def __iter__(self):  # type: ignore[override]
        return iter(self.rooms)

    def counts_by_type(self) -> dict[str, int]:
        return dict(Counter(r.room_type or "Unknown" for r in self.rooms))

    def counts_by_level(self) -> dict[str, int]:
        return dict(Counter(r.level_type or "Unknown" for r in self.rooms))

    def on_level(self, level_type: str) -> list[Room]:
        return [r for r in self.rooms if r.level_type == level_type]

    def of_type(self, room_type: str) -> list[Room]:
        return [r for r in self.rooms if r.room_type == room_type]


# --------------------------------------------------------------------------
# Levels and areas
# --------------------------------------------------------------------------


class Level(_Model):
    """One ``LEVEL``: ANSI Z765-style per-level finished/unfinished areas."""

    level_type: str | None = None
    grade_level_type: str | None = None
    finished_area_sqft: float | None = None
    unfinished_area_sqft: float | None = None
    area_unit: str | None = None
    access_type: str | None = None
    below_grade_exterior_access: str | None = None


class UnitAreas(_Model):
    """The six ``PROPERTY_UNIT_AREA`` roll-ups (all in square feet)."""

    standard_above_grade_finished: float | None = None
    """Standard above-grade finished area — the GLA in the UAD 3.6 sense."""
    nonstandard_above_grade_finished: float | None = None
    above_grade_unfinished: float | None = None
    standard_below_grade_finished: float | None = None
    nonstandard_below_grade_finished: float | None = None
    below_grade_unfinished: float | None = None


class LevelAreas(_Model):
    """Per-level areas plus the unit-level roll-ups for one property unit."""

    levels: list[Level] = []
    unit_areas: UnitAreas | None = None

    def __len__(self) -> int:
        return len(self.levels)

    def __iter__(self):  # type: ignore[override]
        return iter(self.levels)

    @property
    def total_finished_sqft(self) -> float | None:
        vals = [lv.finished_area_sqft for lv in self.levels if lv.finished_area_sqft is not None]
        return sum(vals) if vals else None

    @property
    def gross_living_area_sqft(self) -> float | None:
        """Standard above-grade finished area, when the roll-up is present."""
        return self.unit_areas.standard_above_grade_finished if self.unit_areas else None


# --------------------------------------------------------------------------
# Property units and properties
# --------------------------------------------------------------------------


class UnitSummary(_Model):
    """``PROPERTY_UNIT_DETAIL``: counts, C/Q ratings, occupancy."""

    bedroom_count: int | None = None
    full_bathroom_count: int | None = None
    half_bathroom_count: int | None = None
    level_count: int | None = None
    interior_condition_rating: str | None = None
    """UAD condition code C1–C6 (``InteriorConditionRatingCode``)."""
    interior_quality_rating: str | None = None
    """UAD quality code Q1–Q6 (``InteriorQualityRatingCode``)."""
    occupancy: str | None = None
    is_adu: bool | None = None
    valuation_comment: str | None = None


class PropertyUnit(_Model):
    """One dwelling unit: summary + room inventory + level areas."""

    label: str | None = None
    """xlink:label when present (e.g. ``PROPERTY_UNIT_PRIMARY_DWELLING``)."""
    summary: UnitSummary | None = None
    rooms: RoomInventory = RoomInventory()
    areas: LevelAreas = LevelAreas()


class SubjectProperty(_Model):
    """The ``PROPERTY ValuationUseType="SubjectProperty"`` element."""

    address: Address | None = None
    units: list[PropertyUnit] = []

    @property
    def primary_unit(self) -> PropertyUnit | None:
        return self.units[0] if self.units else None

    @property
    def rooms(self) -> RoomInventory:
        """Room inventory of the primary unit (the common single-unit case)."""
        return self.primary_unit.rooms if self.primary_unit else RoomInventory()

    @property
    def areas(self) -> LevelAreas:
        """Level areas of the primary unit (the common single-unit case)."""
        return self.primary_unit.areas if self.primary_unit else LevelAreas()


# --------------------------------------------------------------------------
# Sales comparison grid
# --------------------------------------------------------------------------


class Adjustment(_Model):
    """One ``COMPARABLE_ADJUSTMENT`` line item."""

    adjustment_type: str | None = None
    amount: float | None = None
    description: str | None = None


class Comparable(_Model):
    """A ``PROPERTY ValuationUseType="SalesComparable"`` entry in the grid."""

    ordinal: int | None = None
    address: Address | None = None
    sale_price: float | None = None
    """Closed price when available (``OwnershipTransferTransactionAmount``)."""
    adjusted_sale_price: float | None = None
    price_per_gla_sqft: float | None = None
    net_adjustment_total: float | None = None
    proximity_miles: float | None = None
    direction_from_subject: str | None = None
    weight: str | None = None
    """``ComparableWeightType`` (e.g. Most / Equal / Least)."""
    listing_status: str | None = None
    sales_contract_date: str | None = None
    ownership_transfer_date: str | None = None
    unit: PropertyUnit | None = None
    """Comp room inventory / areas, when delivered."""
    adjustments: list[Adjustment] = []

    def adjustment(self, adjustment_type: str) -> Adjustment | None:
        return next((a for a in self.adjustments if a.adjustment_type == adjustment_type), None)


class PropertyNotUsed(_Model):
    """An "Additional Properties Analyzed But Not Used" entry.

    New in UAD 3.6: properties the appraiser considered and documented
    excluding, with structured reasons (``ReasonPropertyNotUsedType``) and
    a free-text explanation. Carried in
    ``PROPERTY ValuationUseType="PropertyAnalyzedNotUsed"``.
    """

    ordinal: int | None = None
    address: Address | None = None
    reasons: list[str] = []
    explanation: str | None = None
    consideration_requested: bool | None = None
    listing_status: str | None = None


class SalesComparisonGrid(_Model):
    """Subject + comparables + analyzed-but-not-used entries, plus grid-level facts."""

    subject: SubjectProperty | None = None
    comparables: list[Comparable] = []
    analyzed_not_used: list[PropertyNotUsed] = []
    indicated_value: float | None = None
    """``ValueIndicatedBySalesComparisonAmount``."""
    comment: str | None = None


# --------------------------------------------------------------------------
# Exhibits
# --------------------------------------------------------------------------

FLOOR_PLAN_CATEGORIES = ("FloorPlan", "SubjectPropertyImprovementSketch")
"""``ImageCategoryType`` values that carry the floor-plan layout.

The layout is NOT in the XML data — these image exhibits are the only place
the floor plan itself ships in a UAD 3.6 delivery.
"""


class Exhibits(_Model):
    """Every image referenced by the report, with category metadata."""

    images: list[ImageRef] = []

    def __len__(self) -> int:
        return len(self.images)

    def __iter__(self):  # type: ignore[override]
        return iter(self.images)

    def by_category(self, category: str) -> list[ImageRef]:
        return [i for i in self.images if i.category == category]

    def floor_plans(self) -> list[ImageRef]:
        """Floor-plan and improvement-sketch exhibits (the layout carriers)."""
        return [i for i in self.images if i.category in FLOOR_PLAN_CATEGORIES]

    def categories(self) -> dict[str, int]:
        return dict(Counter(i.category or "(uncategorized)" for i in self.images))


# --------------------------------------------------------------------------
# Assignment & report
# --------------------------------------------------------------------------


class Party(_Model):
    """A ``PARTY`` with its roles. Individual names are PII — see uad36.pii."""

    roles: list[str] = []
    individual_name: str | None = None
    company_name: str | None = None
    license_id: str | None = None
    license_state: str | None = None


class Assignment(_Model):
    """Assignment-level attributes gathered from across the document."""

    assignment_type: str | None = None
    """``ValuationAssignmentType`` (Purchase / Refinance / …)."""
    effective_date: str | None = None
    """``AppraisalReportEffectiveDate``."""
    signed_date: str | None = None
    """Appraiser signature ``ExecutionDate``."""
    opinion_of_value: float | None = None
    """``OpinionOfValueAmount``."""
    parties: list[Party] = []

    def parties_in_role(self, role: str) -> list[Party]:
        return [p for p in self.parties if role in p.roles]

    @property
    def appraiser(self) -> Party | None:
        found = self.parties_in_role("Appraiser")
        return found[0] if found else None

    @property
    def borrowers(self) -> list[Party]:
        return self.parties_in_role("Borrower")

    @property
    def lender(self) -> Party | None:
        found = self.parties_in_role("Lender")
        return found[0] if found else None


class Report(_Model):
    """A parsed UAD 3.6 URAR.

    Produced by :func:`uad36.load_report` (bare XML) or via
    :class:`uad36.UcdpPackage` (the full delivery ZIP).
    """

    mismo_reference_model: str | None = None
    """``MISMOReferenceModelIdentifier`` attribute on ``MESSAGE``."""
    about_versions: list[str] = []
    assignment: Assignment = Assignment()
    subject: SubjectProperty | None = None
    sales_comparison: SalesComparisonGrid = SalesComparisonGrid()
    exhibits: Exhibits = Exhibits()
    pdf_reference: str | None = None
    """ZIP-relative path of the human-readable PDF (``FOREIGN_OBJECT/ObjectURL``)."""

    @property
    def rooms(self) -> RoomInventory:
        """Subject room inventory (primary unit) — shortcut for the common case."""
        return self.subject.rooms if self.subject else RoomInventory()

    @property
    def areas(self) -> LevelAreas:
        """Subject level areas (primary unit) — shortcut for the common case."""
        return self.subject.areas if self.subject else LevelAreas()
