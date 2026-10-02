"""Builders for minimal, hand-written Office Open XML packages used in tests.

These let unit tests exercise edge cases (inline strings, 1904 dates,
footnotes, tracked changes, ...) without depending on openpyxl/python-docx.
The committed ``tests/fixtures/*.xlsx`` / ``*.docx`` files cover the
"real application output" case.
"""

from __future__ import annotations

import io
import zipfile

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
S_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
</Types>
"""


def zip_bytes(parts: dict[str, str | bytes]) -> bytes:
    """Zip *parts* (name -> content) into an in-memory archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        for name, content in parts.items():
            zf.writestr(name, content)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------


def build_xlsx(
    sheets: dict[str, str],
    shared_strings: list[str] | None = None,
    styles_xml: str | None = None,
    date1904: bool = False,
    core_title: str = "",
    extra_parts: dict[str, str | bytes] | None = None,
) -> bytes:
    """Build an .xlsx from ``{sheet name: <sheetData> inner XML}``."""
    sheet_entries = []
    rels = []
    parts: dict[str, str | bytes] = {}
    for idx, (name, sheet_data) in enumerate(sheets.items(), 1):
        rid = f"rId{idx}"
        sheet_entries.append(f'<sheet name="{name}" sheetId="{idx}" r:id="{rid}"/>')
        rels.append(
            f'<Relationship Id="{rid}" '
            f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{idx}.xml"/>'
        )
        parts[f"xl/worksheets/sheet{idx}.xml"] = (
            f'<worksheet xmlns="{S_NS}"><sheetData>{sheet_data}</sheetData></worksheet>'
        )
    if shared_strings is not None:
        rels.append(
            '<Relationship Id="rIdSst" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" '
            'Target="sharedStrings.xml"/>'
        )
        items = "".join(f"<si><t>{s}</t></si>" for s in shared_strings)
        parts["xl/sharedStrings.xml"] = f'<sst xmlns="{S_NS}">{items}</sst>'
    if styles_xml is not None:
        parts["xl/styles.xml"] = styles_xml
    wb_pr = '<workbookPr date1904="1"/>' if date1904 else "<workbookPr/>"
    parts["xl/workbook.xml"] = (
        f'<workbook xmlns="{S_NS}" xmlns:r="{R_NS}">{wb_pr}'
        f"<sheets>{''.join(sheet_entries)}</sheets></workbook>"
    )
    parts["xl/_rels/workbook.xml.rels"] = (
        f'<Relationships xmlns="{RELS_NS}">{"".join(rels)}</Relationships>'
    )
    if core_title:
        parts["docProps/core.xml"] = _core_xml(core_title)
    if extra_parts:
        parts.update(extra_parts)
    return zip_bytes(parts)


def styles_with_formats(xf_num_fmt_ids: list[int], custom: dict[int, str] | None = None) -> str:
    """Build a styles.xml whose cellXfs use the given numFmtIds in order."""
    custom = custom or {}
    num_fmts = "".join(
        f'<numFmt numFmtId="{i}" formatCode="{code}"/>' for i, code in custom.items()
    )
    xfs = "".join(f'<xf numFmtId="{i}" applyNumberFormat="1"/>' for i in xf_num_fmt_ids)
    return (
        f'<styleSheet xmlns="{S_NS}">'
        f'<numFmts count="{len(custom)}">{num_fmts}</numFmts>'
        f'<cellXfs count="{len(xf_num_fmt_ids)}">{xfs}</cellXfs>'
        "</styleSheet>"
    )


# ---------------------------------------------------------------------------
# Word
# ---------------------------------------------------------------------------

DEFAULT_STYLES = f"""<w:styles xmlns:w="{W_NS}">
  <w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>
    <w:pPr><w:outlineLvl w:val="0"/></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/>
    <w:pPr><w:outlineLvl w:val="1"/></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/>
    <w:pPr><w:outlineLvl w:val="2"/></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="Ueberschrift1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="MyCustomHead"><w:name w:val="My Custom Head"/><w:basedOn w:val="Heading2"/></w:style>
  <w:style w:type="paragraph" w:styleId="OutlineOnly"><w:name w:val="Outline Only"/>
    <w:pPr><w:outlineLvl w:val="2"/></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="ListBullet"><w:name w:val="List Bullet"/><w:basedOn w:val="Normal"/>
    <w:pPr><w:numPr><w:numId w:val="1"/></w:numPr></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="BodyText"><w:name w:val="Body Text"/><w:basedOn w:val="Normal"/>
    <w:pPr><w:outlineLvl w:val="9"/></w:pPr></w:style>
</w:styles>
"""

DEFAULT_NUMBERING = f"""<w:numbering xmlns:w="{W_NS}">
  <w:abstractNum w:abstractNumId="0">
    <w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/></w:lvl>
    <w:lvl w:ilvl="1"><w:numFmt w:val="decimal"/></w:lvl>
  </w:abstractNum>
  <w:abstractNum w:abstractNumId="1">
    <w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/></w:lvl>
  </w:abstractNum>
  <w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
  <w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>
  <w:num w:numId="3"><w:abstractNumId w:val="1"/>
    <w:lvlOverride w:ilvl="0"><w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/></w:lvl></w:lvlOverride>
  </w:num>
</w:numbering>
"""


def build_docx(
    body_xml: str,
    styles_xml: str | None = DEFAULT_STYLES,
    numbering_xml: str | None = DEFAULT_NUMBERING,
    footnotes_xml: str | None = None,
    endnotes_xml: str | None = None,
    hyperlinks: dict[str, str] | None = None,
    core_title: str = "",
    w_ns: str = W_NS,
) -> bytes:
    """Build a .docx whose <w:body> contains *body_xml*."""
    parts: dict[str, str | bytes] = {
        "word/document.xml": (
            f'<w:document xmlns:w="{w_ns}" xmlns:r="{R_NS}" '
            'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
            'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
            f"<w:body>{body_xml}<w:sectPr/></w:body></w:document>"
        )
    }
    rels = []
    if styles_xml is not None:
        parts["word/styles.xml"] = styles_xml
    if numbering_xml is not None:
        parts["word/numbering.xml"] = numbering_xml
    if footnotes_xml is not None:
        parts["word/footnotes.xml"] = footnotes_xml
    if endnotes_xml is not None:
        parts["word/endnotes.xml"] = endnotes_xml
    for rid, url in (hyperlinks or {}).items():
        rels.append(
            f'<Relationship Id="{rid}" '
            f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
            f'Target="{url}" TargetMode="External"/>'
        )
    parts["word/_rels/document.xml.rels"] = (
        f'<Relationships xmlns="{RELS_NS}">{"".join(rels)}</Relationships>'
    )
    if core_title:
        parts["docProps/core.xml"] = _core_xml(core_title)
    return zip_bytes(parts)


def p(text: str = "", style: str = "", runs: str = "", num_id: str = "", ilvl: str = "0") -> str:
    """Build a <w:p> with an optional style / numbering and plain or raw runs."""
    ppr = ""
    if style or num_id:
        ppr = "<w:pPr>"
        if style:
            ppr += f'<w:pStyle w:val="{style}"/>'
        if num_id:
            ppr += f'<w:numPr><w:ilvl w:val="{ilvl}"/><w:numId w:val="{num_id}"/></w:numPr>'
        ppr += "</w:pPr>"
    if text and not runs:
        runs = r(text)
    return f"<w:p>{ppr}{runs}</w:p>"


def r(text: str, bold: bool = False, italic: bool = False, vert: str = "") -> str:
    """Build a <w:r> with the given direct formatting."""
    rpr = ""
    if bold or italic or vert:
        rpr = "<w:rPr>"
        if bold:
            rpr += "<w:b/>"
        if italic:
            rpr += "<w:i/>"
        if vert:
            rpr += f'<w:vertAlign w:val="{vert}"/>'
        rpr += "</w:rPr>"
    return f'<w:r>{rpr}<w:t xml:space="preserve">{text}</w:t></w:r>'


def tbl(rows: list[list[str]], header_first: bool = False) -> str:
    """Build a simple <w:tbl> from cell texts."""
    out = ["<w:tbl><w:tblPr/>"]
    for i, row in enumerate(rows):
        tr_pr = "<w:trPr><w:tblHeader/></w:trPr>" if header_first and i == 0 else ""
        cells = "".join(f"<w:tc>{p(cell)}</w:tc>" for cell in row)
        out.append(f"<w:tr>{tr_pr}{cells}</w:tr>")
    out.append("</w:tbl>")
    return "".join(out)


def _core_xml(title: str) -> str:
    return (
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f"<dc:title>{title}</dc:title></cp:coreProperties>"
    )
