"""uad36 — unofficial parser for UAD 3.6 URAR XML and UCDP delivery ZIPs.

Quickstart::

    import uad36

    with uad36.UcdpPackage.open("delivery.zip") as pkg:
        report = pkg.report
        print(report.subject.address.one_line())
        print(report.rooms.counts_by_type())
        pkg.extract_floor_plans("exhibits/")

    report = uad36.load_report("appraisal.xml")   # bare XML works too

This package parses the publicly published GSE (Fannie Mae / Freddie Mac)
UAD 3.6 specification. It is not affiliated with, or endorsed by, Fannie
Mae, Freddie Mac, or MISMO, and it ships no schema files — run
``uad36 fetch-schemas`` to download the free GSE subschema for validation.
"""

from .errors import (
    FetchError,
    MalformedXmlError,
    PackageError,
    SchemaNotAvailableError,
    Uad36Error,
)
from .fetch import fetch_samples, fetch_schemas
from .models import (
    Address,
    Adjustment,
    Assignment,
    Comparable,
    Exhibits,
    FLOOR_PLAN_CATEGORIES,
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
from .package import UCDP_MAX_SIZE_BYTES, UcdpPackage, load_package
from .parse import load_report
from .pii import PII_FIELDS, PiiField, PiiHit, iter_pii, redact, redact_package
from .validate import Finding, ValidationResult, validate_xml

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # loading
    "load_report",
    "load_package",
    "UcdpPackage",
    "UCDP_MAX_SIZE_BYTES",
    # models
    "Report",
    "Assignment",
    "Party",
    "SubjectProperty",
    "PropertyUnit",
    "UnitSummary",
    "UnitAreas",
    "Room",
    "RoomInventory",
    "Level",
    "LevelAreas",
    "SalesComparisonGrid",
    "Comparable",
    "Adjustment",
    "PropertyNotUsed",
    "Exhibits",
    "ImageRef",
    "Address",
    "FLOOR_PLAN_CATEGORIES",
    # validation
    "validate_xml",
    "ValidationResult",
    "Finding",
    # PII
    "PII_FIELDS",
    "PiiField",
    "PiiHit",
    "iter_pii",
    "redact",
    "redact_package",
    # fetch
    "fetch_schemas",
    "fetch_samples",
    # errors
    "Uad36Error",
    "MalformedXmlError",
    "PackageError",
    "SchemaNotAvailableError",
    "FetchError",
]
