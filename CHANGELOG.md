# Changelog

## 0.1.0 — unreleased

Initial release. The useful 20%:

- `load_report()` — UAD 3.6 URAR XML → typed `Report` (pydantic models:
  `RoomInventory`, `LevelAreas`, `SalesComparisonGrid` including the new
  "Additional Properties Analyzed But Not Used" entries, `Exhibits`,
  `Assignment`).
- `UcdpPackage` — open the UCDP delivery ZIP (XML + PDF + images), resolve
  the XML's Windows-style image references to ZIP members, extract exhibits
  (`extract_floor_plans()`).
- `validate_xml()` — structural validation (well-formedness + the GSE
  UAD 3.6 subschema) with readable findings. Compliance-rule checking is
  explicitly out of scope (use the free GSE UAD Compliance APIs).
- `iter_pii()` / `redact()` / `redact_package()` — documented PII field map
  and de-identified copies that preserve analytical structure.
- `uad36` CLI: `fetch-schemas`, `fetch-samples`, `inspect`, `validate`,
  `redact`, `exhibits`.
- No schema files in the repo, ever (MISMO licensing): schemas and GSE
  samples are fetched at runtime from the official GSE URLs.
- Verified against all 12 official GSE Appendix D-1 sample packages.
