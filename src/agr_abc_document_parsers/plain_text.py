"""Extract plain text from Document models for downstream ML pipelines."""

from __future__ import annotations

import re

from agr_abc_document_parsers.models import (
    Document,
    Figure,
    Reference,
    Section,
    Table,
)

# ---------------------------------------------------------------------------
# Inline Markdown stripping
# ---------------------------------------------------------------------------

# Order matters: bold (**) before italic (*) to avoid partial matches.
_STRIP_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\*\*(.+?)\*\*"), r"\1"),  # **bold**
    (re.compile(r"\*(.+?)\*"), r"\1"),  # *italic*
    (re.compile(r"~~(.+?)~~"), r"\1"),  # ~~strikethrough~~
    (re.compile(r"<u>(.+?)</u>", re.I), r"\1"),  # <u>underline</u>
    (re.compile(r"<sup>(.+?)</sup>", re.I), r"\1"),  # <sup>x</sup>
    (re.compile(r"<sub>(.+?)</sub>", re.I), r"\1"),  # <sub>x</sub>
    (re.compile(r"`(.+?)`"), r"\1"),  # `monospace`
    (re.compile(r"\[([^\]]+)\]\([^)]+\)"), r"\1"),  # [text](url)
    (re.compile(r"\\([*])"), r"\1"),  # \* → * (unescape)
]

# Sentence splitting: split on .!? followed by whitespace + uppercase letter,
# but not after common abbreviations.
_ABBREVIATIONS = {
    "Dr",
    "Mr",
    "Mrs",
    "Ms",
    "Prof",
    "Jr",
    "Sr",
    "Fig",
    "Figs",
    "Fig.",
    "Figs.",
    "No",
    "Nos",
    "Vol",
    "Vols",
    "al",
    "etc",
    "approx",
    "ca",
    "vs",
    "cf",
    "viz",
    "i.e",
    "e.g",
    "Eq",
    "Eqs",
    "Ref",
    "Refs",
    "Dept",
    "Univ",
    "Inc",
    "Corp",
    "Ltd",
    "St",
    "Ave",
    "Blvd",
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def strip_markdown_formatting(text: str) -> str:
    """Strip inline Markdown formatting from a string.

    Converts:
    - ``**bold**`` → ``bold``
    - ``*italic*`` → ``italic``
    - ``<sup>x</sup>`` → ``x``
    - ``<sub>x</sub>`` → ``x``
    - ``[text](url)`` → ``text``
    """
    for pattern, replacement in _STRIP_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def extract_plain_text(
    doc: Document,
    include_authors: bool = False,
    include_correspondence: bool = False,
    include_metadata: bool = False,
    include_abstract: bool = True,
    include_keywords: bool = False,
    include_body: bool = True,
    include_acknowledgments: bool = True,
    include_funding: bool = True,
    include_author_notes: bool = True,
    include_competing_interests: bool = True,
    include_data_availability: bool = True,
    include_back_matter: bool = True,
    include_references: bool = False,
    include_supplements: bool = True,
    include_sub_articles: bool = False,
) -> str:
    """Extract plain text from a Document, stripping Markdown formatting.

    Each content section can be independently included or excluded.
    Defaults preserve backward-compatible behaviour: title + abstract +
    secondary abstracts + body + acknowledgments + funding + author
    notes + competing interests + data availability + back matter +
    supplements.

    Args:
        doc: A populated Document model.
        include_authors: Whether to include author names.
        include_correspondence: Whether to include corresponding
            author emails (e.g. ``Correspondence: Name (email)``).
        include_metadata: Whether to include article metadata
            (journal, DOI, PMID, etc.).
        include_abstract: Whether to include abstract and secondary
            abstracts.
        include_keywords: Whether to include keyword list.
        include_body: Whether to include body sections (paragraphs,
            figures, tables, formulas, lists).
        include_acknowledgments: Whether to include acknowledgments.
        include_funding: Whether to include funding information.
        include_author_notes: Whether to include author notes
            (correspondence notes from ``<author-notes>``).
        include_competing_interests: Whether to include competing
            interest statements.
        include_data_availability: Whether to include data
            availability statements.
        include_back_matter: Whether to include back-matter sections.
        include_references: Whether to include the reference list.
        include_supplements: Whether to include supplement text.
        include_sub_articles: Whether to include sub-article text
            (e.g., decision letters, author responses).

    Returns:
        Plain text with double-newline paragraph separation.
    """
    parts: list[str] = []

    if doc.title:
        parts.append(strip_markdown_formatting(doc.title))

    if include_metadata:
        meta_parts: list[str] = []
        if doc.journal:
            meta_parts.append(f"Journal: {doc.journal}")
        if doc.doi:
            meta_parts.append(f"DOI: {doc.doi}")
        if doc.pmid:
            meta_parts.append(f"PMID: {doc.pmid}")
        if doc.pmcid:
            meta_parts.append(f"PMCID: {doc.pmcid}")
        if doc.pub_date:
            meta_parts.append(f"Published: {doc.pub_date}")
        if meta_parts:
            parts.append("; ".join(meta_parts))

    if include_authors and doc.authors:
        names = []
        for author in doc.authors:
            name = f"{author.given_name} {author.surname}".strip()
            if name:
                names.append(name)
        if names:
            parts.append(", ".join(names))

    if include_correspondence:
        email_parts = []
        for author in doc.authors:
            if author.email:
                name = f"{author.given_name} {author.surname}".strip()
                email_parts.append(f"{name} ({author.email})")
        if email_parts:
            parts.append("Correspondence: " + ", ".join(email_parts))

    if include_abstract:
        for para in doc.abstract:
            parts.append(strip_markdown_formatting(para.text))

        for sa in doc.secondary_abstracts:
            if sa.label:
                parts.append(strip_markdown_formatting(sa.label))
            for para in sa.paragraphs:
                parts.append(strip_markdown_formatting(para.text))

    if include_keywords and doc.keywords:
        parts.append("Keywords: " + ", ".join(doc.keywords))

    if include_body:
        _collect_sections_text(doc.sections, parts)

        for fig in doc.figures:
            _collect_figure_text(fig, parts)

        for table in doc.tables:
            _collect_table_text(table, parts)

    if include_acknowledgments and doc.acknowledgments:
        parts.append("Acknowledgments")
        parts.append(strip_markdown_formatting(doc.acknowledgments))

    if include_funding and (doc.funding_statement or doc.funding):
        parts.append("Funding")
        if doc.funding:
            for entry in doc.funding:
                ids = ", ".join(entry.award_ids) if entry.award_ids else ""
                if ids:
                    parts.append(f"{entry.funder}: {ids}")
                else:
                    parts.append(entry.funder)
        if doc.funding_statement:
            parts.append(strip_markdown_formatting(doc.funding_statement))

    if include_author_notes and doc.author_notes:
        parts.append("Author Notes")
        for note in doc.author_notes:
            parts.append(strip_markdown_formatting(note))

    if include_competing_interests and doc.competing_interests:
        parts.append("Competing Interests")
        parts.append(strip_markdown_formatting(doc.competing_interests))

    if include_data_availability and doc.data_availability:
        parts.append("Data Availability Statement")
        parts.append(strip_markdown_formatting(doc.data_availability))

    if include_back_matter:
        _collect_sections_text(doc.back_matter, parts)

    # Reference annotation notes (note-only refs without citation data).
    for ref in doc.references:
        if not ref.authors and not ref.journal and not ref.year:
            note_text = ref.comment or ref.title
            if note_text:
                parts.append(strip_markdown_formatting(note_text))

    if include_references:
        _collect_references_text(doc.references, parts)

    if include_supplements:
        for supp in doc.supplements:
            supp_text = extract_plain_text(supp, include_supplements=False)
            if supp_text:
                parts.append(supp_text)

    if include_sub_articles:
        for sub in doc.sub_articles:
            if sub.doi:
                parts.append("DOI: " + sub.doi)
            if sub.title:
                parts.append(strip_markdown_formatting(sub.title))
            # Author/editor lines for sub-articles
            for author in sub.authors:
                line = f"{author.given_name} {author.surname}".strip()
                if not line:
                    continue
                parts.append(line)
            # Abstract, body, and remaining content
            # (skip title since we already emitted it above)
            sub_parts: list[str] = []
            for para in sub.abstract:
                t = strip_markdown_formatting(para.text)
                if t:
                    sub_parts.append(t)
            _collect_sections_text(sub.sections, sub_parts)
            for fig in sub.figures:
                _collect_figure_text(fig, sub_parts)
            for table in sub.tables:
                _collect_table_text(table, sub_parts)
            if sub.competing_interests:
                sub_parts.append(strip_markdown_formatting(sub.competing_interests))
            _collect_sections_text(sub.back_matter, sub_parts)
            for p in sub_parts:
                if p:
                    parts.append(p)

    return "\n\n".join(p for p in parts if p)


def extract_abstract_text(doc: Document) -> str:
    """Extract plain-text abstract with formatting stripped.

    Args:
        doc: A populated Document model.

    Returns:
        Plain abstract text, or empty string if no abstract.
    """
    parts: list[str] = []
    for para in doc.abstract:
        parts.append(strip_markdown_formatting(para.text))
    return "\n\n".join(p for p in parts if p)


def extract_sentences(
    doc: Document,
    include_supplements: bool = True,
) -> list[str]:
    """Split document text into sentences.

    Handles common abbreviations (Dr., Fig., et al., e.g., i.e., etc.)
    to avoid false sentence breaks.

    Args:
        doc: A populated Document model.
        include_supplements: Whether to include supplement text.

    Returns:
        List of sentence strings.
    """
    text = extract_plain_text(doc, include_supplements=include_supplements)
    if not text:
        return []
    return _split_sentences(text)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _collect_figure_text(fig: Figure, parts: list[str]) -> None:
    """Collect plain text from a figure, including label, caption, and alt-text."""
    text_parts: list[str] = []
    if fig.doi:
        text_parts.append(fig.doi)
    if fig.label:
        text_parts.append(fig.label.rstrip(".:").strip())
    if fig.caption:
        text_parts.append(strip_markdown_formatting(fig.caption))
    if text_parts:
        parts.append(" ".join(text_parts))
    for cp in fig.caption_paragraphs:
        parts.append(strip_markdown_formatting(cp))
    if fig.alt_text:
        parts.append(strip_markdown_formatting(fig.alt_text))
    if fig.attrib:
        parts.append(strip_markdown_formatting(fig.attrib))


def _collect_table_text(table: Table, parts: list[str]) -> None:
    """Collect plain text from a table, including label, caption, and cell text."""
    if table.label or table.caption:
        text_parts: list[str] = []
        label = table.label.rstrip(".:").strip() if table.label else ""
        if label:
            text_parts.append(label)
        if table.caption:
            text_parts.append(strip_markdown_formatting(table.caption))
        parts.append(" ".join(text_parts))
    for row in table.rows:
        for cell in row:
            cell_text = cell.text.strip()
            if cell_text:
                parts.append(strip_markdown_formatting(cell_text))
    if table.foot_notes:
        for fn in table.foot_notes:
            parts.append(strip_markdown_formatting(fn))


def _collect_sections_text(sections: list[Section], parts: list[str]) -> None:
    """Recursively collect plain text from sections."""
    for section in sections:
        if section.heading:
            parts.append(strip_markdown_formatting(section.heading))

        for para in section.paragraphs:
            parts.append(strip_markdown_formatting(para.text))

        for table in section.tables:
            _collect_table_text(table, parts)

        for formula in section.formulas:
            if formula.text:
                parts.append(strip_markdown_formatting(formula.text))

        for lst in section.lists:
            if lst.title:
                parts.append(strip_markdown_formatting(lst.title))
            for idx, item in enumerate(lst.items, 1):
                text = strip_markdown_formatting(item)
                if lst.ordered:
                    text = f"{idx}. {text}"
                parts.append(text)

        for note in section.notes:
            parts.append(strip_markdown_formatting(note))

        _collect_sections_text(section.subsections, parts)


def _collect_references_text(
    references: list[Reference],
    parts: list[str],
) -> None:
    """Collect plain text from the reference list."""
    if not references:
        return
    parts.append("References")
    for ref in references:
        ref_parts: list[str] = []
        if ref.authors:
            ref_parts.append(", ".join(ref.authors))
        if ref.year:
            ref_parts.append(f"({ref.year})")
        if ref.title:
            ref_parts.append(f"{ref.title}.")
        if ref.chapter_title:
            ref_parts.append(f"In: {ref.chapter_title}.")
        if ref.editors:
            ref_parts.append(f"Edited by {', '.join(ref.editors)}.")
        if ref.journal:
            journal_part = ref.journal
            if ref.volume:
                journal_part += f", {ref.volume}"
                if ref.issue:
                    journal_part += f"({ref.issue})"
            if ref.pages:
                journal_part += f", {ref.pages}"
            journal_part += "."
            ref_parts.append(journal_part)
        if ref.publisher:
            pub_str = ref.publisher
            if ref.publisher_loc:
                pub_str = f"{ref.publisher_loc}: {pub_str}"
            ref_parts.append(f"{pub_str}.")
        if ref.doi:
            ref_parts.append(f"doi:{ref.doi}")
        if ref.pmid:
            ref_parts.append(f"PMID:{ref.pmid}")
        if ref.comment and not ref_parts:
            ref_parts.append(ref.comment)
        elif ref.comment:
            ref_parts.append(ref.comment)
        if ref_parts:
            parts.append(f"{ref.index}. " + " ".join(ref_parts))


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences, respecting abbreviations."""
    # Normalize whitespace: collapse newlines into spaces for sentence splitting
    text = re.sub(r"\n+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return []

    sentences: list[str] = []
    current_pos = 0

    # Split on sentence-ending punctuation followed by space + uppercase,
    # but skip common abbreviations.
    for m in re.finditer(r"([.!?])\s+(?=[A-Z])", text):
        end_pos = m.start() + 1  # include the punctuation

        # Check if the word before the punctuation is an abbreviation
        preceding = text[current_pos:end_pos]
        word_before = _last_word(preceding.rstrip(".!?"))

        if word_before.rstrip(".") in _ABBREVIATIONS:
            continue

        sentence = text[current_pos:end_pos].strip()
        if sentence:
            sentences.append(sentence)
        current_pos = m.end()

    # Add the remaining text as the last sentence
    last = text[current_pos:].strip()
    if last:
        sentences.append(last)

    return sentences


def _last_word(text: str) -> str:
    """Extract the last word from text, stripping surrounding punctuation."""
    parts = text.rsplit(None, 1)
    if not parts:
        return ""
    # Strip parentheses, brackets, quotes that may surround abbreviations
    return parts[-1].strip("()[]\"'")
