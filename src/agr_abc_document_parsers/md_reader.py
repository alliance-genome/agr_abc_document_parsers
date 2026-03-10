"""Parse ABC-format Markdown back into a Document model."""
from __future__ import annotations

import re

from agr_abc_document_parsers.models import (
    Author,
    Document,
    Figure,
    ListBlock,
    Paragraph,
    Reference,
    Section,
    Table,
    TableCell,
)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_KEYWORDS_RE = re.compile(r"^\*\*Keywords:\*\*\s*(.+)$")
_BOLD_LABEL_RE = re.compile(r"^\*\*(.+?)\.\*\*(?:\s+(.*))?$")
_FIGURE_LABEL_RE = re.compile(
    r"^(Figure|Fig\.|Supplementary Figure|Supplementary Fig\.)\s*\d+",
    re.IGNORECASE,
)
_TABLE_LABEL_RE = re.compile(
    r"^(Table|Supplementary Table)\s*\d+",
    re.IGNORECASE,
)
_FOOTNOTE_RE = re.compile(r"^\[\^(\d+)\]:\s+(.+)$")
_ORDERED_LIST_RE = re.compile(r"^(\d+)\.\s+(.+)$")
_REF_LINE_RE = re.compile(r"^(\d+)\.\s*(.*)$")
_GFM_SEP_RE = re.compile(r"^\|[-:| ]+\|$")
_REF_YEAR_RE = re.compile(r"\((\d{4}[a-z]?)\)")
_REF_ITALIC_RE = re.compile(r"\*([^*]+)\*")
_REF_VOL_RE = re.compile(r"^(\d+)(?:\(([^)]+)\))?$")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def read_markdown(text: str) -> Document:
    """Parse ABC-format Markdown into a Document model.

    Handles both complete documents (with title, abstract, sections,
    references) and partial documents like supplements (which may lack
    a title, abstract, or references section).
    """
    doc = Document()
    lines = text.split("\n")
    # Strip trailing empty lines
    while lines and not lines[-1].strip():
        lines.pop()

    n = len(lines)
    if n == 0:
        return doc

    pos = _skip_blank(lines, 0, n)

    # --- Title (H1) ---
    if pos < n and _heading_level(lines[pos]) == 1:
        doc.title = _heading_text(lines[pos])
        pos += 1
        pos = _skip_blank(lines, pos, n)

    # --- Author line (non-heading, non-keyword, non-bold-label before first H2) ---
    if (
        pos < n
        and _heading_level(lines[pos]) == 0
        and not _KEYWORDS_RE.match(lines[pos])
        and not _BOLD_LABEL_RE.match(lines[pos])
        and not lines[pos].startswith("|")
        and not lines[pos].startswith("- ")
        and not lines[pos].startswith("> ")
        and not _FOOTNOTE_RE.match(lines[pos])
    ):
        doc.authors = _parse_author_line(lines[pos])
        pos += 1
        pos = _skip_blank(lines, pos, n)

    # --- Keywords before first H2 (if no abstract) ---
    if pos < n and _KEYWORDS_RE.match(lines[pos]):
        doc.keywords = _parse_keywords(lines[pos])
        pos += 1
        pos = _skip_blank(lines, pos, n)

    # --- Preamble content before first H2 (for partial/supplement docs) ---
    preamble_lines: list[str] = []
    while pos < n and _heading_level(lines[pos]) == 0:
        preamble_lines.append(lines[pos])
        pos += 1
    if preamble_lines:
        section = _parse_section_lines("", preamble_lines, 2)
        if section.paragraphs or section.figures or section.tables or section.lists:
            doc.sections.append(section)

    # --- H2+ sections ---
    h2_blocks = _collect_h2_blocks(lines, pos, n)

    found_ack = False
    found_ref = False
    for heading, content_lines in h2_blocks:
        if heading == "Abstract":
            doc.abstract, kw = _parse_abstract_lines(content_lines)
            if kw and not doc.keywords:
                doc.keywords = kw
        elif heading == "Acknowledgments":
            doc.acknowledgments = _parse_acknowledgments_lines(content_lines)
            found_ack = True
        elif heading == "References":
            refs = _parse_references_lines(content_lines)
            if refs:
                doc.references = refs
                found_ref = True
            elif found_ack:
                # Empty ## References from back_matter — preserve as section
                doc.back_matter.append(
                    _parse_section_lines(heading, content_lines, 2)
                )
        elif found_ack and not found_ref:
            doc.back_matter.append(
                _parse_section_lines(heading, content_lines, 2)
            )
        else:
            doc.sections.append(
                _parse_section_lines(heading, content_lines, 2)
            )

    return doc


def load_document_with_supplements(
    main_md: str,
    supplement_mds: list[str] | None = None,
) -> Document:
    """Parse a main document and its supplements into a single Document.

    Args:
        main_md: Markdown text of the main paper.
        supplement_mds: Optional list of Markdown texts for each supplement.

    Returns:
        A Document with supplements populated.
    """
    doc = read_markdown(main_md)
    if supplement_mds:
        for supp_md in supplement_mds:
            doc.supplements.append(read_markdown(supp_md))
    return doc


# ---------------------------------------------------------------------------
# Line-level helpers
# ---------------------------------------------------------------------------


def _heading_level(line: str) -> int:
    """Return heading level (1-6) or 0 if not a heading."""
    if not line.startswith("#"):
        return 0
    level = 0
    for ch in line:
        if ch == "#":
            level += 1
        else:
            break
    if 0 < level <= 6 and level < len(line) and line[level] == " ":
        return level
    return 0


def _heading_text(line: str) -> str:
    """Extract heading text from a heading line."""
    m = _HEADING_RE.match(line)
    return m.group(2) if m else ""


def _skip_blank(lines: list[str], pos: int, n: int) -> int:
    """Advance past blank lines."""
    while pos < n and not lines[pos].strip():
        pos += 1
    return pos


# ---------------------------------------------------------------------------
# Header parsing (title, authors, keywords)
# ---------------------------------------------------------------------------


def _parse_author_line(line: str) -> list[Author]:
    """Parse comma-separated author names into Author objects."""
    authors: list[Author] = []
    for name in line.split(", "):
        name = name.strip()
        if not name:
            continue
        parts = name.rsplit(" ", 1)
        if len(parts) == 2:
            authors.append(Author(given_name=parts[0], surname=parts[1]))
        else:
            authors.append(Author(surname=parts[0]))
    return authors


def _parse_keywords(line: str) -> list[str]:
    """Parse **Keywords:** line into a list of strings."""
    m = _KEYWORDS_RE.match(line)
    if not m:
        return []
    return [k.strip() for k in m.group(1).split(",") if k.strip()]


# ---------------------------------------------------------------------------
# H2 block collection
# ---------------------------------------------------------------------------


def _collect_h2_blocks(
    lines: list[str], start: int, end: int,
) -> list[tuple[str, list[str]]]:
    """Collect H2 sections as (heading_text, content_lines) tuples."""
    blocks: list[tuple[str, list[str]]] = []
    pos = start
    while pos < end:
        if _heading_level(lines[pos]) == 2:
            heading = _heading_text(lines[pos])
            pos += 1
            content_start = pos
            while pos < end and _heading_level(lines[pos]) != 2:
                pos += 1
            blocks.append((heading, lines[content_start:pos]))
        else:
            pos += 1
    return blocks


# ---------------------------------------------------------------------------
# Abstract
# ---------------------------------------------------------------------------


def _parse_abstract_lines(
    content_lines: list[str],
) -> tuple[list[Paragraph], list[str]]:
    """Parse abstract content lines. Returns (paragraphs, keywords)."""
    paragraphs: list[Paragraph] = []
    keywords: list[str] = []
    for line in content_lines:
        if not line.strip():
            continue
        m_kw = _KEYWORDS_RE.match(line)
        if m_kw:
            keywords = [k.strip() for k in m_kw.group(1).split(",") if k.strip()]
        else:
            paragraphs.append(Paragraph(text=line))
    return paragraphs, keywords


# ---------------------------------------------------------------------------
# Acknowledgments
# ---------------------------------------------------------------------------


def _parse_acknowledgments_lines(content_lines: list[str]) -> str:
    """Parse acknowledgments content into a single string."""
    parts: list[str] = []
    for line in content_lines:
        if line.strip():
            parts.append(line)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# References
# ---------------------------------------------------------------------------


def _parse_references_lines(content_lines: list[str]) -> list[Reference]:
    """Parse numbered reference entries."""
    refs: list[Reference] = []
    for line in content_lines:
        line = line.strip()
        if not line:
            continue
        m = _REF_LINE_RE.match(line)
        if m:
            ref = _parse_reference_entry(int(m.group(1)), m.group(2).strip())
            refs.append(ref)
    return refs


def _parse_reference_entry(index: int, text: str) -> Reference:
    """Parse a single reference entry text into a Reference object."""
    ref = Reference(index=index)

    # Strip identifiers from the right
    text = _strip_ref_ids(text, ref)

    # Find (year)
    m_year = _REF_YEAR_RE.search(text)
    if not m_year:
        # No year found — store everything as title
        ref.title = text.rstrip(". ")
        return ref

    ref.year = m_year.group(1)
    authors_str = text[: m_year.start()].rstrip(" ,")
    after_year = text[m_year.end() :].strip()

    # Authors
    if authors_str:
        ref.authors = [a.strip() for a in authors_str.split(", ")]

    # Parse post-year content: Title. [In: chapter.] [Edited by ...] [*source*...] [Publisher.]
    _parse_ref_body(after_year, ref)

    return ref


def _strip_ref_ids(text: str, ref: Reference) -> str:
    """Strip doi, PMID, PMCID, ext_links from end of reference text."""
    while True:
        text = text.rstrip()

        # ext_links (URLs)
        m = re.search(r"\s+(https?://\S+)$", text)
        if m:
            ref.ext_links.insert(0, m.group(1))
            text = text[: m.start()]
            continue

        # PMCID
        m = re.search(r"\s+PMCID:(\S+)$", text)
        if m:
            ref.pmcid = m.group(1)
            text = text[: m.start()]
            continue

        # PMID
        m = re.search(r"\s+PMID:(\S+)$", text)
        if m:
            ref.pmid = m.group(1)
            text = text[: m.start()]
            continue

        # doi
        m = re.search(r"\s+doi:(\S+)$", text)
        if m:
            ref.doi = m.group(1)
            text = text[: m.start()]
            continue

        break
    return text


def _parse_ref_body(text: str, ref: Reference) -> None:
    """Parse title, journal, editors, publisher from reference body."""
    if not text:
        return

    remaining = text

    # Find italic source markers (*Journal* or *Conference*)
    italic_matches = list(_REF_ITALIC_RE.finditer(remaining))

    if not italic_matches:
        # No italic — just title (possibly with publisher)
        ref.title = remaining.rstrip(". ").rstrip(".")
        return

    first_italic_pos = italic_matches[0].start()

    # Everything before first italic: title [+ In: chapter. + Edited by editors.]
    before_italic = remaining[:first_italic_pos].rstrip()

    # Parse title + chapter + editors from before_italic
    _parse_title_chapter_editors(before_italic, ref)

    # Parse source (journal/conference/publisher) from italic onwards
    from_italic = remaining[first_italic_pos:]
    _parse_ref_source(from_italic, ref, italic_matches, first_italic_pos)


def _parse_title_chapter_editors(text: str, ref: Reference) -> None:
    """Parse title, 'In: chapter.', 'Edited by editors.' from text before italic source."""
    remaining = text

    # Check for "Edited by ..." at end (before the source part)
    m_ed = re.search(r"\.\s+Edited by\s+(.+)\.\s*$", remaining)
    if m_ed:
        ref.editors = [e.strip() for e in m_ed.group(1).split(", ")]
        remaining = remaining[: m_ed.start() + 1]  # keep the period before "Edited by"

    # Check for "In: chapter." at end of remaining
    m_chap = re.search(r"\.\s+In:\s+(.+)\.\s*$", remaining)
    if m_chap:
        ref.chapter_title = m_chap.group(1)
        remaining = remaining[: m_chap.start() + 1]

    # Remaining is the title (strip trailing period)
    ref.title = remaining.rstrip(". ").rstrip(".")


def _parse_ref_source(
    text: str, ref: Reference,
    italic_matches: list[re.Match[str]],  # type: ignore[type-arg]
    offset: int,
) -> None:
    """Parse journal/conference/publisher from text starting with italic markers."""
    remaining = text

    # Match first italic: journal name
    m_italic = _REF_ITALIC_RE.match(remaining)
    if not m_italic:
        return
    ref.journal = m_italic.group(1)
    remaining = remaining[m_italic.end():]

    # Parse volume, issue, pages after journal
    remaining = _parse_journal_details(remaining, ref)

    # Check for second italic: conference
    remaining = remaining.strip()
    m_conf = _REF_ITALIC_RE.match(remaining)
    if m_conf:
        ref.conference = m_conf.group(1)
        remaining = remaining[m_conf.end():].lstrip(".").strip()

    # Remaining: publisher
    _parse_publisher(remaining, ref)


def _parse_journal_details(text: str, ref: Reference) -> str:
    """Parse optional , vol[(issue)][, pages]. after journal name."""
    if not text.startswith(","):
        # Just *Journal*. or *Journal* — strip trailing period
        return text.lstrip(".").strip()

    # Strip leading comma and space
    inner = text[1:].lstrip()

    # Find the terminating period for the journal part
    dot_pos = inner.find(".")
    if dot_pos < 0:
        # No period found — treat all as pages
        ref.pages = inner.strip()
        return ""

    parts_str = inner[:dot_pos]
    remaining = inner[dot_pos + 1:]

    # Split by ", " to get vol/pages parts
    parts = [p.strip() for p in parts_str.split(",") if p.strip()]
    if not parts:
        return remaining

    first = parts[0]
    m_vol = _REF_VOL_RE.match(first)
    if m_vol:
        # First part is volume (possibly with issue)
        ref.volume = m_vol.group(1)
        if m_vol.group(2):
            ref.issue = m_vol.group(2)
        if len(parts) > 1:
            ref.pages = ", ".join(parts[1:])
    else:
        # First part is pages (contains non-digit characters like hyphen)
        ref.pages = ", ".join(parts)

    return remaining


def _parse_publisher(text: str, ref: Reference) -> None:
    """Parse publisher location and name from remaining reference text."""
    text = text.strip().rstrip(".")
    if not text:
        return
    if ": " in text:
        parts = text.split(": ", 1)
        ref.publisher_loc = parts[0].strip()
        ref.publisher = parts[1].strip().rstrip(".")
    else:
        ref.publisher = text.strip().rstrip(".")


# ---------------------------------------------------------------------------
# Section content parsing
# ---------------------------------------------------------------------------


def _parse_section_lines(
    heading: str, content_lines: list[str], heading_level: int,
) -> Section:
    """Parse section content lines into a Section object."""
    section = Section(heading=heading, level=max(1, heading_level - 1))

    n = len(content_lines)
    i = 0
    last_table: Table | None = None
    capture_table_fns = False
    table_fn_collected = 0

    while i < n:
        line = content_lines[i]

        # Blank line
        if not line.strip():
            if capture_table_fns and table_fn_collected > 0:
                capture_table_fns = False
                table_fn_collected = 0
            i += 1
            continue

        # Subsection heading
        hlevel = _heading_level(line)
        if hlevel > 0 and hlevel > heading_level:
            sub_heading = _heading_text(line)
            i += 1
            # Collect subsection content until next heading at same or lower level
            sub_start = i
            while i < n:
                hl = _heading_level(content_lines[i])
                if hl > 0 and hl <= hlevel:
                    break
                i += 1
            sub_section = _parse_section_lines(
                sub_heading, content_lines[sub_start:i], hlevel,
            )
            section.subsections.append(sub_section)
            last_table = None
            capture_table_fns = False
            table_fn_collected = 0
            continue

        # GFM table
        if line.startswith("|"):
            table_lines: list[str] = []
            while i < n and content_lines[i].startswith("|"):
                table_lines.append(content_lines[i])
                i += 1
            table = _parse_gfm_table(table_lines)
            section.tables.append(table)
            last_table = table
            capture_table_fns = False
            table_fn_collected = 0
            continue

        # Bold label: **Label.** [Caption]
        m_label = _BOLD_LABEL_RE.match(line)
        if m_label:
            label = m_label.group(1)
            caption = m_label.group(2) or ""

            if _TABLE_LABEL_RE.match(label):
                # Table caption — attach to preceding table
                if last_table is not None:
                    last_table.label = label
                    last_table.caption = caption
                else:
                    # Orphan table caption — create table with just caption
                    t = Table(label=label, caption=caption)
                    section.tables.append(t)
                    last_table = t
                capture_table_fns = True
                table_fn_collected = 0
                i += 1
                continue

            if _FIGURE_LABEL_RE.match(label):
                section.figures.append(Figure(label=label, caption=caption))
                last_table = None
                capture_table_fns = False
                table_fn_collected = 0
                i += 1
                continue

            # Other bold labels (e.g., Supplementary File) — treat as figure
            section.figures.append(Figure(label=label, caption=caption))
            last_table = None
            capture_table_fns = False
            table_fn_collected = 0
            i += 1
            continue

        # Footnote: [^N]: text
        m_fn = _FOOTNOTE_RE.match(line)
        if m_fn:
            section.notes.append(m_fn.group(2))
            i += 1
            capture_table_fns = False
            table_fn_collected = 0
            continue

        # Unordered list: - item
        if line.startswith("- "):
            items: list[str] = []
            while i < n and content_lines[i].startswith("- "):
                items.append(content_lines[i][2:])
                i += 1
            section.lists.append(ListBlock(items=items, ordered=False))
            last_table = None
            capture_table_fns = False
            table_fn_collected = 0
            continue

        # Ordered list: N. item (not in References context)
        m_ol = _ORDERED_LIST_RE.match(line)
        if m_ol and not capture_table_fns:
            items_ol: list[str] = []
            while i < n:
                m2 = _ORDERED_LIST_RE.match(content_lines[i])
                if m2:
                    items_ol.append(m2.group(2))
                    i += 1
                else:
                    break
            section.lists.append(ListBlock(items=items_ol, ordered=True))
            last_table = None
            capture_table_fns = False
            table_fn_collected = 0
            continue

        # Keywords (may appear in abstract block content)
        if _KEYWORDS_RE.match(line):
            i += 1
            continue

        # Table footnotes: plain text after a table caption
        if capture_table_fns and last_table is not None:
            last_table.foot_notes.append(line)
            table_fn_collected += 1
            i += 1
            continue

        # Block quote: > text
        if line.startswith("> "):
            section.paragraphs.append(Paragraph(text=line[2:]))
            i += 1
            last_table = None
            capture_table_fns = False
            table_fn_collected = 0
            continue

        # Default: paragraph
        section.paragraphs.append(Paragraph(text=line))
        last_table = None
        capture_table_fns = False
        table_fn_collected = 0
        i += 1

    return section


# ---------------------------------------------------------------------------
# GFM table parsing
# ---------------------------------------------------------------------------


def _parse_gfm_table(table_lines: list[str]) -> Table:
    """Parse GFM table lines into a Table object."""
    table = Table()
    header_done = False

    for line in table_lines:
        line = line.strip()
        if not line:
            continue

        # Separator row
        if _GFM_SEP_RE.match(line):
            header_done = True
            continue

        # Parse cells
        cells = _parse_table_row(line)
        if not header_done:
            # Header row
            table.rows.append(
                [TableCell(text=c, is_header=True) for c in cells]
            )
        else:
            table.rows.append(
                [TableCell(text=c, is_header=False) for c in cells]
            )

    return table


def _parse_table_row(line: str) -> list[str]:
    """Parse a GFM table row into cell text values."""
    # Strip leading/trailing pipes
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]

    # Split on unescaped pipes
    cells: list[str] = []
    current = ""
    i = 0
    while i < len(line):
        if line[i] == "\\" and i + 1 < len(line) and line[i + 1] == "|":
            current += "|"
            i += 2
        elif line[i] == "|":
            cells.append(current.strip())
            current = ""
            i += 1
        else:
            current += line[i]
            i += 1
    cells.append(current.strip())

    return cells
