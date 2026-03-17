"""Emit docling-style Markdown from the intermediate Document model."""

from __future__ import annotations

from agr_abc_document_parsers.models import (
    Document,
    Figure,
    ListBlock,
    Reference,
    Section,
    Table,
)

MAX_HEADING_LEVEL = 6


def emit_markdown(doc: Document) -> str:
    """Convert a Document model to a Markdown string.

    Args:
        doc: A populated Document dataclass.

    Returns:
        A docling-style Markdown string.
    """
    lines: list[str] = []

    _emit_title(doc, lines)
    _emit_metadata(doc, lines)
    _emit_categories(doc, lines)
    _emit_authors(doc, lines)
    _emit_abstract(doc, lines)
    _emit_secondary_abstracts(doc, lines)
    _emit_keywords(doc, lines)
    footnote_counter = [0]  # mutable counter shared across sections
    _emit_sections(doc.sections, lines, base_level=2, footnote_counter=footnote_counter)
    _emit_doc_level_figures(doc, lines)
    _emit_doc_level_tables(doc, lines)
    _emit_acknowledgments(doc, lines)
    _emit_funding(doc, lines)
    _emit_author_notes(doc, lines)
    _emit_competing_interests(doc, lines)
    _emit_data_availability(doc, lines)
    _emit_back_matter(doc, lines, footnote_counter=footnote_counter)
    _emit_references(doc, lines)
    _emit_author_roles(doc, lines)
    _emit_sub_articles(doc, lines)

    return "\n".join(lines).rstrip("\n") + "\n"


def _emit_title(doc: Document, lines: list[str]) -> None:
    if not doc.title:
        return
    lines.append(f"# {doc.title}")
    lines.append("")
    for tt in doc.trans_titles:
        lines.append(f"*{tt}*")
        lines.append("")


def _emit_metadata(doc: Document, lines: list[str]) -> None:
    """Emit article-level metadata block after the title."""
    meta_parts: list[str] = []
    if doc.journal:
        meta_parts.append(f"**Journal:** {doc.journal}")
    if doc.doi:
        meta_parts.append(f"**DOI:** {doc.doi}")
    if doc.pmid:
        meta_parts.append(f"**PMID:** {doc.pmid}")
    if doc.pmcid:
        meta_parts.append(f"**PMCID:** {doc.pmcid}")
    cite_parts = []
    if doc.volume:
        vol_str = doc.volume
        if doc.issue:
            vol_str += f"({doc.issue})"
        cite_parts.append(vol_str)
    if doc.pages:
        cite_parts.append(doc.pages)
    if cite_parts:
        meta_parts.append(f"**Citation:** {', '.join(cite_parts)}")
    if doc.pub_date:
        meta_parts.append(f"**Published:** {doc.pub_date}")
    if doc.license:
        meta_parts.append(f"**License:** {doc.license}")
    if not meta_parts:
        return
    for part in meta_parts:
        lines.append(part)
    lines.append("")


def _emit_authors(doc: Document, lines: list[str]) -> None:
    if not doc.authors:
        return

    # Comma-separated author names
    author_parts = []
    for author in doc.authors:
        name = f"{author.given_name} {author.surname}".strip()
        if name:
            author_parts.append(name)

    if author_parts:
        lines.append(", ".join(author_parts))
        lines.append("")

    # Affiliations (deduplicated, numbered)
    all_affils: list[str] = []
    seen: set[str] = set()
    for author in doc.authors:
        for aff in author.affiliations:
            if aff and aff not in seen:
                seen.add(aff)
                all_affils.append(aff)
    if all_affils:
        for i, aff in enumerate(all_affils, 1):
            lines.append(f"{i}. {aff}")
        lines.append("")


def _emit_abstract(doc: Document, lines: list[str]) -> None:
    if not doc.abstract:
        return
    lines.append("## Abstract")
    lines.append("")
    for para in doc.abstract:
        lines.append(para.text)
        lines.append("")


def _emit_keywords(doc: Document, lines: list[str]) -> None:
    if not doc.keywords:
        return
    lines.append(f"**Keywords:** {', '.join(doc.keywords)}")
    lines.append("")


def _emit_sections(
    sections: list[Section],
    lines: list[str],
    base_level: int,
    footnote_counter: list[int] | None = None,
) -> None:
    if footnote_counter is None:
        footnote_counter = [0]
    for section in sections:
        if section.is_boxed:
            lines.append("::: boxed-text")
            lines.append("")
            _emit_section(
                section,
                lines,
                base_level,
                footnote_counter,
            )
            lines.append(":::")
            lines.append("")
        else:
            _emit_section(
                section,
                lines,
                base_level,
                footnote_counter,
            )


def _emit_section(
    section: Section,
    lines: list[str],
    heading_level: int,
    footnote_counter: list[int] | None = None,
) -> None:
    if footnote_counter is None:
        footnote_counter = [0]
    capped_level = min(heading_level, MAX_HEADING_LEVEL)
    hashes = "#" * capped_level

    # Heading (section numbers omitted to match consensus pipeline format)
    if section.heading:
        lines.append(f"{hashes} {section.heading}")
        lines.append("")

    # Paragraphs (para.refs preserved in the Document model for downstream use)
    for para in section.paragraphs:
        lines.append(para.text)
        lines.append("")

    # Figures
    for fig in section.figures:
        _emit_figure(fig, lines)

    # Tables
    for table in section.tables:
        _emit_table(table, lines)

    # Formulas
    for formula in section.formulas:
        if formula.label:
            lines.append(f"{formula.label} {formula.text}")
        else:
            lines.append(formula.text)
        lines.append("")

    # Lists
    for lst in section.lists:
        _emit_list(lst, lines)

    # Footnotes
    for note in section.notes:
        footnote_counter[0] += 1
        lines.append(f"[^{footnote_counter[0]}]: {note}")
    if section.notes:
        lines.append("")

    # Subsections — when the parent section has no heading, emit
    # subsections at the same level so they don't become orphan
    # headings that the Markdown reader cannot reconstruct.
    sub_level = heading_level if not section.heading else heading_level + 1
    for sub in section.subsections:
        if sub.is_boxed:
            lines.append("::: boxed-text")
            lines.append("")
            _emit_section(sub, lines, sub_level, footnote_counter)
            lines.append(":::")
            lines.append("")
        else:
            _emit_section(sub, lines, sub_level, footnote_counter)


def _escape_cell(cell_text: str) -> str:
    """Escape characters that break GFM table cells."""
    return cell_text.replace("|", "\\|").replace("\n", " ")


def _emit_table(table: Table, lines: list[str]) -> None:
    # Filter out empty rows and determine column count from widest row
    non_empty_rows = [row for row in table.rows if row]

    if not non_empty_rows:
        # Image-only tables have no data rows but may have a caption.
        if table.label or table.caption:
            label = table.label.rstrip(".:").strip() if table.label else ""
            if label and table.caption:
                lines.append(f"**{label}.** {table.caption}")
            elif label:
                lines.append(f"**{label}.**")
            elif table.caption:
                lines.append(table.caption)
            lines.append("")
        if table.foot_notes:
            for fn in table.foot_notes:
                lines.append(fn)
            lines.append("")
        return
    col_count = max(len(row) for row in non_empty_rows)

    # Split rows into header and data based on is_header flag.
    # A row is treated as a header only if ALL its cells are headers.
    header_rows = []
    data_rows = []
    for row in non_empty_rows:
        if all(cell.is_header for cell in row):
            header_rows.append(row)
        else:
            data_rows.append(row)

    # If no explicit headers, treat first row as header
    if not header_rows and non_empty_rows:
        header_rows = [non_empty_rows[0]]
        data_rows = non_empty_rows[1:]

    # Emit header rows
    for row in header_rows:
        cells = [_escape_cell(cell.text) for cell in row]
        while len(cells) < col_count:
            cells.append("")
        lines.append("| " + " | ".join(cells) + " |")

    # Separator after headers — use alignment from last header row
    separators: list[str] = []
    last_header = header_rows[-1] if header_rows else []
    for col_idx in range(col_count):
        align = ""
        if col_idx < len(last_header):
            align = last_header[col_idx].align
        if align == "center":
            separators.append(":---:")
        elif align == "right":
            separators.append("---:")
        else:
            separators.append("---")
    lines.append("|" + "|".join(separators) + "|")

    # Data rows
    for row in data_rows:
        cells = [_escape_cell(cell.text) for cell in row]
        while len(cells) < col_count:
            cells.append("")
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    # Caption
    if table.label or table.caption:
        label = table.label.rstrip(".:").strip()
        if label and table.caption:
            lines.append(f"**{label}.** {table.caption}")
        elif label:
            lines.append(f"**{label}.**")
        elif table.caption:
            lines.append(table.caption)
        lines.append("")

    # Table footnotes
    if table.foot_notes:
        for fn in table.foot_notes:
            lines.append(fn)
        lines.append("")


def _emit_list(lst: ListBlock, lines: list[str]) -> None:
    if lst.title:
        lines.append(lst.title)
        lines.append("")
    for i, item in enumerate(lst.items, 1):
        if lst.ordered:
            lines.append(f"{i}. {item}")
        else:
            lines.append(f"- {item}")
    lines.append("")


def _emit_figure(fig: Figure, lines: list[str]) -> None:
    """Emit a single figure caption and optional alt-text."""
    if fig.doi:
        lines.append(f"<!-- doi: {fig.doi} -->")
        lines.append("")
    label = fig.label.rstrip(".:").strip()
    if label:
        if fig.caption:
            lines.append(f"**{label}.** {fig.caption}")
        else:
            lines.append(f"**{label}.**")
    elif fig.caption:
        lines.append(fig.caption)
    else:
        if not fig.alt_text and not fig.attrib and not fig.caption_paragraphs:
            return
    lines.append("")
    for cp in fig.caption_paragraphs:
        lines.append(cp)
        lines.append("")
    if fig.alt_text:
        lines.append(fig.alt_text)
        lines.append("")
    if fig.attrib:
        lines.append(fig.attrib)
        lines.append("")


def _emit_doc_level_figures(doc: Document, lines: list[str]) -> None:
    """Emit figures that are at document level (not inside sections)."""
    for fig in doc.figures:
        _emit_figure(fig, lines)


def _emit_doc_level_tables(doc: Document, lines: list[str]) -> None:
    """Emit tables that are at document level (not inside sections)."""
    for table in doc.tables:
        _emit_table(table, lines)


def _emit_acknowledgments(doc: Document, lines: list[str]) -> None:
    if not doc.acknowledgments:
        return
    lines.append("## Acknowledgments")
    lines.append("")
    lines.append(doc.acknowledgments)
    lines.append("")


def _emit_funding(doc: Document, lines: list[str]) -> None:
    if not doc.funding and not doc.funding_statement:
        return
    lines.append("## Funding")
    lines.append("")
    for entry in doc.funding:
        ids = ", ".join(entry.award_ids) if entry.award_ids else ""
        if entry.funder and ids:
            lines.append(f"{entry.funder}: {ids}")
        elif entry.funder:
            lines.append(entry.funder)
        elif ids:
            lines.append(ids)
    if doc.funding:
        lines.append("")
    if doc.funding_statement:
        lines.append(doc.funding_statement)
        lines.append("")


def _emit_author_notes(doc: Document, lines: list[str]) -> None:
    if not doc.author_notes:
        return
    lines.append("## Author Notes")
    lines.append("")
    for note in doc.author_notes:
        lines.append(note)
        lines.append("")


def _emit_competing_interests(doc: Document, lines: list[str]) -> None:
    if not doc.competing_interests:
        return
    lines.append("## Competing Interests")
    lines.append("")
    lines.append(doc.competing_interests)
    lines.append("")


def _emit_data_availability(doc: Document, lines: list[str]) -> None:
    if not doc.data_availability:
        return
    # Skip if the content is already in back_matter with original heading
    for section in doc.back_matter:
        if section.paragraphs and any(
            doc.data_availability[:40] in p.text for p in section.paragraphs
        ):
            return
    lines.append("## Data Availability")
    lines.append("")
    lines.append(doc.data_availability)
    lines.append("")


def _emit_back_matter(
    doc: Document,
    lines: list[str],
    footnote_counter: list[int] | None = None,
) -> None:
    if not doc.back_matter:
        return
    if footnote_counter is None:
        footnote_counter = [0]
    # Emit headed sections first, then headingless ones as footnotes
    # to prevent headingless paragraphs from being absorbed by
    # adjacent sections during markdown roundtrip.
    headed = [s for s in doc.back_matter if s.heading]
    headingless = [s for s in doc.back_matter if not s.heading]
    _emit_sections(headed, lines, base_level=2, footnote_counter=footnote_counter)
    for section in headingless:
        for para in section.paragraphs:
            footnote_counter[0] += 1
            lines.append(f"[^{footnote_counter[0]}]: {para.text}")
        for note in section.notes:
            footnote_counter[0] += 1
            lines.append(f"[^{footnote_counter[0]}]: {note}")
        for lst in section.lists:
            for item in lst.items:
                footnote_counter[0] += 1
                lines.append(f"[^{footnote_counter[0]}]: {item}")
        if section.paragraphs or section.notes or section.lists:
            lines.append("")
        # Tables and figures in headingless sections
        for table in section.tables:
            _emit_table(table, lines)
        for fig in section.figures:
            _emit_figure(fig, lines)
        # Emit headed subsections (e.g. appendix sections)
        headed_subs = [s for s in section.subsections if s.heading]
        if headed_subs:
            _emit_sections(headed_subs, lines, base_level=2, footnote_counter=footnote_counter)


def _format_ref_source(ref: Reference) -> list[str]:
    """Format journal, conference, publisher parts of a reference."""
    parts: list[str] = []
    if ref.journal:
        journal_part = f"*{ref.journal}*"
        if ref.volume:
            journal_part += f", {ref.volume}"
            if ref.issue:
                journal_part += f"({ref.issue})"
        if ref.pages:
            journal_part += f", {ref.pages}"
        journal_part += "."
        parts.append(journal_part)
    if ref.conference:
        parts.append(f"*{ref.conference}*.")
    if ref.publisher:
        pub_str = ref.publisher
        if ref.publisher_loc:
            pub_str = f"{ref.publisher_loc}: {pub_str}"
        parts.append(f"{pub_str}.")
    return parts


def _format_ref_line(ref: Reference) -> str:
    """Format a single reference as a numbered line."""
    parts: list[str] = []
    if ref.authors:
        parts.append(", ".join(ref.authors))
    if ref.year:
        parts.append(f"({ref.year})")
    if ref.title:
        parts.append(f"{ref.title}.")
    if ref.chapter_title:
        parts.append(f"In: {ref.chapter_title}.")
    if ref.editors:
        parts.append(f"Edited by {', '.join(ref.editors)}.")
    parts.extend(_format_ref_source(ref))
    if ref.doi:
        parts.append(f"doi:{ref.doi}")
    if ref.pmid:
        parts.append(f"PMID:{ref.pmid}")
    if ref.pmcid:
        parts.append(f"PMCID:{ref.pmcid}")
    for link in ref.ext_links:
        parts.append(link)
    if ref.comment and not parts:
        # Note-only reference (e.g., reference annotations).
        parts.append(ref.comment)
    elif ref.comment:
        parts.append(ref.comment)
    return f"{ref.index}. " + " ".join(parts)


def _emit_references(doc: Document, lines: list[str]) -> None:
    if not doc.references:
        return
    lines.append("## References")
    lines.append("")
    for ref in doc.references:
        lines.append(_format_ref_line(ref))
    lines.append("")


def _emit_categories(doc: Document, lines: list[str]) -> None:
    if not doc.categories:
        return
    lines.append(f"**Categories:** {', '.join(doc.categories)}")
    lines.append("")


def _emit_secondary_abstracts(doc: Document, lines: list[str]) -> None:
    if not doc.secondary_abstracts:
        return
    for sa in doc.secondary_abstracts:
        lines.append(f"## {sa.label}")
        lines.append("")
        for para in sa.paragraphs:
            lines.append(para.text)
            lines.append("")


def _emit_author_roles(doc: Document, lines: list[str]) -> None:
    """Emit CRediT author roles as footnotes after references."""
    entries: list[str] = []
    for author in doc.authors:
        if author.roles:
            name = f"{author.given_name} {author.surname}".strip()
            entries.append(f"{name}: {', '.join(author.roles)}")
    if not entries:
        return
    for i, entry in enumerate(entries, 1):
        lines.append(f"[^{i}]: {entry}")
    lines.append("")


def _emit_sub_articles(doc: Document, lines: list[str]) -> None:
    """Emit sub-articles (decision letters, author responses, etc.)."""
    if not doc.sub_articles:
        return
    for sub in doc.sub_articles:
        _emit_sub_article(sub, lines)


def _emit_sub_article(sub: Document, lines: list[str]) -> None:
    """Emit a single sub-article with ``---`` separator and H2 title."""
    lines.append("---")
    lines.append("")
    if sub.doi:
        lines.append(f"DOI: {sub.doi}")
        lines.append("")
    if sub.title:
        lines.append(f"## {sub.title}")
        lines.append("")
    if sub.authors:
        has_roles = any(a.roles for a in sub.authors)
        has_affiliations = any(a.affiliations for a in sub.authors)
        if has_roles:
            # Editor/reviewer style: one contributor per line with
            # role and inline affiliation details.
            for author in sub.authors:
                parts = [f"{author.surname} {author.given_name}".strip()]
                if not parts[0]:
                    continue
                for role in author.roles:
                    parts.append(role)
                for aff in author.affiliations:
                    parts.append(aff)
                lines.append(" ".join(parts))
            lines.append("")
        elif has_affiliations:
            # Meeting-abstract style: one author per line with
            # affiliation superscripts, followed by affiliation lines.
            aff_list: list[str] = []
            aff_index: dict[str, int] = {}
            for author in sub.authors:
                for aff in author.affiliations:
                    if aff not in aff_index:
                        aff_index[aff] = len(aff_list) + 1
                        aff_list.append(aff)
            for author in sub.authors:
                name = f"{author.surname} {author.given_name}".strip()
                if not name:
                    continue
                nums = " ".join(str(aff_index[a]) for a in author.affiliations if a in aff_index)
                if nums:
                    name = f"{name} {nums}"
                lines.append(name)
            for idx, aff_text in enumerate(aff_list, 1):
                lines.append(f"{idx} {aff_text}")
            lines.append("")
        else:
            # Simple style: comma-separated names on one line.
            author_parts = []
            for author in sub.authors:
                name = f"{author.given_name} {author.surname}".strip()
                if name:
                    author_parts.append(name)
            if author_parts:
                lines.append(", ".join(author_parts))
            lines.append("")
    if sub.author_notes:
        for note in sub.author_notes:
            lines.append(note)
        lines.append("")
    if sub.abstract:
        for para in sub.abstract:
            lines.append(para.text)
            lines.append("")
    footnote_counter = [0]
    _emit_sections(sub.sections, lines, base_level=3, footnote_counter=footnote_counter)
    # Sub-article back-matter (fn-groups, notes, etc.)
    if sub.competing_interests:
        lines.append("### Competing Interests")
        lines.append("")
        lines.append(sub.competing_interests)
        lines.append("")
    if sub.back_matter:
        _emit_sections(
            [s for s in sub.back_matter if s.heading],
            lines,
            base_level=3,
            footnote_counter=footnote_counter,
        )
        for section in sub.back_matter:
            if not section.heading:
                for para in section.paragraphs:
                    footnote_counter[0] += 1
                    lines.append(f"[^{footnote_counter[0]}]: {para.text}")
                for note in section.notes:
                    footnote_counter[0] += 1
                    lines.append(f"[^{footnote_counter[0]}]: {note}")
                if section.paragraphs or section.notes:
                    lines.append("")
    if sub.references:
        lines.append("### References")
        lines.append("")
        for ref in sub.references:
            lines.append(_format_ref_line(ref))
        lines.append("")
