"""Parse Word documents (.docx / .docm) into the intermediate Document model.

Mapping:

* ``Title``-styled paragraph        -> ``Document.title`` (when no title given)
* ``Heading N`` paragraphs           -> nested :class:`Section` tree
* body paragraphs                    -> :class:`Paragraph` (bold / italic /
  superscript / subscript / hyperlinks preserved as inline Markdown)
* numbered / bulleted paragraphs     -> :class:`ListBlock`
* tables                             -> :class:`Table` (``gridSpan`` padded,
  repeat-header rows flagged)
* footnotes / endnotes               -> ``[^n]`` markers + section notes

The emitter serializes a section's paragraphs, then tables, then lists.  To
keep Word's original block order, the parser opens a heading-less child
section whenever a block would otherwise be emitted ahead of content that
precedes it in the source.  Heading-less sections render transparently.

Reads the OOXML parts directly with ``zipfile`` + ``lxml`` (no python-docx).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from lxml import etree

from agr_abc_document_parsers.models import (
    Document,
    ListBlock,
    Paragraph,
    Section,
    Table,
    TableCell,
)
from agr_abc_document_parsers.ooxml_utils import (
    OoxmlPackage,
    attr,
    child,
    children,
    is_true,
    local_name,
)

_DOCUMENT_PART = "word/document.xml"
_STYLES_PART = "word/styles.xml"
_NUMBERING_PART = "word/numbering.xml"
_FOOTNOTES_PART = "word/footnotes.xml"
_ENDNOTES_PART = "word/endnotes.xml"

_HEADING_NAME_RE = re.compile(r"^heading\s*(\d)$", re.IGNORECASE)
_HEADING_ID_RE = re.compile(r"^Heading(\d)$")
_WS_RE = re.compile(r"\s+")

# Emission order of block kinds inside a Section (see md_emitter._emit_section).
_RANK = {"paragraph": 0, "table": 1, "formula": 2, "list": 3}

# Elements whose content is never part of the visible text.
_SKIP_INLINE = frozenset(
    {
        "pPr",
        "rPr",
        "del",
        "delText",
        "delInstrText",
        "instrText",
        "moveFrom",
        "bookmarkStart",
        "bookmarkEnd",
        "proofErr",
        "commentRangeStart",
        "commentRangeEnd",
        "commentReference",
        "fldChar",
        "lastRenderedPageBreak",
        "footnoteRef",
        "endnoteRef",
        "separator",
        "continuationSeparator",
    }
)


# ---------------------------------------------------------------------------
# Package-level context (styles, numbering, notes, relationships)
# ---------------------------------------------------------------------------


@dataclass
class _Style:
    name: str = ""
    based_on: str = ""
    outline_lvl: int | None = None
    num_id: str = ""
    ilvl: str = "0"


@dataclass
class _Context:
    styles: dict[str, _Style] = field(default_factory=dict)
    numbering: dict[str, dict[str, bool]] = field(default_factory=dict)  # numId -> ilvl -> ordered
    hyperlinks: dict[str, str] = field(default_factory=dict)  # rId -> URL
    footnotes: dict[str, str] = field(default_factory=dict)
    endnotes: dict[str, str] = field(default_factory=dict)
    note_counter: int = 0
    pending_notes: list[str] = field(default_factory=list)
    pending_blocks: list[etree._Element] = field(default_factory=list)

    def resolve_style_chain(self, style_id: str) -> list[_Style]:
        chain: list[_Style] = []
        seen: set[str] = set()
        while style_id and style_id not in seen and style_id in self.styles:
            seen.add(style_id)
            style = self.styles[style_id]
            chain.append(style)
            style_id = style.based_on
        return chain


def _read_styles(pkg: OoxmlPackage) -> dict[str, _Style]:
    root = pkg.read_xml(_STYLES_PART)
    styles: dict[str, _Style] = {}
    if root is None:
        return styles
    for style_elem in children(root, "style"):
        if attr(style_elem, "type", "paragraph") != "paragraph":
            continue
        style_id = attr(style_elem, "styleId")
        if not style_id:
            continue
        style = _Style()
        name_elem = child(style_elem, "name")
        if name_elem is not None:
            style.name = attr(name_elem, "val")
        based_on = child(style_elem, "basedOn")
        if based_on is not None:
            style.based_on = attr(based_on, "val")
        ppr = child(style_elem, "pPr")
        if ppr is not None:
            outline = child(ppr, "outlineLvl")
            if outline is not None:
                try:
                    style.outline_lvl = int(attr(outline, "val"))
                except ValueError:
                    pass
            num_pr = child(ppr, "numPr")
            if num_pr is not None:
                style.num_id, style.ilvl = _num_pr_values(num_pr)
        styles[style_id] = style
    return styles


def _num_pr_values(num_pr: etree._Element) -> tuple[str, str]:
    num_id_elem = child(num_pr, "numId")
    ilvl_elem = child(num_pr, "ilvl")
    num_id = attr(num_id_elem, "val") if num_id_elem is not None else ""
    ilvl = attr(ilvl_elem, "val", "0") if ilvl_elem is not None else "0"
    return num_id, ilvl or "0"


def _read_numbering(pkg: OoxmlPackage) -> dict[str, dict[str, bool]]:
    """Return ``numId -> ilvl -> ordered`` from word/numbering.xml."""
    root = pkg.read_xml(_NUMBERING_PART)
    if root is None:
        return {}
    abstract: dict[str, dict[str, bool]] = {}
    for abs_num in children(root, "abstractNum"):
        abs_id = attr(abs_num, "abstractNumId")
        levels: dict[str, bool] = {}
        for lvl in children(abs_num, "lvl"):
            fmt_elem = child(lvl, "numFmt")
            fmt = attr(fmt_elem, "val", "decimal") if fmt_elem is not None else "decimal"
            levels[attr(lvl, "ilvl", "0")] = fmt not in ("bullet", "none")
        abstract[abs_id] = levels
    numbering: dict[str, dict[str, bool]] = {}
    for num in children(root, "num"):
        num_id = attr(num, "numId")
        abs_ref = child(num, "abstractNumId")
        abs_id = attr(abs_ref, "val") if abs_ref is not None else ""
        levels = dict(abstract.get(abs_id, {}))
        for override in children(num, "lvlOverride"):
            override_lvl = child(override, "lvl")
            if override_lvl is None:
                continue
            fmt_elem = child(override_lvl, "numFmt")
            if fmt_elem is not None:
                levels[attr(override, "ilvl", "0")] = attr(fmt_elem, "val") not in (
                    "bullet",
                    "none",
                )
        numbering[num_id] = levels
    return numbering


def _read_notes(pkg: OoxmlPackage, part: str, tag: str, ctx: _Context) -> dict[str, str]:
    root = pkg.read_xml(part)
    notes: dict[str, str] = {}
    if root is None:
        return notes
    for note in children(root, tag):
        if attr(note, "type"):  # separator / continuationSeparator
            continue
        note_id = attr(note, "id")
        texts = [t for t in (_paragraph_text(p, ctx) for p in children(note, "p")) if t]
        if note_id and texts:
            notes[note_id] = " ".join(texts)
    return notes


# ---------------------------------------------------------------------------
# Section flow
# ---------------------------------------------------------------------------


class _Flow:
    """Builds the Section tree while preserving source block order."""

    def __init__(self) -> None:
        self.sections: list[Section] = []
        self._stack: list[Section] = []  # real (headed) sections by level
        self._container: Section | None = None
        self._open_list: ListBlock | None = None
        self._open_list_key: tuple[str, bool] | None = None

    def add_heading(self, text: str, level: int) -> None:
        level = max(1, min(level, len(self._stack) + 1))
        section = Section(heading=text, level=level)
        del self._stack[level - 1 :]
        if self._stack:
            self._stack[-1].subsections.append(section)
        else:
            self.sections.append(section)
        self._stack.append(section)
        self._container = section
        self._open_list = None

    def _target(self, kind: str) -> Section:
        container = self._container
        if container is None:
            container = Section(level=1)
            self.sections.append(container)
            self._container = container
            return container
        rank = _RANK[kind]
        later = (
            (rank < _RANK["table"] and container.tables)
            or (rank < _RANK["formula"] and container.formulas)
            or (rank < _RANK["list"] and container.lists)
            or container.subsections
        )
        if later:
            anon = Section(level=container.level + 1)
            container.subsections.append(anon)
            self._container = anon
            return anon
        return container

    def add_notes(self, notes: list[str]) -> None:
        if notes:
            self._target("paragraph").notes.extend(notes)

    def add_paragraph(self, text: str, notes: list[str]) -> None:
        self._open_list = None
        target = self._target("paragraph")
        target.paragraphs.append(Paragraph(text=text))
        target.notes.extend(notes)

    def add_table(self, table: Table, notes: list[str]) -> None:
        self._open_list = None
        target = self._target("table")
        target.tables.append(table)
        target.notes.extend(notes)

    def add_list_item(self, text: str, num_id: str, ordered: bool, notes: list[str]) -> None:
        key = (num_id, ordered)
        if self._open_list is not None and self._open_list_key == key and not notes:
            self._open_list.items.append(text)
            return
        target = self._target("list")
        block = ListBlock(items=[text], ordered=ordered)
        target.lists.append(block)
        target.notes.extend(notes)
        self._open_list = block
        self._open_list_key = key


# ---------------------------------------------------------------------------
# Inline text
# ---------------------------------------------------------------------------


@dataclass
class _Run:
    text: str
    bold: bool = False
    italic: bool = False
    vert: str = ""  # "", "sup", "sub"
    literal: bool = False  # pre-rendered Markdown (hyperlinks); never wrapped

    def fmt(self) -> tuple[bool, bool, str, bool]:
        return (self.bold, self.italic, self.vert, self.literal)


def _iter_content(elem: etree._Element) -> list[etree._Element]:
    """Children of *elem*, descending into only one branch of AlternateContent."""
    out: list[etree._Element] = []
    for c in elem:
        name = local_name(c)
        if name == "AlternateContent":
            branch = child(c, "Choice")
            if branch is None:
                branch = child(c, "Fallback")
            if branch is not None:
                out.extend(_iter_content(branch))
        else:
            out.append(c)
    return out


def _run_format(run: etree._Element) -> tuple[bool, bool, str]:
    rpr = child(run, "rPr")
    if rpr is None:
        return False, False, ""
    bold = italic = False
    vert = ""
    for prop in rpr:
        name = local_name(prop)
        if name == "b":
            bold = is_true(attr(prop, "val"))
        elif name == "i":
            italic = is_true(attr(prop, "val"))
        elif name == "vertAlign":
            val = attr(prop, "val")
            vert = "sup" if val == "superscript" else "sub" if val == "subscript" else ""
    return bold, italic, vert


def _collect_runs(elem: etree._Element, ctx: _Context, out: list[_Run]) -> None:
    for node in _iter_content(elem):
        name = local_name(node)
        if name in _SKIP_INLINE:
            continue
        if name == "r":
            _collect_run(node, ctx, out)
        elif name == "hyperlink":
            inner: list[_Run] = []
            _collect_runs(node, ctx, inner)
            text = _render_runs(inner)
            url = ctx.hyperlinks.get(attr(node, "id"), "")
            if url and text:
                out.append(_Run(text=f"[{text}]({url})", literal=True))
            elif url:
                out.append(_Run(text=url, literal=True))
            elif text:
                out.append(_Run(text=text, literal=True))
        elif name in ("oMath", "oMathPara"):
            math = "".join(t.text or "" for t in node.iter() if local_name(t) == "t")
            if math.strip():
                out.append(_Run(text=math))
        elif name in ("drawing", "pict", "object"):
            _queue_text_boxes(node, ctx)
        else:
            # ins, smartTag, sdt, sdtContent, customXml, fldSimple, moveTo, dir, bdo ...
            _collect_runs(node, ctx, out)


def _collect_run(run: etree._Element, ctx: _Context, out: list[_Run]) -> None:
    bold, italic, vert = _run_format(run)
    for node in _iter_content(run):
        name = local_name(node)
        if name in ("drawing", "pict", "object"):
            _queue_text_boxes(node, ctx)
            continue
        if name == "t":
            text = node.text or ""
        elif name in ("tab", "br", "cr"):
            text = " "
        elif name == "noBreakHyphen":
            text = "-"
        elif name == "footnoteReference":
            text = _note_marker(ctx, ctx.footnotes, attr(node, "id"))
        elif name == "endnoteReference":
            text = _note_marker(ctx, ctx.endnotes, attr(node, "id"))
        else:
            # rPr, sym, softHyphen, fldChar, instrText, delText, ...
            continue
        if text:
            out.append(_Run(text=text, bold=bold, italic=italic, vert=vert))


def _queue_text_boxes(node: etree._Element, ctx: _Context) -> None:
    """Queue the block content of the first text box under *node* (if any)."""
    for txbx in node.iter():
        if local_name(txbx) == "txbxContent":
            ctx.pending_blocks.extend(_iter_content(txbx))
            return


def _note_marker(ctx: _Context, notes: dict[str, str], note_id: str) -> str:
    body = notes.get(note_id, "")
    if not body:
        return ""
    ctx.note_counter += 1
    ctx.pending_notes.append(body)
    return f"[^{ctx.note_counter}]"


def _wrap(text: str, run: _Run) -> str:
    if run.literal:
        return text
    if run.vert == "sup":
        text = f"<sup>{text}</sup>"
    elif run.vert == "sub":
        text = f"<sub>{text}</sub>"
    if run.italic:
        text = f"*{text}*"
    if run.bold:
        text = f"**{text}**"
    return text


def _render_runs(runs: list[_Run]) -> str:
    # Merge adjacent runs with identical formatting (Word splits runs freely).
    merged: list[_Run] = []
    for run in runs:
        if merged and not run.literal and merged[-1].fmt() == run.fmt():
            merged[-1].text += run.text
        else:
            merged.append(_Run(run.text, run.bold, run.italic, run.vert, run.literal))

    parts: list[str] = []
    for run in merged:
        text = run.text
        core = text.strip()
        if not core:
            parts.append(text)
            continue
        lead = text[: len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()) :]
        parts.append(lead + _wrap(_WS_RE.sub(" ", core), run) + trail)
    return _WS_RE.sub(" ", "".join(parts)).strip()


def _paragraph_text(p: etree._Element, ctx: _Context) -> str:
    runs: list[_Run] = []
    _collect_runs(p, ctx, runs)
    return _render_runs(runs)


# ---------------------------------------------------------------------------
# Paragraph classification
# ---------------------------------------------------------------------------


def _paragraph_style_id(p: etree._Element) -> str:
    ppr = child(p, "pPr")
    style = child(ppr, "pStyle") if ppr is not None else None
    return attr(style, "val") if style is not None else ""


def _heading_level(p: etree._Element, ctx: _Context) -> int | None:
    """Return the heading level (1-based) for *p*, or None for body text."""
    ppr = child(p, "pPr")
    outline = child(ppr, "outlineLvl") if ppr is not None else None
    if outline is not None:
        try:
            lvl = int(attr(outline, "val"))
        except ValueError:
            lvl = 9
        return lvl + 1 if 0 <= lvl < 9 else None
    style_id = _paragraph_style_id(p)
    m = _HEADING_ID_RE.match(style_id)
    if m:
        return int(m.group(1))
    for style in ctx.resolve_style_chain(style_id):
        m = _HEADING_NAME_RE.match(style.name)
        if m:
            return int(m.group(1))
        if style.outline_lvl is not None:
            return style.outline_lvl + 1 if style.outline_lvl < 9 else None
    return None


def _is_title_style(p: etree._Element, ctx: _Context) -> bool:
    style_id = _paragraph_style_id(p)
    if style_id == "Title":
        return True
    chain = ctx.resolve_style_chain(style_id)
    return bool(chain) and chain[0].name.strip().lower() == "title"


def _list_info(p: etree._Element, ctx: _Context) -> tuple[str, bool] | None:
    """Return ``(numId, ordered)`` when *p* is a list item, else None."""
    ppr = child(p, "pPr")
    num_pr = child(ppr, "numPr") if ppr is not None else None
    num_id = ""
    ilvl = "0"
    if num_pr is not None:
        num_id, ilvl = _num_pr_values(num_pr)
    else:
        for style in ctx.resolve_style_chain(_paragraph_style_id(p)):
            if style.num_id:
                num_id, ilvl = style.num_id, style.ilvl
                break
    if not num_id or num_id == "0":
        return None
    levels = ctx.numbering.get(num_id)
    if levels is None:
        return None
    ordered = levels.get(ilvl, levels.get("0", True))
    return num_id, ordered


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------


def _take_notes(ctx: _Context) -> list[str]:
    notes = list(ctx.pending_notes)
    ctx.pending_notes.clear()
    return notes


def _parse_table(tbl: etree._Element, ctx: _Context) -> Table | None:
    table = Table()
    tbl_pr = child(tbl, "tblPr")
    caption_elem = child(tbl_pr, "tblCaption") if tbl_pr is not None else None
    if caption_elem is not None:
        table.caption = _WS_RE.sub(" ", attr(caption_elem, "val")).strip()

    has_text = False
    for tr in _iter_content(tbl):
        if local_name(tr) != "tr":
            continue
        tr_pr = child(tr, "trPr")
        is_header = tr_pr is not None and child(tr_pr, "tblHeader") is not None
        row: list[TableCell] = []
        for tc in _iter_content(tr):
            if local_name(tc) != "tc":
                continue
            texts: list[str] = []
            for block in _iter_content(tc):
                name = local_name(block)
                if name == "p":
                    text = _paragraph_text(block, ctx)
                elif name == "tbl":
                    nested = _parse_table(block, ctx)
                    text = (
                        " ".join(c.text for r in nested.rows for c in r if c.text) if nested else ""
                    )
                elif name in ("sdt", "customXml"):
                    text = " ".join(
                        t
                        for t in (
                            _paragraph_text(p, ctx) for p in block.iter() if local_name(p) == "p"
                        )
                        if t
                    )
                else:
                    continue
                if text:
                    texts.append(text)
            cell_text = " ".join(texts)
            if cell_text:
                has_text = True
            row.append(TableCell(text=cell_text, is_header=is_header))
            tc_pr = child(tc, "tcPr")
            span_elem = child(tc_pr, "gridSpan") if tc_pr is not None else None
            if span_elem is not None:
                try:
                    span = int(attr(span_elem, "val", "1"))
                except ValueError:
                    span = 1
                for _ in range(max(span - 1, 0)):
                    row.append(TableCell(text="", is_header=is_header))
        if row:
            table.rows.append(row)

    if not has_text:
        return None
    width = max(len(r) for r in table.rows)
    for row in table.rows:
        while len(row) < width:
            row.append(TableCell(text="", is_header=row[0].is_header if row else False))
    return table


def _handle_paragraph(p: etree._Element, flow: _Flow, ctx: _Context, doc: Document) -> None:
    level = _heading_level(p, ctx)
    text = _paragraph_text(p, ctx)
    notes = _take_notes(ctx)

    if text:
        if level is not None:
            flow.add_heading(text, level)
            flow.add_notes(notes)
        elif not doc.title and _is_title_style(p, ctx):
            doc.title = text
        else:
            info = _list_info(p, ctx)
            if info is not None:
                flow.add_list_item(text, info[0], info[1], notes)
            else:
                flow.add_paragraph(text, notes)
    else:
        flow.add_notes(notes)

    _flush_pending_blocks(flow, ctx, doc)


def _flush_pending_blocks(flow: _Flow, ctx: _Context, doc: Document) -> None:
    while ctx.pending_blocks:
        blocks = list(ctx.pending_blocks)
        ctx.pending_blocks.clear()
        for block in blocks:
            _handle_block(block, flow, ctx, doc)


def _handle_block(block: etree._Element, flow: _Flow, ctx: _Context, doc: Document) -> None:
    name = local_name(block)
    if name == "p":
        _handle_paragraph(block, flow, ctx, doc)
    elif name == "tbl":
        table = _parse_table(block, ctx)
        notes = _take_notes(ctx)
        if table is not None:
            flow.add_table(table, notes)
        else:
            flow.add_notes(notes)
        _flush_pending_blocks(flow, ctx, doc)
    elif name in ("sdt", "customXml", "sdtContent", "smartTag", "ins", "moveTo"):
        for inner in _iter_content(block):
            _handle_block(inner, flow, ctx, doc)
    # sectPr, bookmarkStart/End, proofErr, del, altChunk ... are ignored.


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse_docx(content: bytes, title: str = "") -> Document:
    """Parse a Word document into a Document model.

    Args:
        content: Raw bytes of a ``.docx``/``.docm`` file (optionally gzipped).
        title: Document title (the supplement's display name).  When empty,
            the first ``Title``-styled paragraph is used, then the package's
            ``dc:title`` core property.

    Returns:
        A populated Document.

    Raises:
        ValueError: If *content* is not a Word document.
    """
    pkg = OoxmlPackage(content)
    if not pkg.has(_DOCUMENT_PART):
        raise ValueError("Not a Word document: missing word/document.xml")
    root = pkg.read_xml(_DOCUMENT_PART)
    body = child(root, "body") if root is not None else None
    if body is None:
        raise ValueError("Not a Word document: word/document.xml has no <body>")

    ctx = _Context()
    ctx.styles = _read_styles(pkg)
    ctx.numbering = _read_numbering(pkg)
    ctx.hyperlinks = {
        rid: target
        for rid, (target, mode) in pkg.relationships(_DOCUMENT_PART).items()
        if mode == "External"
    }
    ctx.footnotes = _read_notes(pkg, _FOOTNOTES_PART, "footnote", ctx)
    ctx.endnotes = _read_notes(pkg, _ENDNOTES_PART, "endnote", ctx)
    ctx.pending_notes.clear()
    ctx.pending_blocks.clear()
    ctx.note_counter = 0

    doc = Document(source_format="docx", title=title)
    flow = _Flow()
    for block in _iter_content(body):
        _handle_block(block, flow, ctx, doc)

    doc.sections = flow.sections
    if not doc.title:
        doc.title = pkg.core_title()
    return doc


__all__ = ["parse_docx"]
