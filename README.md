# uad36

**Python parser for UAD 3.6 appraisal data: the redesigned URAR XML and the UCDP delivery ZIP.**

On **November 2, 2026**, UAD 3.6 becomes mandatory for appraisals delivered to Fannie Mae and Freddie Mac. Every GSE appraisal after that date is a machine-readable XML document — room inventory, per-level areas, condition and quality ratings, the full sales-comparison grid — packaged in a ZIP with the PDF and every exhibit image. As far as we can tell, no other open-source library parses any of it. This one does.

```
pip install uad36        # not yet published — build from source for now
uad36 fetch-schemas      # downloads the free GSE UAD 3.6 subschema (validation)
uad36 fetch-samples      # downloads the official GSE sample packages (~62 MB)
```

> **Unofficial.** This library parses the *publicly published* GSE (Fannie Mae / Freddie Mac) UAD 3.6 specification. It is not affiliated with, sponsored by, or endorsed by Fannie Mae, Freddie Mac, or MISMO®. It makes no claim of certification or compliance with any MISMO program. It ships **no schema files** — see [Schemas and licensing](#schemas-and-licensing).

## Quickstart

```python
import uad36

with uad36.UcdpPackage.open("delivery.zip") as pkg:   # the UCDP submission ZIP
    report = pkg.report
    print(report.assignment.effective_date)            # '2019-08-07'
    print(report.rooms.counts_by_type())               # {'Bedroom': 5, 'Kitchen': 1, ...}
    print(report.areas.gross_living_area_sqft)         # 3308.0
    for comp in report.sales_comparison.comparables:
        print(comp.ordinal, comp.adjusted_sale_price, comp.weight)
    pkg.extract_floor_plans("exhibits/")                # the layout ships ONLY as an image

report = uad36.load_report("appraisal.xml")             # bare URAR XML works too
```

Or from the shell:

```
uad36 inspect delivery.zip      # human-readable summary
uad36 validate delivery.zip     # structural validation against the GSE subschema
uad36 redact delivery.zip out.zip   # de-identified copy (see PII section)
uad36 exhibits delivery.zip out/ --floor-plans-only
```

## What's actually inside the UCDP ZIP

A UAD 3.6 delivery to the Uniform Collateral Data Portal is a single ZIP, capped at **60 MB** (up from the old 15 MB ENV limit):

| Member | What it is | What `uad36` gives you |
|---|---|---|
| `<name>.xml` | The URAR itself, MISMO v3.6-based XML (678 mapped data points) | `pkg.report` → typed `Report` |
| `<name>.pdf` | The human-readable report, referenced from the XML as a `FOREIGN_OBJECT` | `report.pdf_reference`, `pkg.pdf_names` |
| `Images/*.png\|jpg` | Every photo, map, graph — and the **floor plan / improvement sketch exhibit** | `report.exhibits`, `pkg.extract_floor_plans()` |

Inside the XML, the parts most integrations care about (paths abbreviated — the real ones are ~20 containers deep under `MESSAGE/…/VALUATION_RESPONSE/VALUATION_ANALYSIS`):

| XML container | Content | Model |
|---|---|---|
| `PROPERTY[@ValuationUseType="SubjectProperty"]` | The subject: address, units, improvements | `report.subject` |
| `…PROPERTY_UNIT/ROOMS/ROOM/ROOM_DETAIL` | Room inventory: `RoomType` × `LevelType` + condition/quality/update status per room | `report.rooms` (`RoomInventory`) |
| `…PROPERTY_UNIT/LEVELS/LEVEL` | ANSI Z765-style per-level finished/unfinished areas | `report.areas` (`LevelAreas`) |
| `…PROPERTY_UNIT_AREA` | The six GLA roll-ups (standard/non-standard × above/below grade) | `report.areas.unit_areas` |
| `PROPERTY[@ValuationUseType="SalesComparable"]` | Each comp: prices, adjustments, weight, proximity, its own room/level data | `report.sales_comparison.comparables` |
| `PROPERTY[@ValuationUseType="PropertyAnalyzedNotUsed"]` | **New in UAD 3.6**: "Additional Properties Analyzed But Not Used", with structured `ReasonPropertyNotUsedType` values + free-text explanation | `report.sales_comparison.analyzed_not_used` |
| `IMAGE/ImageCategoryType` | Exhibit metadata (`FloorPlan`, `SubjectPropertyImprovementSketch`, `PropertyPhoto`, maps, graphs) | `report.exhibits` |

**The one thing that is NOT in the XML: geometry.** There are no room dimensions, no coordinates, no polygons, no adjacency — the room list says *what* exists on *which* level, and the actual layout ships only as an image exhibit (`FloorPlan` or `SubjectPropertyImprovementSketch`). If you need the layout, you need the image (and note it's not guaranteed present — exterior-only scenarios ship without one).

## Field notes (things the spec won't tell you)

Learned from parsing all twelve official GSE Appendix D-1 sample packages:

- **Image paths are Windows-style.** `ImageFileLocationIdentifier` looks like `\\Images\SF2_Den.png` — backslashes, leading separator. ZIP members are `Images/SF2_Den.png`. `uad36` normalizes (and falls back to case-insensitive and basename matching).
- **Ignore `xsi:schemaLocation`.** The samples point it at a Fannie Mae employee's local OneDrive path (`file:///C:/Users/…`). Never resolve it; validate against your own fetched copy of the subschema.
- **Sample versions ≠ schema version.** Current samples are v1.2–v1.4 against subschema v1.3 — all twelve validate cleanly anyway.
- **The samples carry XML comments marked "DO NOT DELIVER".** Real deliveries must strip them; parsers must tolerate them.
- **Room-level images are uncategorized.** `ImageCategoryType` appears on inspection/amenity/document images, but images attached to a `ROOM` have no category — you can't find the kitchen photo by category alone.
- **The layout exhibit category varies.** Some scenarios use `FloorPlan`, others `SubjectPropertyImprovementSketch`; treat them as one family (`uad36.FLOOR_PLAN_CATEGORIES`), and handle absence.
- **There is no "GLA" element.** Gross living area is `UnitStandardAboveGradeFinishedAreaMeasure`, one of six `PROPERTY_UNIT_AREA` roll-ups.
- **`MISMOReferenceModelIdentifier` is `3.6.0366`** on all current samples, not `3.6`.

## Validating for UCDP submission

`uad36 validate` answers one question: **is this document structurally a UAD 3.6 URAR?** — well-formed XML that conforms to the GSE-published subschema, with readable errors (line numbers, namespace clutter stripped).

It deliberately does **not** reimplement the GSEs' UAD compliance rules — the 800+ conditionality and business-logic checks (709 URAR rules + Restricted Update + Completion Report rules) that UCDP enforces at submission time. Fannie Mae and Freddie Mac each expose exactly those rules, for free, through their **UAD Compliance APIs**, including a customer test environment you can use before completing GSE verification. The sane pipeline is:

1. `uad36 validate` locally, in your unit tests, on every file you touch — fast, offline, structural;
2. the GSE UAD Compliance APIs before submission — authoritative, complete, theirs.

Anything this library duplicated from layer 2 would be a maintenance liability that drifts out of sync with the GSEs; we'd rather interoperate with the source of truth.

## PII: this data is regulated

A URAR is nonpublic personal information about a consumer of a financial institution — it names the borrower, pinpoints their home, and reveals their finances. GLBA / FTC Safeguards Rule obligations flow down by contract to vendors that touch it. `uad36` is PII-aware by design:

- `uad36.PII_FIELDS` documents which elements carry PII and why (names; street/city/county/ZIP; GPS coordinates; license numbers; client file and MLS identifiers).
- `uad36.iter_pii(xml)` enumerates the PII actually present in a document.
- `uad36.redact(xml)` / `uad36 redact in.zip out.zip` produce a **de-identified copy that keeps the analytical structure** — every room, level, area, rating, and adjustment survives; identity and precise location do not. State codes survive by default (coarse geography); redacted output still validates against the subschema. For ZIPs, photos and the PDF are dropped (faces, addresses, signatures) and floor-plan exhibits are kept.
- Caveat: free-text comment fields are kept by default and can contain incidental PII; pass `redact_free_text=True` / `--free-text` to blank them.

If you're asking a partner for appraisal data to test with, ask for the redacted form. It's what we do.

## Examples

Three runnable scripts against the official GSE samples (`uad36 fetch-samples` first):

- [`examples/01_inspect_package.py`](examples/01_inspect_package.py) — open a delivery ZIP, walk rooms/levels/grid
- [`examples/02_sales_grid_and_not_used.py`](examples/02_sales_grid_and_not_used.py) — the sales-comparison grid and the new "analyzed but not used" section
- [`examples/03_redact_and_extract.py`](examples/03_redact_and_extract.py) — de-identify a package and pull the floor-plan exhibits

## Schemas and licensing

The **code** is MIT-licensed. The repository contains **no schema files, no sample files, and no MISMO-derived artifacts** — and PRs adding them will be declined (there's a test that fails if any sneak in):

- The **GSE UAD 3.6 subschema** is published free by Fannie Mae and Freddie Mac for building UCDP-compliant software. `uad36 fetch-schemas` downloads it from the official Freddie Mac URL onto *your* machine, under *their* terms (it remains Fannie Mae / Freddie Mac copyrighted material).
- The **base MISMO v3.6 Reference Model** is copyrighted by MISMO and licensed under MISMO's own End-User/Distributor terms, which do not permit redistribution in a repository like this one. If you need it, download it from [mismo.org](https://www.mismo.org) after accepting their license.
- The **GSE sample packages** (Appendix D-1) are public GSE documentation; `uad36 fetch-samples` downloads them the same way. The test suite runs against them; it skips (with instructions) until you fetch.

UAD® and Uniform Appraisal Dataset® materials are © Fannie Mae and Freddie Mac. MISMO® is a registered trademark of the Mortgage Industry Standards Maintenance Organization. This project claims no rights in any of them.

## Timeline (why this matters now)

| Date | Milestone |
|---|---|
| Sep 8, 2025 | UAD 3.6 Limited Production Period began |
| Jan 26, 2026 | Broad Production Period — any lender may deliver UAD 3.6 |
| **Nov 2, 2026** | **UAD 3.6 mandatory** for new GSE appraisal assignments |
| May 3, 2027 | UAD 2.6 pipeline closes (revisions only until then) |

## Status

v0.1 — the useful 20%. Parses every official GSE sample scenario (12/12, structural validation clean). The API will move; pin your version. Issues and real-world (redacted!) problem files welcome.
