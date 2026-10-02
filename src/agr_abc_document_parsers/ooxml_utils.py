"""Shared helpers for reading Office Open XML packages (.docx / .xlsx).

Both Word and Excel files are ZIP archives of XML parts.  This module
provides a small, dependency-free (``zipfile`` + ``lxml``) package reader
plus namespace-tolerant element helpers used by :mod:`docx_parser` and
:mod:`xlsx_parser`.

Element lookups match on *local names* only, so the parsers work for both
the transitional OOXML namespaces written by Microsoft Office and the ISO
"strict" variants.
"""

from __future__ import annotations

import io
import posixpath
import zipfile
from typing import Iterator

from lxml import etree

from agr_abc_document_parsers.xml_utils import maybe_decompress, parse_xml

# ZIP local-file-header magic number.
_ZIP_MAGIC = b"PK\x03\x04"

_DC_TITLE_LOCALNAME = "title"


def is_zip(data: bytes) -> bool:
    """Return True when *data* (optionally gzip-compressed) is a ZIP archive."""
    return maybe_decompress(data)[:4] == _ZIP_MAGIC


class OoxmlPackage:
    """Minimal read-only view of an OOXML ZIP package."""

    def __init__(self, data: bytes) -> None:
        data = maybe_decompress(data)
        try:
            self._zip = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise ValueError("Not an Office Open XML package (invalid ZIP data)") from exc
        self._names = set(self._zip.namelist())

    @staticmethod
    def _normalize(name: str) -> str:
        return name.lstrip("/")

    def has(self, name: str) -> bool:
        """Return True when the package contains part *name*."""
        return self._normalize(name) in self._names

    def read_bytes(self, name: str) -> bytes | None:
        """Return the raw bytes of part *name*, or None when absent."""
        name = self._normalize(name)
        if name not in self._names:
            return None
        return self._zip.read(name)

    def read_xml(self, name: str) -> etree._Element | None:
        """Parse part *name* as XML, or return None when absent/empty."""
        raw = self.read_bytes(name)
        if not raw or not raw.strip():
            return None
        try:
            return parse_xml(raw)
        except (ValueError, etree.XMLSyntaxError):
            return None

    def relationships(self, part_name: str) -> dict[str, tuple[str, str]]:
        """Return the relationships of *part_name*.

        The result maps relationship id -> ``(target, mode)`` where *mode* is
        ``"External"`` for URLs and ``"Internal"`` for package parts.  Internal
        targets are resolved to absolute, normalized part names (without a
        leading slash) so they can be passed straight to :meth:`read_xml`.
        """
        part_name = self._normalize(part_name)
        base_dir = posixpath.dirname(part_name)
        rels_name = posixpath.join(base_dir, "_rels", posixpath.basename(part_name) + ".rels")
        root = self.read_xml(rels_name)
        result: dict[str, tuple[str, str]] = {}
        if root is None:
            return result
        for rel in root:
            if local_name(rel) != "Relationship":
                continue
            rid = rel.get("Id", "")
            target = rel.get("Target", "")
            mode = rel.get("TargetMode", "Internal")
            if not rid or not target:
                continue
            if mode != "External":
                if target.startswith("/"):
                    target = target.lstrip("/")
                else:
                    target = posixpath.normpath(posixpath.join(base_dir, target))
            result[rid] = (target, mode)
        return result

    def core_title(self) -> str:
        """Return the ``dc:title`` from ``docProps/core.xml`` (may be empty)."""
        root = self.read_xml("docProps/core.xml")
        if root is None:
            return ""
        for child in root:
            if local_name(child) == _DC_TITLE_LOCALNAME:
                return " ".join((child.text or "").split())
        return ""


# ---------------------------------------------------------------------------
# Namespace-tolerant element helpers
# ---------------------------------------------------------------------------


def local_name(elem: etree._Element) -> str:
    """Return the local (un-namespaced) tag name, or '' for comments/PIs."""
    tag = elem.tag
    if not isinstance(tag, str):
        return ""
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[1]
    return tag


def attr(elem: etree._Element, name: str, default: str = "") -> str:
    """Return attribute *name* regardless of its namespace prefix."""
    value = elem.get(name)
    if value is not None:
        return value
    suffix = "}" + name
    for key, val in elem.attrib.items():
        if isinstance(key, str) and key.endswith(suffix):
            return val if isinstance(val, str) else val.decode("utf-8", "replace")
    return default


def child(elem: etree._Element | None, name: str) -> etree._Element | None:
    """Return the first direct child with local name *name*."""
    if elem is None:
        return None
    for c in elem:
        if local_name(c) == name:
            return c
    return None


def children(elem: etree._Element | None, name: str) -> Iterator[etree._Element]:
    """Iterate direct children with local name *name*."""
    if elem is None:
        return
    for c in elem:
        if local_name(c) == name:
            yield c


def descendants(elem: etree._Element | None, name: str) -> Iterator[etree._Element]:
    """Iterate all descendants with local name *name* (document order)."""
    if elem is None:
        return
    for d in elem.iter():
        if local_name(d) == name:
            yield d


def is_true(value: str) -> bool:
    """Interpret an OOXML boolean attribute value (absent/"" means true)."""
    return value.strip().lower() not in ("0", "false", "off")
