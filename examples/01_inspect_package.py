"""Open a UCDP delivery ZIP and walk the report.

Run `uad36 fetch-samples` once first, then:

    uv run python examples/01_inspect_package.py
"""

from uad36 import UcdpPackage
from uad36.fetch import find_sample_package

package_path = find_sample_package("SF2")
if package_path is None:
    raise SystemExit("samples not fetched — run `uad36 fetch-samples` first")

with UcdpPackage.open(package_path) as pkg:
    report = pkg.report

    print(f"package : {package_path.name}")
    print(f"xml     : {pkg.xml_name}")
    print(f"pdf     : {', '.join(pkg.pdf_names)}")
    print(f"size    : {pkg.total_size_bytes / 1_048_576:.1f} MB (limit 60 MB)")

    a = report.assignment
    print(f"\nassignment: {a.assignment_type}, effective {a.effective_date}")
    print(f"opinion of value: ${a.opinion_of_value:,.0f}")
    print(f"appraiser: {a.appraiser.company_name if a.appraiser else '—'}")

    print(f"\nsubject: {report.subject.address.one_line()}")
    print("rooms by level:")
    for level, count in sorted(report.rooms.counts_by_level().items()):
        types = [r.room_type for r in report.rooms.on_level(level)]
        print(f"  {level}: {count} rooms ({', '.join(t or '?' for t in types)})")

    print("\nareas:")
    for lv in report.areas:
        print(
            f"  {lv.level_type} ({lv.grade_level_type}): "
            f"{lv.finished_area_sqft:g} finished / {lv.unfinished_area_sqft or 0:g} unfinished sqft"
        )
    print(f"  GLA (standard above-grade finished): {report.areas.gross_living_area_sqft:g} sqft")

    print(f"\nexhibits by category: {report.exhibits.categories()}")
    plans = report.exhibits.floor_plans()
    print(f"floor-plan exhibit(s): {[p.file_name for p in plans] or 'NONE (not guaranteed!)'}")
