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

### Load a document from a file

The `Document` class provides file-based loading methods that auto-detect
the format from the file extension (`.tei.gz`, `.nxml.gz`, `.xml`, `.md`):

```python
from agr_abc_document_parsers import Document

# Load main paper from a gzipped nXML file
doc = Document()
doc.load_main_file("paper.nxml.gz")

print(doc.title)       # "Distinct DNA Binding Sites ..."
print(doc.journal)     # "PLoS Genetics"
print(doc.doi)         # "10.1371/journal.pgen.1004133"
print(doc.pmid)        # "24516405"
print(len(doc.sections))   # 5
print(len(doc.references)) # 107

# Add supplements (each becomes a Document in doc.supplements)
doc.add_supplement_file("supp1.tei.gz")
doc.add_supplement_files(["supp2.nxml.gz", "supp3.md"])

# Method chaining
doc = (
    Document()
    .load_main_file("paper.nxml.gz")
    .add_supplement_files(["supp1.tei.gz", "supp2.md"])
)
```

### Load a document from in-memory data

The `load_main` and `add_supplement` methods accept `str` (Markdown) or
`bytes` (XML, optionally gzip-compressed). Format is auto-detected:

```python
from agr_abc_document_parsers import Document

doc = Document()

# bytes input → auto-detects TEI vs JATS from the XML root element
doc.load_main(xml_bytes)
doc.load_main(gzipped_xml_bytes)          # gz decompressed automatically

# str input → parsed as ABC-format Markdown
doc.load_main(markdown_string)

# Explicit format override
doc.load_main(xml_bytes, format="tei")
doc.load_main(xml_bytes, format="jats")

# Add supplements from mixed sources
doc.add_supplement(supplement_xml_bytes)
doc.add_supplements([s1_bytes, s2_bytes, s3_markdown_str])
```

### Convert XML to Markdown (one-step)

```python
from agr_abc_document_parsers import convert_xml_to_markdown

# Auto-detect TEI or JATS format; also accepts gzipped bytes
markdown = convert_xml_to_markdown(xml_bytes)

# Explicit format
markdown = convert_xml_to_markdown(xml_bytes, source_format="tei")
markdown = convert_xml_to_markdown(xml_bytes, source_format="jats")
```

### Parse, inspect, and emit

```python
from agr_abc_document_parsers import parse_tei, parse_jats, emit_markdown

# Parse XML into the intermediate Document model
doc = parse_tei(tei_bytes)    # also accepts gzipped bytes
doc = parse_jats(jats_bytes)

# Inspect the document
print(doc.title, doc.doi, doc.journal, doc.pmid)
for section in doc.sections:
    print(section.heading)
for ref in doc.references:
    print(f"{ref.index}. {ref.title} — {ref.journal}")

# Emit Markdown from Document
markdown = emit_markdown(doc)
```

### Read Markdown back into a Document

```python
from agr_abc_document_parsers import read_markdown, load_document_with_supplements

# Parse ABC-format Markdown → Document (round-trip capable)
doc = read_markdown(markdown_text)

# Load main paper + supplements in one call
doc = load_document_with_supplements(
    main_md=main_text,
    supplement_mds=[supp1_text, supp2_text],
)
```

### Extract plain text for ML pipelines

```python
from agr_abc_document_parsers import (
    extract_plain_text, extract_abstract_text, extract_sentences,
)

# Full document text (title + abstract + body), no Markdown formatting
text = extract_plain_text(doc)

# Optionally include article metadata (journal, DOI, PMID, etc.)
text = extract_plain_text(doc, include_metadata=True)

# Abstract only
abstract = extract_abstract_text(doc)

# Split into sentences (handles abbreviations: Dr., Fig., et al., etc.)
sentences = extract_sentences(doc)

# Exclude supplement text
text = extract_plain_text(doc, include_supplements=False)
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

| Format | Parser | Input |
|--------|--------|-------|
| GROBID TEI XML | `parse_tei()` | `bytes` (plain or gzipped) |
| PMC nXML / JATS | `parse_jats()` | `bytes` (plain or gzipped) |
| ABC Markdown | `read_markdown()` | `str` |

All parsers produce a common `Document` model that can be emitted as ABC
Markdown via `emit_markdown()`.

### File extension auto-detection

When using `load_main_file()` / `add_supplement_file()`:

| Extension | Parser |
|-----------|--------|
| `.tei`, `.tei.gz` | TEI |
| `.nxml`, `.nxml.gz`, `.xml`, `.xml.gz` | JATS |
| `.md` | Markdown |
| `.gz` (other) | Auto-detect from XML root element |

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
