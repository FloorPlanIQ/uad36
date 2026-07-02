"""De-identify a delivery package and extract the floor-plan exhibits.

The redacted ZIP keeps the analytical structure (rooms, levels, areas,
ratings, the sales grid) and the floor-plan/sketch exhibit, and drops
names, addresses, coordinates, photos, and the PDF. This is the shape to
ask for when requesting appraisal data from a partner.

Run `uad36 fetch-samples` once first, then:

    uv run python examples/03_redact_and_extract.py
"""

from pathlib import Path

from uad36 import UcdpPackage, iter_pii, redact_package
from uad36.fetch import find_sample_package

package_path = find_sample_package("SF2")
if package_path is None:
    raise SystemExit("samples not fetched — run `uad36 fetch-samples` first")

out_dir = Path("example-output")
out_dir.mkdir(exist_ok=True)

# what PII is in there?
with UcdpPackage.open(package_path) as pkg:
    hits = iter_pii(pkg.read_xml())
print(f"{len(hits)} PII values in the original, e.g.:")
for hit in hits[:5]:
    print(f"  {hit.element} = {hit.value!r}  [{hit.category}]")

# write the de-identified copy
redacted_zip = out_dir / "redacted.zip"
members = redact_package(package_path, redacted_zip)
print(f"\nwrote {redacted_zip}: {members}")

# prove the structure survived, then pull the layout exhibit
with UcdpPackage.open(redacted_zip) as pkg:
    report = pkg.report
    print(f"redacted subject: {report.subject.address.one_line()}")
    print(f"rooms: {len(report.rooms)}, GLA: {report.areas.gross_living_area_sqft:g} sqft")
    plans = pkg.extract_floor_plans(out_dir)
    print(f"floor plan(s) extracted: {[str(p) for p in plans]}")
