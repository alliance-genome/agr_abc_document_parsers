# agr-abc-document-parsers

Shared Python library for the Alliance of Genome Resources (AGR) document processing pipeline. Provides parsers, emitters, and validators for the ABC Markdown format — the canonical text representation used across all AGR services for scientific publications.

## Installation

```bash
pip install agr-abc-document-parsers
```

For development:

```bash
pip install -e ".[dev]"
```

## Usage

### Convert XML to Markdown

```python
from agr_abc_document_parsers import convert_xml_to_markdown

# Auto-detect TEI or JATS format
markdown = convert_xml_to_markdown(xml_bytes)

# Explicit format
markdown = convert_xml_to_markdown(xml_bytes, source_format="tei")
markdown = convert_xml_to_markdown(xml_bytes, source_format="jats")
```

### Parse to Document model

```python
from agr_abc_document_parsers import parse_tei, parse_jats, emit_markdown

# Parse XML into intermediate Document model
doc = parse_tei(tei_bytes)
doc = parse_jats(jats_bytes)

# Emit Markdown from Document
markdown = emit_markdown(doc)
```

### Validate Markdown

```python
from agr_abc_document_parsers import validate_markdown

result = validate_markdown(markdown_text)
if result.valid:
    print("Document is valid")
else:
    for error in result.errors:
        print(f"Line {error.line}: [{error.rule_id}] {error.message}")
```

### Access Document model classes

```python
from agr_abc_document_parsers import (
    Document, Section, Author, Paragraph,
    Figure, Table, TableCell, Reference,
    Formula, ListBlock, InlineRef,
)
```

## Supported formats

- **GROBID TEI XML** — parsed by `parse_tei()`
- **PMC nXML/JATS** — parsed by `parse_jats()`

Both produce a common `Document` model that is emitted as ABC Markdown.

## Validation rules

The validator checks 9 schema rules (S01–S09). See `MARKDOWN_SCHEMA.md` in the package for the full specification.

## Development

```bash
make install    # install with dev dependencies
make lint       # run ruff
make type-check # run mypy
make test       # run pytest
make test-cov   # run pytest with coverage
make build      # build sdist + wheel
```

## License

MIT
