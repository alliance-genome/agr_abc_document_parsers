"""Orchestrator for source-to-Markdown conversion.

Detects the input format (TEI, JATS, or Office Open XML) and dispatches to
the appropriate parser, then emits Markdown via the shared emitter.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from lxml import etree

from agr_abc_document_parsers.docx_parser import parse_docx
from agr_abc_document_parsers.jats_parser import parse_jats
from agr_abc_document_parsers.md_emitter import emit_markdown, emit_markdown_with_provenance
from agr_abc_document_parsers.models import Document, MarkdownEmission
from agr_abc_document_parsers.ooxml_utils import OoxmlPackage, is_zip
from agr_abc_document_parsers.tei_parser import parse_tei
from agr_abc_document_parsers.xlsx_parser import parse_xlsx
from agr_abc_document_parsers.xml_utils import parse_xml

TEI_NAMESPACE = "http://www.tei-c.org/ns/1.0"

OFFICE_FORMATS = ("xlsx", "docx")
_OFFICE_EXTENSIONS = (".xlsx", ".xlsm", ".docx", ".docm")


def detect_format(content: bytes) -> str:
    """Detect the source format of a document.

    Args:
        content: Raw bytes of an XML file or an Office Open XML package
            (``.xlsx`` / ``.docx``), optionally gzip-compressed.

    Returns:
        'tei', 'jats', 'xlsx', or 'docx'.

    Raises:
        ValueError: If format cannot be determined.
    """
    if is_zip(content):
        return detect_office_format(content)
    root = parse_xml(content)
    return _detect_format_from_root(root)


def detect_office_format(content: bytes) -> str:
    """Detect whether an Office Open XML package is a workbook or a document.

    Args:
        content: Raw bytes of a ZIP-based Office file, optionally gzipped.

    Returns:
        'xlsx' or 'docx'.

    Raises:
        ValueError: If the bytes are not a ZIP package or hold neither a
            workbook nor a Word document.
    """
    pkg = OoxmlPackage(content)
    if pkg.has("xl/workbook.xml"):
        return "xlsx"
    if pkg.has("word/document.xml"):
        return "docx"
    raise ValueError(
        "Unknown format: ZIP package is neither an .xlsx workbook nor a .docx document"
    )


def _detect_format_from_root(root: etree._Element) -> str:
    """Detect format from a pre-parsed XML root element."""
    tag = root.tag
    # TEI: root is {namespace}TEI or just TEI with namespace
    if tag == f"{{{TEI_NAMESPACE}}}TEI" or tag == "TEI":
        return "tei"
    # JATS: root is <article>
    if etree.QName(tag).localname == "article":
        return "jats"

    raise ValueError(f"Unknown format: unrecognized root element <{tag}>")


def convert_xml_to_markdown(xml_content: bytes, source_format: str = "auto") -> str:
    """Convert TEI or JATS XML to a Markdown string.

    Office Open XML packages (``.xlsx`` / ``.docx``) are accepted too and
    routed through :func:`convert_office_to_markdown`; use that function
    directly when you can supply the supplement's display name as title.

    Args:
        xml_content: Raw bytes of an XML file (optionally gzipped).
        source_format: One of 'auto', 'tei', 'jats', 'xlsx', or 'docx'.
            If 'auto', format is detected from the content.

    Returns:
        A docling-style Markdown string.

    Raises:
        ValueError: If format is unknown or cannot be detected.
    """
    if source_format in OFFICE_FORMATS or (source_format == "auto" and is_zip(xml_content)):
        return convert_office_to_markdown(xml_content, source_format=source_format)

    root = None
    if source_format == "auto":
        root = parse_xml(xml_content)
        source_format = _detect_format_from_root(root)

    if source_format == "tei":
        document = parse_tei(xml_content, root=root)
    elif source_format == "jats":
        document = parse_jats(xml_content, root=root)
    else:
        raise ValueError(f"Unknown format: {source_format}")

    return emit_markdown(document)


def office_display_name(filename: str) -> str:
    """Return a human-readable title for an Office file name.

    Strips any directory part, a trailing ``.gz`` and the Office extension:
    ``"s3/Table_S1.xlsx.gz"`` -> ``"Table_S1"``.
    """
    name = PurePosixPath(filename.replace("\\", "/")).name
    if name.lower().endswith(".gz"):
        name = name[:-3]
    lower = name.lower()
    for ext in _OFFICE_EXTENSIONS:
        if lower.endswith(ext):
            name = name[: -len(ext)]
            break
    return name.strip()


def parse_office(content: bytes, source_format: str = "auto", title: str = "") -> Document:
    """Parse an Excel workbook or Word document into a Document model.

    Args:
        content: Raw bytes of an ``.xlsx``/``.xlsm`` or ``.docx``/``.docm``
            file, optionally gzip-compressed.
        source_format: 'auto', 'xlsx', or 'docx'.
        title: Document title (the supplement's display name).

    Raises:
        ValueError: If the format is unknown or the content is not an
            Office Open XML package.
    """
    if source_format == "auto":
        source_format = detect_office_format(content)
    if source_format == "xlsx":
        return parse_xlsx(content, title=title)
    if source_format == "docx":
        return parse_docx(content, title=title)
    raise ValueError(f"Unknown format: {source_format}")


def convert_office_to_markdown(
    content: bytes,
    source_format: str = "auto",
    title: str = "",
    filename: str = "",
) -> str:
    """Convert an Excel workbook or Word document to ABC Markdown.

    Spreadsheets become one section per worksheet, each holding a GFM
    table; Word documents keep their heading hierarchy, paragraphs, lists
    and tables.  The output conforms to ``MARKDOWN_SCHEMA.md`` like every
    other ABC Markdown file.

    Args:
        content: Raw bytes of the Office file, optionally gzip-compressed.
        source_format: 'auto' (sniff the ZIP contents), 'xlsx', or 'docx'.
        title: The H1 title to emit, normally the supplement's display name.
        filename: Used to derive the title when *title* is empty
            (``"Table_S1.xlsx"`` -> ``"Table_S1"``).

    Returns:
        A Markdown string with exactly one H1.

    Raises:
        ValueError: If the format is unknown or cannot be detected.
    """
    if not title and filename:
        title = office_display_name(filename)
    document = parse_office(content, source_format=source_format, title=title)
    return emit_markdown(document)


def convert_tei_to_markdown_with_provenance(xml_content: bytes) -> MarkdownEmission:
    """Convert TEI once into canonical Markdown and native-source byte spans."""
    document = parse_tei(xml_content)
    return emit_markdown_with_provenance(document)
