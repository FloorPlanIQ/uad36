"""The ``uad36`` command-line interface.

Commands:

* ``uad36 fetch-schemas`` — download the free GSE UAD 3.6 subschema
* ``uad36 fetch-samples`` — download the GSE Appendix D-1 sample packages
* ``uad36 inspect FILE`` — summarize a URAR XML or UCDP ZIP
* ``uad36 validate FILE`` — structural validation against the fetched subschema
* ``uad36 redact IN OUT`` — de-identified copy (XML or ZIP)
* ``uad36 exhibits ZIP DEST`` — extract image exhibits from a delivery ZIP
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .errors import Uad36Error


def _cmd_fetch_schemas(args: argparse.Namespace) -> int:
    from .fetch import fetch_schemas, find_schema_xsd

    dest = fetch_schemas(args.dest, force=args.force)
    print(f"GSE UAD 3.6 subschema ready: {find_schema_xsd(dest)}")
    return 0


def _cmd_fetch_samples(args: argparse.Namespace) -> int:
    from .fetch import fetch_samples, iter_sample_xml

    dest = fetch_samples(args.dest, force=args.force)
    samples = iter_sample_xml(dest)
    print(f"{len(samples)} sample URAR XML file(s) under {dest}")
    for path in samples:
        print(f"  {path.relative_to(dest)}")
    return 0


def _is_zip(path: Path) -> bool:
    if path.suffix.lower() == ".zip":
        return True
    try:
        with path.open("rb") as fh:
            return fh.read(4) == b"PK\x03\x04"
    except OSError:
        return False


def _load_report_any(path: Path):
    from .package import UcdpPackage
    from .parse import load_report

    if _is_zip(path):
        with UcdpPackage.open(path) as pkg:
            return pkg.report, pkg
    return load_report(path), None


def _cmd_inspect(args: argparse.Namespace) -> int:
    from .package import UcdpPackage
    from .parse import load_report

    path = Path(args.file)
    if _is_zip(path):
        with UcdpPackage.open(path) as pkg:
            report = pkg.report
            print(f"UCDP package: {path.name}")
            print(f"  members: {len(pkg.names)}  (xml: {pkg.xml_name}, pdf: {', '.join(pkg.pdf_names) or '—'})")
            size_mb = pkg.total_size_bytes / (1024 * 1024)
            flag = "  ⚠ exceeds the 60 MB UCDP limit" if pkg.exceeds_ucdp_size_limit else ""
            print(f"  uncompressed size: {size_mb:.1f} MB{flag}")
            missing = pkg.missing_images()
            if missing:
                print(f"  ⚠ {len(missing)} image reference(s) not present in the ZIP")
    else:
        report = load_report(path)
        print(f"URAR XML: {path.name}")

    a = report.assignment
    print(f"  MISMO reference model: {report.mismo_reference_model or '—'}")
    print(f"  assignment: {a.assignment_type or '—'}  effective {a.effective_date or '—'}")
    if a.opinion_of_value is not None:
        print(f"  opinion of value: ${a.opinion_of_value:,.0f}")
    if report.subject and report.subject.address:
        print(f"  subject: {report.subject.address.one_line()}")
    rooms = report.rooms
    if len(rooms):
        counts = ", ".join(f"{v}× {k}" for k, v in sorted(rooms.counts_by_type().items()))
        print(f"  rooms ({len(rooms)}): {counts}")
    areas = report.areas
    for lv in areas:
        print(
            f"  level {lv.level_type}: finished {lv.finished_area_sqft or 0:g} sqft, "
            f"unfinished {lv.unfinished_area_sqft or 0:g} sqft"
        )
    if areas.gross_living_area_sqft is not None:
        print(f"  GLA (standard above-grade finished): {areas.gross_living_area_sqft:g} sqft")
    grid = report.sales_comparison
    print(f"  comparables: {len(grid.comparables)}  analyzed-not-used: {len(grid.analyzed_not_used)}")
    for comp in grid.comparables:
        addr = comp.address.one_line() if comp.address else "—"
        print(f"    #{comp.ordinal}: {addr}  adjusted ${comp.adjusted_sale_price or 0:,.0f}  weight {comp.weight or '—'}")
    for pnu in grid.analyzed_not_used:
        addr = pnu.address.one_line() if pnu.address else "—"
        print(f"    not used: {addr}  reasons: {', '.join(pnu.reasons) or '—'}")
    cats = report.exhibits.categories()
    if cats:
        print(f"  exhibits: {', '.join(f'{v}× {k}' for k, v in sorted(cats.items()))}")
    plans = report.exhibits.floor_plans()
    if plans:
        print(f"  floor-plan exhibit(s): {', '.join(p.file_name for p in plans)}")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    from .package import UcdpPackage
    from .validate import validate_xml

    path = Path(args.file)
    source: object = path
    if _is_zip(path):
        with UcdpPackage.open(path) as pkg:
            source = pkg.read_xml()
    result = validate_xml(source, schemas_root=args.schemas)  # type: ignore[arg-type]
    if args.json:
        print(
            json.dumps(
                {
                    "valid": result.valid,
                    "summary": result.summary(),
                    "findings": [
                        {"severity": f.severity, "line": f.line, "message": f.message}
                        for f in result.findings
                    ],
                },
                indent=2,
            )
        )
    else:
        print(f"{path.name}: {result.summary()}")
        for finding in result.findings[: args.max_findings]:
            print(f"  {finding}")
        if len(result.findings) > args.max_findings:
            print(f"  … and {len(result.findings) - args.max_findings} more")
    return 0 if result.valid else 1


def _cmd_redact(args: argparse.Namespace) -> int:
    from .pii import redact, redact_package

    src, dst = Path(args.input), Path(args.output)
    if _is_zip(src):
        members = redact_package(
            src,
            dst,
            keep_pdf=args.keep_pdf,
            keep_other_images=args.keep_photos,
            redact_free_text=args.free_text,
        )
        print(f"wrote {dst} ({len(members)} member(s): {', '.join(members)})")
    else:
        dst.write_bytes(redact(src, redact_free_text=args.free_text))
        print(f"wrote {dst}")
    return 0


def _cmd_exhibits(args: argparse.Namespace) -> int:
    from .package import UcdpPackage

    with UcdpPackage.open(args.zip) as pkg:
        if args.floor_plans_only:
            written = pkg.extract_floor_plans(args.dest)
        elif args.category:
            written = pkg.extract_exhibits(args.dest, categories=tuple(args.category))
        else:
            written = pkg.extract_exhibits(args.dest)
    for path in written:
        print(path)
    if not written:
        print("no matching exhibits found", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="uad36",
        description="Unofficial parser and tools for UAD 3.6 URAR XML and UCDP delivery ZIPs.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("fetch-schemas", help="download the free GSE UAD 3.6 subschema")
    p.add_argument("--dest", type=Path, default=None, help="artifacts dir (default: ~/.uad36 or $UAD36_ARTIFACTS_DIR)")
    p.add_argument("--force", action="store_true", help="re-download even if present")
    p.set_defaults(func=_cmd_fetch_schemas)

    p = sub.add_parser("fetch-samples", help="download the GSE Appendix D-1 sample URAR packages (~62 MB)")
    p.add_argument("--dest", type=Path, default=None)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=_cmd_fetch_samples)

    p = sub.add_parser("inspect", help="summarize a URAR XML or UCDP ZIP")
    p.add_argument("file")
    p.set_defaults(func=_cmd_inspect)

    p = sub.add_parser("validate", help="structural validation against the fetched GSE subschema")
    p.add_argument("file")
    p.add_argument("--schemas", type=Path, default=None, help="fetched schemas dir")
    p.add_argument("--json", action="store_true")
    p.add_argument("--max-findings", type=int, default=20)
    p.set_defaults(func=_cmd_validate)

    p = sub.add_parser("redact", help="write a de-identified copy of a URAR XML or UCDP ZIP")
    p.add_argument("input")
    p.add_argument("output")
    p.add_argument("--free-text", action="store_true", help="also blank free-text comment fields")
    p.add_argument("--keep-pdf", action="store_true", help="(zip) keep the PDF — it is NOT redacted")
    p.add_argument("--keep-photos", action="store_true", help="(zip) keep non-floor-plan images")
    p.set_defaults(func=_cmd_redact)

    p = sub.add_parser("exhibits", help="extract image exhibits from a UCDP ZIP")
    p.add_argument("zip")
    p.add_argument("dest")
    p.add_argument("--floor-plans-only", action="store_true", help="only FloorPlan / improvement-sketch exhibits")
    p.add_argument("--category", action="append", help="extract only this ImageCategoryType (repeatable)")
    p.set_defaults(func=_cmd_exhibits)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except Uad36Error as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
