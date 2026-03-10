"""AGR ABC Document Parsers — shared library for the ABC Markdown format.

Provides parsers, emitters, readers, and validators for the ABC Markdown
format used across all AGR services for scientific publications.
"""

__version__ = "0.1.0"

from agr_abc_document_parsers.converter import (  # noqa: F401
    convert_xml_to_markdown,
    detect_format,
)
from agr_abc_document_parsers.jats_parser import parse_jats  # noqa: F401
from agr_abc_document_parsers.md_emitter import emit_markdown  # noqa: F401
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
    InlineRef,
    ListBlock,
    Paragraph,
    Reference,
    Section,
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
