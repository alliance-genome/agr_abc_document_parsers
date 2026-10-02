"""Parse Excel workbooks (.xlsx / .xlsm) into the intermediate Document model.

Spreadsheets map onto a small slice of the Document model: every worksheet
becomes one :class:`Section` (sheet name as heading) holding exactly one
:class:`Table` whose first non-empty row is the header.  The emitter then
produces the same GFM table syntax as for JATS/TEI articles.

The workbook is read directly from its OOXML parts with ``zipfile`` +
``lxml`` (no openpyxl dependency): shared strings, inline strings, cached
formula results, booleans, errors and numbers are all supported, and cells
styled with a date/time number format are rendered as ISO dates.
"""

from __future__ import annotations

import datetime as _dt
import re

from lxml import etree

from agr_abc_document_parsers.models import Document, Section, Table, TableCell
from agr_abc_document_parsers.ooxml_utils import (
    OoxmlPackage,
    attr,
    child,
    children,
    is_true,
    local_name,
)

_WORKBOOK_PART = "xl/workbook.xml"
_SHARED_STRINGS_PART = "xl/sharedStrings.xml"
_STYLES_PART = "xl/styles.xml"

_CELL_REF_RE = re.compile(r"^([A-Za-z]+)(\d*)$")
_INT_RE = re.compile(r"^[+-]?\d+$")
_WS_RE = re.compile(r"\s+")

# Built-in number-format ids that render as dates and/or times.
_BUILTIN_DATE_FORMATS = (
    set(range(14, 23)) | set(range(27, 37)) | set(range(45, 48)) | set(range(50, 59))
)
_BUILTIN_TIME_ONLY_FORMATS = {18, 19, 20, 21, 45, 46, 47}

# Pieces of a custom format code that never indicate a date: quoted
# literals, bracketed sections ([Red], [$-409], [h]) and escaped chars.
_FORMAT_NOISE_RE = re.compile(r'"[^"]*"|\[[^\]]*\]|\\.')
_FORMAT_ELAPSED_RE = re.compile(r"\[(h+|m+|s+)\]", re.IGNORECASE)

_EPOCH_1900 = _dt.datetime(1899, 12, 30)
_EPOCH_1900_PRE_LEAP = _dt.datetime(1899, 12, 31)
_EPOCH_1904 = _dt.datetime(1904, 1, 1)


def parse_xlsx(content: bytes, title: str = "") -> Document:
    """Parse an Excel workbook into a Document model.

    Args:
        content: Raw bytes of an ``.xlsx``/``.xlsm`` file (optionally gzipped).
        title: Document title (the supplement's display name).  Falls back
            to the workbook's ``dc:title`` core property when empty.

    Returns:
        A Document with one section per non-empty worksheet, each holding a
        single table.

    Raises:
        ValueError: If *content* is not an Excel workbook.
    """
    pkg = OoxmlPackage(content)
    if not pkg.has(_WORKBOOK_PART):
        raise ValueError("Not an Excel workbook: missing xl/workbook.xml")
    workbook = pkg.read_xml(_WORKBOOK_PART)
    if workbook is None:
        raise ValueError("Not an Excel workbook: xl/workbook.xml is unreadable")

    doc = Document(source_format="xlsx")
    doc.title = title or pkg.core_title()

    wb_pr = child(workbook, "workbookPr")
    date1904 = wb_pr is not None and is_true(attr(wb_pr, "date1904", "0"))

    shared_strings = _read_shared_strings(pkg)
    date_styles = _read_date_styles(pkg)
    rels = pkg.relationships(_WORKBOOK_PART)

    sheets_elem = child(workbook, "sheets")
    for sheet in children(sheets_elem, "sheet"):
        name = attr(sheet, "name").strip()
        rid = attr(sheet, "id")
        target = rels.get(rid, ("", ""))[0]
        sheet_root = pkg.read_xml(target) if target else None
        if sheet_root is None:
            continue
        rows = _read_sheet_rows(sheet_root, shared_strings, date_styles, date1904)
        if not rows:
            continue
        table = Table(
            rows=[
                [TableCell(text=cell, is_header=(row_idx == 0)) for cell in row]
                for row_idx, row in enumerate(rows)
            ]
        )
        doc.sections.append(Section(heading=name, level=1, tables=[table]))

    return doc


# ---------------------------------------------------------------------------
# Shared strings and styles
# ---------------------------------------------------------------------------


def _rich_text(elem: etree._Element) -> str:
    """Concatenate the <t> runs of an <si> / <is> element, skipping phonetics."""
    parts: list[str] = []
    for node in elem:
        tag = local_name(node)
        if tag == "t":
            parts.append(node.text or "")
        elif tag == "r":
            t = child(node, "t")
            if t is not None:
                parts.append(t.text or "")
        # <rPh> (phonetic guides) and <phoneticPr> are intentionally ignored.
    return "".join(parts)


def _read_shared_strings(pkg: OoxmlPackage) -> list[str]:
    root = pkg.read_xml(_SHARED_STRINGS_PART)
    if root is None:
        return []
    return [_rich_text(si) for si in children(root, "si")]


def _format_is_date(code: str) -> bool:
    """Return True when a custom number-format code renders a date or time."""
    if _FORMAT_ELAPSED_RE.search(code):
        return True
    stripped = _FORMAT_NOISE_RE.sub("", code)
    if "General" in stripped:
        return False
    return any(ch in stripped.lower() for ch in "ymdhs")


def _format_is_time_only(code: str) -> bool:
    stripped = _FORMAT_NOISE_RE.sub("", code).lower()
    return not any(ch in stripped for ch in "yd")


def _read_date_styles(pkg: OoxmlPackage) -> dict[int, str]:
    """Map cell style (xf) indexes to ``"date"`` or ``"time"`` for date formats."""
    root = pkg.read_xml(_STYLES_PART)
    if root is None:
        return {}

    custom: dict[int, str] = {}
    for num_fmt in children(child(root, "numFmts"), "numFmt"):
        try:
            fmt_id = int(attr(num_fmt, "numFmtId"))
        except ValueError:
            continue
        custom[fmt_id] = attr(num_fmt, "formatCode")

    result: dict[int, str] = {}
    for idx, xf in enumerate(children(child(root, "cellXfs"), "xf")):
        try:
            fmt_id = int(attr(xf, "numFmtId", "0"))
        except ValueError:
            continue
        if fmt_id in custom:
            code = custom[fmt_id]
            if _format_is_date(code):
                result[idx] = "time" if _format_is_time_only(code) else "date"
        elif fmt_id in _BUILTIN_DATE_FORMATS:
            result[idx] = "time" if fmt_id in _BUILTIN_TIME_ONLY_FORMATS else "date"
    return result


# ---------------------------------------------------------------------------
# Cell values
# ---------------------------------------------------------------------------


def _col_index(ref: str) -> int | None:
    """Return the zero-based column index of a cell reference like 'B7'."""
    m = _CELL_REF_RE.match(ref.strip())
    if not m:
        return None
    index = 0
    for ch in m.group(1).upper():
        index = index * 26 + (ord(ch) - ord("A") + 1)
    return index - 1


def _format_number(raw: str) -> str:
    raw = raw.strip()
    if _INT_RE.match(raw):
        return str(int(raw))
    try:
        value = float(raw)
    except ValueError:
        return raw
    if value != value or value in (float("inf"), float("-inf")):  # NaN / inf
        return raw
    if value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    return format(value, ".15g")


def _serial_to_datetime(serial: float, date1904: bool) -> _dt.datetime | None:
    if date1904:
        epoch = _EPOCH_1904
    elif serial < 60:
        epoch = _EPOCH_1900_PRE_LEAP
    else:
        epoch = _EPOCH_1900
    try:
        return epoch + _dt.timedelta(days=serial)
    except (OverflowError, ValueError):
        return None


def _format_date(raw: str, kind: str, date1904: bool) -> str:
    try:
        serial = float(raw)
    except ValueError:
        return raw
    if kind == "time":
        total = int(round(serial * 86400))
        hours, rem = divmod(total, 3600)
        minutes, seconds = divmod(rem, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    if not date1904 and 60 <= serial < 61:
        # Excel's fictitious 1900-02-29 (Lotus 1-2-3 compatibility).
        return "1900-02-29"
    value = _serial_to_datetime(serial, date1904)
    if value is None:
        return _format_number(raw)
    # Round to the nearest second to hide floating-point noise.
    value = value + _dt.timedelta(microseconds=500000)
    value = value.replace(microsecond=0)
    if value.hour or value.minute or value.second:
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value.strftime("%Y-%m-%d")


def _cell_text(
    cell: etree._Element,
    shared_strings: list[str],
    date_styles: dict[int, str],
    date1904: bool,
) -> str:
    cell_type = attr(cell, "t", "n")
    v = child(cell, "v")
    raw = (v.text or "") if v is not None else ""

    if cell_type == "s":
        try:
            text = shared_strings[int(raw)]
        except (ValueError, IndexError):
            text = ""
    elif cell_type == "inlineStr":
        is_elem = child(cell, "is")
        text = _rich_text(is_elem) if is_elem is not None else ""
    elif cell_type == "b":
        text = "TRUE" if raw.strip() in ("1", "true", "TRUE") else "FALSE"
    elif cell_type in ("str", "e"):
        text = raw
    elif cell_type == "d":
        text = raw.strip()
        if text.endswith("T00:00:00"):
            text = text[: -len("T00:00:00")]
        text = text.replace("T", " ")
    else:  # "n" or unknown -> numeric
        if not raw.strip():
            text = ""
        else:
            style = attr(cell, "s")
            kind = ""
            if style:
                try:
                    kind = date_styles.get(int(style), "")
                except ValueError:
                    kind = ""
            text = _format_date(raw, kind, date1904) if kind else _format_number(raw)

    return _WS_RE.sub(" ", text).strip()


def _read_sheet_rows(
    sheet_root: etree._Element,
    shared_strings: list[str],
    date_styles: dict[int, str],
    date1904: bool,
) -> list[list[str]]:
    """Return the sheet's non-empty rows, with entirely empty columns removed."""
    sheet_data = child(sheet_root, "sheetData")
    if sheet_data is None:
        return []

    sparse_rows: list[dict[int, str]] = []
    used_cols: set[int] = set()
    for row in children(sheet_data, "row"):
        cells: dict[int, str] = {}
        next_col = 0
        for cell in children(row, "c"):
            col = _col_index(attr(cell, "r"))
            if col is None:
                col = next_col
            next_col = col + 1
            text = _cell_text(cell, shared_strings, date_styles, date1904)
            if text:
                cells[col] = text
                used_cols.add(col)
        if cells:
            sparse_rows.append(cells)

    if not used_cols:
        return []
    columns = sorted(used_cols)
    return [[cells.get(col, "") for col in columns] for cells in sparse_rows]


__all__ = ["parse_xlsx"]
