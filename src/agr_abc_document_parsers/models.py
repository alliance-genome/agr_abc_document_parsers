"""Intermediate document model for XML-to-Markdown conversion."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Union

# Type alias: accepted input for loading methods.
#   str  -> Markdown text
#   bytes -> XML (TEI or JATS), optionally gzip-compressed
DocumentInput = Union[str, bytes]

# Accepted values for the ``format`` parameter.
Format = Literal["auto", "tei", "jats", "markdown"]


@dataclass
class Author:
    given_name: str = ""
    surname: str = ""
    email: str = ""
    orcid: str = ""
    affiliations: list[str] = field(default_factory=list)


@dataclass
class InlineRef:
    """An inline citation reference like [1] or (Author, 2024)."""
    text: str = ""
    target: str = ""  # e.g., "#b12" pointing to a biblStruct


@dataclass
class Paragraph:
    text: str = ""
    refs: list[InlineRef] = field(default_factory=list)


@dataclass
class Figure:
    label: str = ""       # "Figure 1" or "Fig. 1"
    caption: str = ""     # figDesc text
    graphic_url: str = ""  # image ref (preserved for downstream; not in Markdown)


@dataclass
class TableCell:
    text: str = ""
    is_header: bool = False


@dataclass
class Table:
    label: str = ""              # "Table 1"
    caption: str = ""
    foot_notes: list[str] = field(default_factory=list)
    rows: list[list[TableCell]] = field(default_factory=list)


@dataclass
class Formula:
    text: str = ""
    label: str = ""


@dataclass
class ListBlock:
    items: list[str] = field(default_factory=list)
    ordered: bool = False


@dataclass
class Section:
    heading: str = ""
    number: str = ""                  # "1", "1.1", etc. from <head n="...">
    level: int = 1                    # nesting depth -> Markdown heading level
    paragraphs: list[Paragraph] = field(default_factory=list)
    figures: list[Figure] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    formulas: list[Formula] = field(default_factory=list)
    lists: list[ListBlock] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    subsections: list[Section] = field(default_factory=list)


@dataclass
class Reference:
    """A single entry in the bibliography."""
    index: int = 0
    authors: list[str] = field(default_factory=list)  # "Surname FN" format
    editors: list[str] = field(default_factory=list)
    title: str = ""
    chapter_title: str = ""  # part-title for book chapters
    journal: str = ""
    publisher: str = ""
    publisher_loc: str = ""
    conference: str = ""  # conf-name / meeting
    volume: str = ""
    issue: str = ""
    pages: str = ""
    year: str = ""
    doi: str = ""
    pmid: str = ""
    pmcid: str = ""
    ext_links: list[str] = field(default_factory=list)  # URLs from ext-link/ptr


@dataclass
class Document:
    title: str = ""
    authors: list[Author] = field(default_factory=list)
    abstract: list[Paragraph] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    doi: str = ""
    pmid: str = ""
    pmcid: str = ""
    journal: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    pub_date: str = ""  # ISO-ish: "2014-02-06" or "2014-02" or "2014"
    license: str = ""
    sections: list[Section] = field(default_factory=list)
    figures: list[Figure] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    references: list[Reference] = field(default_factory=list)
    acknowledgments: str = ""
    back_matter: list[Section] = field(default_factory=list)
    source_format: str = ""  # "tei" or "jats"
    supplements: list[Document] = field(default_factory=list)

    # -- Loading methods ---------------------------------------------------

    def load_main(
        self,
        data: DocumentInput,
        format: Format = "auto",
    ) -> Document:
        """Parse *data* and overwrite all main-document fields.

        Existing supplements are preserved unless the parsed data itself
        contains supplements.

        Args:
            data: The document to load.

                * ``str`` — treated as ABC-format Markdown text.
                * ``bytes`` — treated as XML (TEI or JATS).  Gzip-compressed
                  bytes are decompressed automatically.

            format: Parser selection.

                * ``"auto"`` (default) — ``str`` → Markdown parser;
                  ``bytes`` → detect TEI vs JATS from the XML root element.
                * ``"tei"`` — GROBID TEI XML parser (requires ``bytes``).
                * ``"jats"`` — PMC nXML / JATS parser (requires ``bytes``).
                * ``"markdown"`` — ABC Markdown parser (requires ``str``).

        Returns:
            ``self``, for method chaining.

        Example::

            doc = Document()
            doc.load_main(open("paper.nxml.gz", "rb").read())
            doc.load_main(open("paper.md").read(), format="markdown")
        """
        parsed = _parse_content(data, format)
        old_supplements = self.supplements
        for fld in self.__dataclass_fields__:
            setattr(self, fld, getattr(parsed, fld))
        if not parsed.supplements and old_supplements:
            self.supplements = old_supplements
        return self

    def add_supplement(
        self,
        data: DocumentInput,
        format: Format = "auto",
    ) -> Document:
        """Parse *data* as a supplement and append to :attr:`supplements`.

        Args:
            data: Supplement content.

                * ``str`` — ABC-format Markdown text.
                * ``bytes`` — XML (TEI or JATS), optionally gzip-compressed.

            format: Parser selection (same options as :meth:`load_main`).

        Returns:
            ``self``, for method chaining.

        Example::

            doc.add_supplement(open("supp1.nxml.gz", "rb").read())
            doc.add_supplement(open("supp2.md").read())
        """
        self.supplements.append(_parse_content(data, format))
        return self

    def add_supplements(
        self,
        items: list[DocumentInput],
        format: Format = "auto",
    ) -> Document:
        """Parse multiple supplements and append to :attr:`supplements`.

        Args:
            items: List of supplement contents.  Each element is either
                a ``str`` (Markdown) or ``bytes`` (XML, optionally gzipped).
            format: Parser selection, applied to every item.
                ``"auto"`` detects format per item.

        Returns:
            ``self``, for method chaining.

        Example::

            doc.add_supplements([
                open("supp1.nxml.gz", "rb").read(),
                open("supp2.md").read(),
            ])
        """
        for item in items:
            self.add_supplement(item, format=format)
        return self

    # -- File-based loading methods ----------------------------------------

    def load_main_file(
        self,
        path: str | Path,
        format: Format = "auto",
    ) -> Document:
        """Read a file from disk and load it as the main document.

        The format is determined from the file extension when
        ``format="auto"``:

        * ``.tei``, ``.tei.gz`` → TEI parser
        * ``.nxml``, ``.nxml.gz``, ``.xml``, ``.xml.gz`` → JATS parser
        * ``.md`` → Markdown parser
        * ``.gz`` (other) → auto-detect from XML root element

        Args:
            path: Path to the file (str or ``pathlib.Path``).
            format: Parser override.  ``"auto"`` detects from extension.

        Returns:
            ``self``, for method chaining.

        Example::

            doc = Document()
            doc.load_main_file("paper.nxml.gz")
            doc.load_main_file("/data/papers/12345.md")
        """
        data, resolved_format = _read_file(path, format)
        return self.load_main(data, format=resolved_format)

    def add_supplement_file(
        self,
        path: str | Path,
        format: Format = "auto",
    ) -> Document:
        """Read a file from disk and append it as a supplement.

        See :meth:`load_main_file` for format detection rules.

        Args:
            path: Path to the supplement file.
            format: Parser override.

        Returns:
            ``self``, for method chaining.
        """
        data, resolved_format = _read_file(path, format)
        return self.add_supplement(data, format=resolved_format)

    def add_supplement_files(
        self,
        paths: list[str | Path],
        format: Format = "auto",
    ) -> Document:
        """Read multiple files from disk and append each as a supplement.

        Args:
            paths: List of file paths.
            format: Parser override, applied to every file.

        Returns:
            ``self``, for method chaining.

        Example::

            doc.add_supplement_files([
                "supp1.nxml.gz",
                "supp2.tei.gz",
                "supp3.md",
            ])
        """
        for p in paths:
            self.add_supplement_file(p, format=format)
        return self


# -- File extension to format mapping -------------------------------------

_EXT_FORMAT_MAP: dict[str, Format] = {
    ".tei": "tei",
    ".nxml": "jats",
    ".xml": "jats",
    ".md": "markdown",
}


def _resolve_format_from_path(path: Path) -> Format:
    """Guess the parser format from a file's extension."""
    suffixes = path.suffixes  # e.g. ['.tei', '.gz'] or ['.nxml'] or ['.md']
    # Strip trailing .gz
    exts = [s for s in suffixes if s != ".gz"]
    if exts:
        fmt = _EXT_FORMAT_MAP.get(exts[-1])
        if fmt is not None:
            return fmt
    return "auto"


def _read_file(
    path: str | Path, format: Format,
) -> tuple[DocumentInput, Format]:
    """Read a file and resolve its format.

    Returns (data, format) where data is ``str`` for Markdown files and
    ``bytes`` for XML files.
    """
    path = Path(path)
    if format == "auto":
        format = _resolve_format_from_path(path)
    if format == "markdown":
        return path.read_text(encoding="utf-8"), format
    return path.read_bytes(), format


def _parse_content(data: DocumentInput, format: Format) -> Document:
    """Dispatch *data* to the correct parser.

    Imports are deferred to avoid circular dependencies (models is imported
    by every parser module).
    """
    if isinstance(data, str):
        if format in ("auto", "markdown"):
            from agr_abc_document_parsers.md_reader import read_markdown
            return read_markdown(data)
        raise ValueError(
            f"str input requires format='markdown' or 'auto', got '{format}'"
        )

    # bytes — may be gzipped XML
    if format == "markdown":
        raise ValueError("format='markdown' requires str input, got bytes")

    if format == "auto":
        from agr_abc_document_parsers.converter import detect_format
        detected = detect_format(data)
    else:
        detected = format

    if detected == "tei":
        from agr_abc_document_parsers.tei_parser import parse_tei
        return parse_tei(data)
    if detected == "jats":
        from agr_abc_document_parsers.jats_parser import parse_jats
        return parse_jats(data)

    raise ValueError(f"Unknown format: '{detected}'")
