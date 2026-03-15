# AGR ABC Document Parsers — Developer Guide

## Project Overview

Shared parsers, emitters, and validators for the AGR ABC Markdown document format. Converts scientific articles from **JATS XML** (PMC/NLM) and **TEI XML** (GROBID/Alliance) into a structured Markdown format, and can read that Markdown back into the internal model.

## Architecture

The pipeline is: `XML → Document model → Markdown → plain text`

### Source Modules (`src/agr_abc_document_parsers/`)

| Module | Purpose |
|--------|---------|
| `models.py` | Core data model: `Document`, `Section`, `Paragraph`, `Figure`, `Table`, `ListBlock`, etc. |
| `jats_parser.py` | JATS XML → `Document`. Handles PMC/NLM article XML (~1800 lines). |
| `tei_parser.py` | TEI XML → `Document`. Handles GROBID-produced TEI files from Alliance S3. |
| `md_emitter.py` | `Document` → Markdown (AGR ABC format). |
| `md_reader.py` | Markdown → `Document` (round-trip). |
| `md_validator.py` | Validates Markdown against the AGR ABC schema. |
| `plain_text.py` | `Document` → plain text (no formatting). |
| `converter.py` | High-level API: `convert_jats_to_markdown()`, `convert_tei_to_markdown()`. |
| `xml_utils.py` | Shared XML helpers (`all_text()`, namespace handling). |

### Key Design Decisions

- Both JATS and TEI parsers produce the **same `Document` model** — format consistency is enforced at the model level
- `MARKDOWN_SCHEMA.md` defines the AGR ABC Markdown format specification
- `md_reader.py` can reconstruct a `Document` from Markdown (full round-trip)

## Running Tests

### Unit Tests (no network required)
```bash
pytest                              # all unit tests
pytest tests/test_jats_parser.py -x # JATS parser only (~190 tests)
pytest tests/test_tei_parser.py -x  # TEI parser only
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
- `tests/fixtures/` — sample XML files for unit tests. Committed.

## Conventions

- Python 3.8+ compatible (no walrus operator, no `match` statements)
- Line length: 100 characters (ruff)
- Linting: ruff (E, W, F, I, B, C4, UP rules)
- Conventional Commits for git messages
- Only dependency: `lxml>=4.9`
