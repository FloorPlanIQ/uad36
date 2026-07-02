"""Namespace-tolerant XML helpers.

UAD 3.6 URAR XML lives in the MISMO namespace
(``http://www.mismo.org/residential/2009/schemas``) with GSE extension and
xlink namespaces mixed in. Real-world files are not always well-behaved about
this, so every lookup here matches on *local name* — a file with a missing or
non-standard default namespace still parses.
"""

from __future__ import annotations

from collections.abc import Iterator

from lxml import etree

MISMO_NS = "http://www.mismo.org/residential/2009/schemas"
XLINK_NS = "http://www.w3.org/1999/xlink"
GSE_EXTENSION_NS = "http://www.datamodelextension.org"


def local_name(el: etree._Element) -> str:
    """Tag name of *el* without its namespace prefix."""
    return etree.QName(el).localname


def iter_children(el: etree._Element, name: str) -> Iterator[etree._Element]:
    """Direct children of *el* whose local name is *name*."""
    for child in el:
        if isinstance(child.tag, str) and etree.QName(child).localname == name:
            yield child


def find_child(el: etree._Element, name: str) -> etree._Element | None:
    """First direct child of *el* whose local name is *name*."""
    return next(iter_children(el, name), None)


def iter_descendants(el: etree._Element, name: str) -> Iterator[etree._Element]:
    """All descendants of *el* whose local name is *name* (document order)."""
    for node in el.iter():
        if isinstance(node.tag, str) and etree.QName(node).localname == name:
            if node is not el:
                yield node


def find_descendant(el: etree._Element, name: str) -> etree._Element | None:
    """First descendant of *el* whose local name is *name*."""
    return next(iter_descendants(el, name), None)


def descend(el: etree._Element, *names: str) -> etree._Element | None:
    """Walk a chain of direct children by local name; None if any hop is missing."""
    node: etree._Element | None = el
    for name in names:
        if node is None:
            return None
        node = find_child(node, name)
    return node


def text_of(el: etree._Element | None) -> str | None:
    """Stripped text content of *el*, or None if the element is missing/empty."""
    if el is None or el.text is None:
        return None
    stripped = el.text.strip()
    return stripped or None


def child_text(el: etree._Element, name: str) -> str | None:
    """Text of the first direct child named *name*."""
    return text_of(find_child(el, name))


def descendant_text(el: etree._Element, name: str) -> str | None:
    """Text of the first descendant named *name*."""
    return text_of(find_descendant(el, name))


def child_decimal(el: etree._Element, name: str) -> float | None:
    """Text of child *name* parsed as a float; None on absence or bad data."""
    raw = child_text(el, name)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def child_int(el: etree._Element, name: str) -> int | None:
    """Text of child *name* parsed as an int; None on absence or bad data."""
    raw = child_text(el, name)
    if raw is None:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def element_path(el: etree._Element) -> str:
    """Human-readable /LOCAL/NAME/path to *el* for error messages."""
    parts: list[str] = []
    node: etree._Element | None = el
    while node is not None:
        if isinstance(node.tag, str):
            parts.append(etree.QName(node).localname)
        node = node.getparent()
    return "/" + "/".join(reversed(parts))


def normalize_object_path(raw: str) -> str:
    r"""Normalize a UAD file-location identifier to a ZIP-relative POSIX path.

    The GSE sample files write image locations Windows-style with leading
    backslashes (``\\Images\SF2_Den.png``); UCDP ZIP members are addressed
    with forward slashes and no leading separator.
    """
    return raw.replace("\\", "/").lstrip("/")
