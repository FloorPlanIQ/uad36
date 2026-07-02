"""Download the GSE-published UAD 3.6 artifacts at runtime.

This repository deliberately contains NO schema files. The GSE UAD 3.6
subschema and the sample URAR packages are published free of charge by
Fannie Mae and Freddie Mac; this module fetches them from the official
Freddie Mac URLs onto the user's machine (Fannie Mae serves identical files
but blocks non-browser clients).

If you need the full MISMO v3.6 Reference Model rather than the GSE
subschema, download it yourself from mismo.org after accepting MISMO's own
license terms — this package cannot and does not redistribute it.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from .errors import FetchError, SchemaNotAvailableError

SCHEMA_URL = "https://sf.freddiemac.com/docs/zip/uad-3.6-schema.zip"
SAMPLES_URL = (
    "https://sf.freddiemac.com/docs/zip/requirements/"
    "appendix-d-1-urar-sample-scenarios-and-xml-files.zip"
)
DELIVERY_SPEC_URL = (
    "https://sf.freddiemac.com/docs/xls/requirements/appendix-a-1-urar-delivery-specification.xlsx"
)
GSE_UAD_PAGE = "https://sf.freddiemac.com/tools-learning/uniform-mortgage-data-program/uad"

_USER_AGENT = "uad36-fetch/0.1 (+https://github.com/FloorPlanIQ/uad36)"


def default_artifacts_dir() -> Path:
    """Where fetched artifacts live: ``$UAD36_ARTIFACTS_DIR`` or ``~/.uad36``."""
    env = os.environ.get("UAD36_ARTIFACTS_DIR")
    return Path(env) if env else Path.home() / ".uad36"


def schemas_dir(artifacts_dir: Path | None = None) -> Path:
    return (artifacts_dir or default_artifacts_dir()) / "schemas"


def samples_dir(artifacts_dir: Path | None = None) -> Path:
    return (artifacts_dir or default_artifacts_dir()) / "samples"


def _download(url: str, dest: Path, *, quiet: bool = False) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            total = response.headers.get("Content-Length")
            if not quiet:
                size = f" ({int(total) // (1024 * 1024)} MB)" if total else ""
                print(f"downloading {url}{size} ...", file=sys.stderr)
            with tempfile.NamedTemporaryFile(delete=False, dir=dest.parent) as tmp:
                shutil.copyfileobj(response, tmp)
            Path(tmp.name).replace(dest)
    except (urllib.error.URLError, OSError) as exc:
        raise FetchError(
            f"could not download {url}: {exc}. "
            f"The GSE artifacts are also linked from {GSE_UAD_PAGE} — "
            f"download manually and unzip into {dest.parent}."
        ) from exc


def _extract_zip(archive: Path, dest: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(dest)


def fetch_schemas(artifacts_dir: Path | None = None, *, force: bool = False, quiet: bool = False) -> Path:
    """Download and unpack the GSE UAD 3.6 subschema. Returns the schemas dir.

    No-op if a schema is already present (use *force* to re-download).
    """
    dest = schemas_dir(artifacts_dir)
    if not force and find_schema_xsd(dest) is not None:
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    archive = dest / "uad-3.6-schema.zip"
    _download(SCHEMA_URL, archive, quiet=quiet)
    _extract_zip(archive, dest)
    archive.unlink()
    if find_schema_xsd(dest) is None:
        raise FetchError(f"downloaded schema archive did not contain a GSE_UAD_*.xsd under {dest}")
    return dest


def fetch_samples(artifacts_dir: Path | None = None, *, force: bool = False, quiet: bool = False) -> Path:
    """Download and unpack the Appendix D-1 sample URAR scenarios (~62 MB).

    The GSE archive contains one nested ZIP per scenario (SF1…SF5, Condo,
    Co-op, MH, 2–4 unit), each shaped exactly like a UCDP delivery package
    (URAR XML + PDF + ``Images/``). The nested ZIPs are kept as-is (use them
    with :class:`uad36.UcdpPackage`) and additionally extracted into sibling
    directories for direct access to the bare XML.

    Returns the samples dir. No-op if samples are already present.
    """
    dest = samples_dir(artifacts_dir)
    if not force and any(iter_sample_xml(dest)):
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    archive = dest / "appendix-d-1.zip"
    _download(SAMPLES_URL, archive, quiet=quiet)
    _extract_zip(archive, dest)
    archive.unlink()
    for nested in sorted(dest.glob("*_Appraisal*.zip")):
        _extract_zip(nested, dest / nested.stem)
    if not any(iter_sample_xml(dest)):
        raise FetchError(f"downloaded sample archive did not contain any *_Appraisal_*.xml under {dest}")
    return dest


def find_schema_xsd(schemas_root: Path | None = None) -> Path | None:
    """Locate the root GSE UAD XSD under the fetched schemas directory.

    Prefers the ``Combined`` build (one file plus xlink/xml imports).
    """
    root = schemas_root or schemas_dir()
    if not root.is_dir():
        return None

    def is_root_xsd(p: Path) -> bool:
        return not any(
            part in p.name
            for part in ("DataTypes", "EnumeratedTypes", "ComplexType", "Extension", "xlink")
        )

    combined = sorted(p for p in root.glob("**/Combined/GSE_UAD_*.xsd") if is_root_xsd(p))
    if combined:
        return combined[-1]
    candidates = sorted(p for p in root.glob("**/GSE_UAD_*.xsd") if is_root_xsd(p))
    return candidates[-1] if candidates else None


def require_schema_xsd(schemas_root: Path | None = None) -> Path:
    xsd = find_schema_xsd(schemas_root)
    if xsd is None:
        where = schemas_root or schemas_dir()
        raise SchemaNotAvailableError(
            f"no GSE UAD 3.6 subschema found under {where}. Run `uad36 fetch-schemas` first "
            f"(this package never bundles schema files)."
        )
    return xsd


def iter_sample_xml(samples_root: Path | None = None) -> list[Path]:
    """All sample URAR XML files under the fetched samples directory."""
    root = samples_root or samples_dir()
    if not root.is_dir():
        return []
    return sorted(root.glob("**/*_Appraisal_*.xml"))


def find_sample_xml(name_prefix: str, samples_root: Path | None = None) -> Path | None:
    """First sample XML whose file name starts with *name_prefix* (e.g. ``SF2``)."""
    for path in iter_sample_xml(samples_root):
        if path.name.startswith(name_prefix):
            return path
    return None


def iter_sample_packages(samples_root: Path | None = None) -> list[Path]:
    """The nested per-scenario ZIPs — each shaped like a UCDP delivery package."""
    root = samples_root or samples_dir()
    if not root.is_dir():
        return []
    return sorted(root.glob("*_Appraisal*.zip"))


def find_sample_package(scenario: str, samples_root: Path | None = None) -> Path | None:
    """The nested scenario ZIP whose name contains *scenario* (e.g. ``SF2``)."""
    for path in iter_sample_packages(samples_root):
        if scenario in path.name:
            return path
    return None
