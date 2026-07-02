"""The sales-comparison grid, including UAD 3.6's new
"Additional Properties Analyzed But Not Used" section.

Run `uad36 fetch-samples` once first, then:

    uv run python examples/02_sales_grid_and_not_used.py
"""

from uad36 import load_report
from uad36.fetch import find_sample_xml

xml_path = find_sample_xml("Condo1")
if xml_path is None:
    raise SystemExit("samples not fetched — run `uad36 fetch-samples` first")

report = load_report(xml_path)
grid = report.sales_comparison

print(f"subject : {grid.subject.address.one_line()}")
print(f"value indicated by sales comparison: ${grid.indicated_value:,.0f}\n")

for comp in grid.comparables:
    print(f"comp #{comp.ordinal}: {comp.address.one_line()}")
    print(
        f"  sale ${comp.sale_price or 0:,.0f} → adjusted ${comp.adjusted_sale_price or 0:,.0f}"
        f"  ({comp.proximity_miles} mi {comp.direction_from_subject or ''}, weight: {comp.weight})"
    )
    nonzero = [a for a in comp.adjustments if a.amount]
    for adj in nonzero:
        print(f"    {adj.adjustment_type}: {adj.amount:+,.0f}")
    if not nonzero:
        print("    (no non-zero adjustments)")

# The part no pre-3.6 form had: documented exclusions with structured reasons.
print(f"\nanalyzed but NOT used ({len(grid.analyzed_not_used)}):")
for entry in grid.analyzed_not_used:
    print(f"  {entry.address.one_line()}")
    print(f"    reasons: {', '.join(entry.reasons)}")
    print(f"    note   : {entry.explanation}")
