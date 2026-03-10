"""Extract plain text from Document models for downstream ML pipelines."""
from __future__ import annotations

import re

from agr_abc_document_parsers.models import Document, Section

# ---------------------------------------------------------------------------
# Inline Markdown stripping
# ---------------------------------------------------------------------------

# Order matters: bold (**) before italic (*) to avoid partial matches.
_STRIP_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\*\*(.+?)\*\*"), r"\1"),          # **bold**
    (re.compile(r"\*(.+?)\*"), r"\1"),               # *italic*
    (re.compile(r"<sup>(.+?)</sup>", re.I), r"\1"),  # <sup>x</sup>
    (re.compile(r"<sub>(.+?)</sub>", re.I), r"\1"),  # <sub>x</sub>
    (re.compile(r"\[([^\]]+)\]\([^)]+\)"), r"\1"),   # [text](url)
]

# Sentence splitting: split on .!? followed by whitespace + uppercase letter,
# but not after common abbreviations.
_ABBREVIATIONS = {
    "Dr", "Mr", "Mrs", "Ms", "Prof", "Jr", "Sr",
    "Fig", "Figs", "Fig.", "Figs.",
    "No", "Nos", "Vol", "Vols",
    "al", "etc", "approx", "ca",
    "vs", "cf", "viz", "i.e", "e.g",
    "Eq", "Eqs", "Ref", "Refs",
    "Dept", "Univ", "Inc", "Corp", "Ltd",
    "St", "Ave", "Blvd",
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
    doc: Document, include_supplements: bool = True,
) -> str:
    """Extract plain text from a Document, stripping Markdown formatting.

    Returns title + abstract + body sections + acknowledgments +
    supplement text (excluding References). Supplements are included
    by default.

    Args:
        doc: A populated Document model.
        include_supplements: Whether to include supplement text.

    Returns:
        Plain text with double-newline paragraph separation.
    """
    parts: list[str] = []

    if doc.title:
        parts.append(strip_markdown_formatting(doc.title))

    for para in doc.abstract:
        parts.append(strip_markdown_formatting(para.text))

    _collect_sections_text(doc.sections, parts)

    for fig in doc.figures:
        if fig.caption:
            parts.append(strip_markdown_formatting(fig.caption))

    if doc.acknowledgments:
        parts.append(strip_markdown_formatting(doc.acknowledgments))

    _collect_sections_text(doc.back_matter, parts)

    if include_supplements:
        for supp in doc.supplements:
            supp_text = extract_plain_text(supp, include_supplements=False)
            if supp_text:
                parts.append(supp_text)

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
    doc: Document, include_supplements: bool = True,
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


def _collect_sections_text(sections: list[Section], parts: list[str]) -> None:
    """Recursively collect plain text from sections."""
    for section in sections:
        if section.heading:
            parts.append(strip_markdown_formatting(section.heading))

        for para in section.paragraphs:
            parts.append(strip_markdown_formatting(para.text))

        for fig in section.figures:
            if fig.caption:
                parts.append(strip_markdown_formatting(fig.caption))

        for table in section.tables:
            if table.caption:
                parts.append(strip_markdown_formatting(table.caption))

        for formula in section.formulas:
            if formula.text:
                parts.append(strip_markdown_formatting(formula.text))

        for lst in section.lists:
            for item in lst.items:
                parts.append(strip_markdown_formatting(item))

        for note in section.notes:
            parts.append(strip_markdown_formatting(note))

        _collect_sections_text(section.subsections, parts)


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
