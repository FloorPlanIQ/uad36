"""The UCDP UAD 3.6 delivery ZIP — the flagship artifact.

A UAD 3.6 submission to the Uniform Collateral Data Portal is a single ZIP
(≤ 60 MB) containing:

* exactly one URAR XML data file (the machine-readable report),
* one human-readable PDF (referenced from the XML as a ``FOREIGN_OBJECT``),
* an images folder with every photo, map, graph, and — critically — the
  floor-plan / improvement-sketch exhibit, which is the ONLY place the
  actual layout ships (the XML has a room inventory but zero geometry).

:class:`UcdpPackage` opens that ZIP, finds the XML, parses it into a
:class:`~uad36.models.Report`, and resolves the XML's image references to
ZIP members so exhibits can be extracted.
"""

from __future__ import annotations

import posixpath
import zipfile
from os import PathLike
from pathlib import Path
from typing import IO

from .errors import MalformedXmlError, PackageError
from .models import ImageRef, Report
from .parse import load_report

UCDP_MAX_SIZE_BYTES = 60 * 1024 * 1024
"""UCDP's published size limit for a UAD 3.6 delivery ZIP (60 MB)."""


class UcdpPackage:
    """A UAD 3.6 UCDP delivery ZIP, opened for reading.

    Usage::

        with UcdpPackage.open("delivery.zip") as pkg:
            report = pkg.report
            pkg.extract_floor_plans("out/")
    """

    def __init__(self, zf: zipfile.ZipFile, source_name: str):
        self._zf = zf
        self.source_name = source_name
        self.xml_name = self._locate_xml()
        self._report: Report | None = None

    # -- lifecycle ----------------------------------------------------------

    @classmethod
    def open(cls, source: str | PathLike[str] | IO[bytes]) -> "UcdpPackage":
        name = str(source) if isinstance(source, (str, PathLike)) else getattr(source, "name", "<stream>")
        try:
            zf = zipfile.ZipFile(source)
        except (zipfile.BadZipFile, OSError) as exc:
            raise PackageError(f"{name}: not a readable ZIP file ({exc})") from exc
        return cls(zf, name)

    def close(self) -> None:
        self._zf.close()

    def __enter__(self) -> "UcdpPackage":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- members ------------------------------------------------------------

    def _locate_xml(self) -> str:
        xml_members = [
            n for n in self._zf.namelist()
            if n.lower().endswith(".xml") and not n.endswith("/")
        ]
        if not xml_members:
            raise PackageError(f"{self.source_name}: no XML data file found in the ZIP")
        if len(xml_members) > 1:
            # A conforming delivery has exactly one; prefer the shallowest,
            # then the largest, and carry on rather than refusing to open.
            xml_members.sort(key=lambda n: (n.count("/"), -self._zf.getinfo(n).file_size))
        return xml_members[0]

    @property
    def names(self) -> list[str]:
        """All member names in the ZIP."""
        return self._zf.namelist()

    @property
    def total_size_bytes(self) -> int:
        """Sum of uncompressed member sizes."""
        return sum(i.file_size for i in self._zf.infolist())

    @property
    def exceeds_ucdp_size_limit(self) -> bool:
        return self.total_size_bytes > UCDP_MAX_SIZE_BYTES

    @property
    def pdf_names(self) -> list[str]:
        return [n for n in self.names if n.lower().endswith(".pdf")]

    @property
    def image_names(self) -> list[str]:
        exts = (".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff")
        return [n for n in self.names if n.lower().endswith(exts)]

    def read(self, member: str) -> bytes:
        try:
            return self._zf.read(member)
        except KeyError as exc:
            raise PackageError(f"{self.source_name}: no member named {member!r}") from exc

    def read_xml(self) -> bytes:
        return self.read(self.xml_name)

    # -- report -------------------------------------------------------------

    @property
    def report(self) -> Report:
        """The parsed URAR (parsed once, cached)."""
        if self._report is None:
            try:
                self._report = load_report(self.read_xml())
            except MalformedXmlError as exc:
                raise MalformedXmlError(f"{self.source_name} → {self.xml_name}: {exc}") from exc
        return self._report

    # -- exhibits -----------------------------------------------------------

    def resolve_image(self, ref: ImageRef) -> str | None:
        """Map an XML image reference to an actual ZIP member name.

        Tries the normalized path as-is, then case-insensitively, then by
        bare file name — sample and vendor packages are inconsistent about
        folder casing and nesting.
        """
        names = self.names
        if ref.file_name in names:
            return ref.file_name
        lowered = {n.lower(): n for n in names}
        if ref.file_name.lower() in lowered:
            return lowered[ref.file_name.lower()]
        base = posixpath.basename(ref.file_name).lower()
        for n in names:
            if posixpath.basename(n).lower() == base:
                return n
        return None

    def missing_images(self) -> list[ImageRef]:
        """Image references in the XML with no matching ZIP member."""
        return [ref for ref in self.report.exhibits.images if self.resolve_image(ref) is None]

    def extract_exhibits(
        self,
        dest: str | PathLike[str],
        *,
        categories: tuple[str, ...] | None = None,
    ) -> list[Path]:
        """Extract referenced images (optionally only given categories) to *dest*.

        Returns the written paths. Unresolvable references are skipped —
        check :meth:`missing_images` if you need to be strict.
        """
        dest_dir = Path(dest)
        dest_dir.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for ref in self.report.exhibits.images:
            if categories is not None and ref.category not in categories:
                continue
            member = self.resolve_image(ref)
            if member is None:
                continue
            out = dest_dir / posixpath.basename(member)
            out.write_bytes(self.read(member))
            written.append(out)
        return written

    def extract_floor_plans(self, dest: str | PathLike[str]) -> list[Path]:
        """Extract the floor-plan / improvement-sketch exhibits to *dest*.

        These images are the only carrier of the actual layout in a UAD 3.6
        delivery — the XML holds a room inventory but no geometry.
        """
        from .models import FLOOR_PLAN_CATEGORIES

        return self.extract_exhibits(dest, categories=FLOOR_PLAN_CATEGORIES)


def load_package(source: str | PathLike[str] | IO[bytes]) -> UcdpPackage:
    """Alias for :meth:`UcdpPackage.open`."""
    return UcdpPackage.open(source)
