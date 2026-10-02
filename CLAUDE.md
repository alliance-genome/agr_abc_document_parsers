# AGR ABC Document Parsers — Developer Guide

## Project Overview

Shared parsers, emitters, and validators for the AGR ABC Markdown document format. Converts scientific articles from **JATS XML** (PMC/NLM) and **TEI XML** (GROBID/Alliance), plus **Excel (.xlsx)** and **Word (.docx)** supplement files, into a structured Markdown format, and can read that Markdown back into the internal model.

## Architecture

The pipeline is: `XML / Office file → Document model → Markdown → plain text`

### Source Modules (`src/agr_abc_document_parsers/`)

| Module | Purpose |
|--------|---------|
| `models.py` | Core data model: `Document`, `Section`, `Paragraph`, `Figure`, `Table`, `ListBlock`, etc. |
| `jats_parser.py` | JATS XML → `Document`. Handles PMC/NLM article XML (~1800 lines). |
| `tei_parser.py` | TEI XML → `Document`. Handles GROBID-produced TEI files from Alliance S3. |
| `xlsx_parser.py` | Excel workbook → `Document`. One section per sheet, one table per section. |
| `docx_parser.py` | Word document → `Document`. Headings → sections, body → paragraphs/lists/tables, footnotes. |
| `ooxml_utils.py` | Shared OOXML package reader (`zipfile` + lxml) and namespace-tolerant element helpers. |
| `md_emitter.py` | `Document` → Markdown (AGR ABC format). |
| `md_reader.py` | Markdown → `Document` (round-trip). |
| `md_validator.py` | Validates Markdown against the AGR ABC schema. |
| `plain_text.py` | `Document` → plain text (no formatting). |
| `converter.py` | High-level API: `convert_xml_to_markdown()`, `convert_office_to_markdown()`, `detect_format()`. |
| `xml_utils.py` | Shared XML helpers (`all_text()`, namespace handling). |

### Key Design Decisions

- All parsers (JATS, TEI, xlsx, docx) produce the **same `Document` model** — format consistency is enforced at the model level
- Office files are parsed straight from their OOXML parts with `zipfile` + lxml (no openpyxl / python-docx); `tests/fixtures/*.xlsx|*.docx` were generated with those libraries once and committed
- The emitter writes a section's paragraphs, then tables, then lists; `docx_parser.py` opens heading-less child sections to keep Word's original block order
- `MARKDOWN_SCHEMA.md` defines the AGR ABC Markdown format specification
- `md_reader.py` can reconstruct a `Document` from Markdown (full round-trip)

## Running Tests

### Unit Tests (no network required)
```bash
pytest                              # all unit tests
pytest tests/test_jats_parser.py -x # JATS parser only (~190 tests)
pytest tests/test_tei_parser.py -x  # TEI parser only
pytest tests/test_xlsx_parser.py tests/test_docx_parser.py tests/test_office_loading.py -x  # Office parsers
```

### PMC Parity Tests (`webtest` marker)
Compares JATS→Markdown output against PMC S3 plain text + BioC API.

```bash
# Cached articles only (offline, ~580 articles in tests/.pmcdata/)
pytest -m webtest --cached-only -v --tb=short

# Fetch N new random articles from PMC
pytest -m webtest --count=500 -v --tb=short

# Test a specific article
pytest -m webtest --cached-only -k "PMC12986642" -v --tb=short
```

Options: `--count=N`, `--ncbi-api-key=KEY`, `--refresh-cache`, `--cached-only`

### TEI Parity Tests (`teitest` marker)
Compares TEI→Markdown round-trip for content preservation.

```bash
# Cached TEI files (~51 in tests/.teidata/)
pytest -m teitest --tei-count=51 -v --tb=short

# Fetch N articles from Alliance prod DB (requires .env credentials)
pytest -m teitest --tei-count=200 -v --tb=short
```

Options: `--tei-count=N`

### Linting & Type Checking
```bash
ruff check src/ tests/           # lint (ruff)
ruff format --check src/ tests/  # format check
mypy src/                        # type check
```

### CI
CI runs unit tests (`pytest`), `ruff check`, and `ruff format --check`. Parity tests (webtest/teitest) are **not** in CI — they require network/credentials.

## Test Data Caches

- `tests/.pmcdata/` — cached PMC articles (JATS XML, S3 text, BioC JSON). Gitignored.
- `tests/.teidata/` — cached TEI files + metadata. Gitignored.
- `tests/fixtures/` — sample XML files plus `supplement_tables.xlsx` / `supplement_methods.docx` for unit tests. Committed.
- `tests/ooxml_helpers.py` — builders for hand-written minimal `.xlsx` / `.docx` packages (edge-case tests).

## Conventions

- Python 3.8+ compatible (no walrus operator, no `match` statements)
- Line length: 100 characters (ruff)
- Linting: ruff (E, W, F, I, B, C4, UP rules)
- Conventional Commits for git messages
- Only dependency: `lxml>=4.9`
