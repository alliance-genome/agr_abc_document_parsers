"""AGR ABC Document Parsers — shared library for the ABC Markdown format.

Provides parsers, emitters, readers, and validators for the ABC Markdown
format used across all AGR services for scientific publications.
"""

from agr_abc_document_parsers.converter import (  # noqa: F401
    convert_office_to_markdown,
    convert_tei_to_markdown_with_provenance,
    convert_xml_to_markdown,
    detect_format,
    detect_office_format,
    parse_office,
)
from agr_abc_document_parsers.docx_parser import parse_docx  # noqa: F401
from agr_abc_document_parsers.jats_parser import parse_jats  # noqa: F401
from agr_abc_document_parsers.md_emitter import (  # noqa: F401
    emit_markdown,
    emit_markdown_with_provenance,
)
from agr_abc_document_parsers.md_reader import (  # noqa: F401
    load_document_with_supplements,
    read_markdown,
)
from agr_abc_document_parsers.md_validator import (  # noqa: F401
    Severity,
    ValidationIssue,
    ValidationResult,
    validate_markdown,
)
from agr_abc_document_parsers.models import (  # noqa: F401
    Author,
    Document,
    Figure,
    Formula,
    FundingEntry,
    InlineRef,
    ListBlock,
    MarkdownEmission,
    MarkdownSourceSpan,
    Paragraph,
    Reference,
    SecondaryAbstract,
    Section,
    SourceProvenance,
    Table,
    TableCell,
)
from agr_abc_document_parsers.plain_text import (  # noqa: F401
    extract_abstract_text,
    extract_plain_text,
    extract_sentences,
    strip_markdown_formatting,
)
from agr_abc_document_parsers.tei_parser import parse_tei  # noqa: F401
from agr_abc_document_parsers.xlsx_parser import parse_xlsx  # noqa: F401
