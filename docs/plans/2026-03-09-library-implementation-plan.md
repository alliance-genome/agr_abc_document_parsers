# agr_abc_document_parsers — Implementation Plan

**Date:** 2026-03-09
**Jira:** SCRUM-5869
**Points:** 13
**Status:** In Progress

## Overview

Shared Python library for the Alliance of Genome Resources (AGR) document
processing pipeline. Provides parsers, emitters, readers, and validators for
the ABC Markdown format — the canonical text representation used across all AGR
services for scientific publications.

### Why this library exists

The ABC is migrating from GROBID TEI XML to Markdown as the primary text
format. Multiple services need to read and write this format:

- **agr_literature_service** — converts XML to Markdown, stores and serves files
- **agr_pdf_extraction_service** — produces Markdown from PDFs via AI engines
- **agr_automated_information_extraction** — consumes Markdown for ML pipelines
- **agr_ai_curation** — reads Markdown for LLM-based curation

A shared library avoids duplicating parsers and ensures all services agree on
the document format.

### Source code being moved

The `xml2md` module currently lives in `agr_literature_service/lit_processing/xml2md/`:

| Module | Purpose | LOC (approx) |
|---|---|---|
| `models.py` | 12 dataclasses: Document, Section, Author, Table, Figure, etc. | 112 |
| `jats_parser.py` | PMC NXML/JATS → Document | ~500 |
| `tei_parser.py` | GROBID TEI → Document | ~400 |
| `md_emitter.py` | Document → Markdown string | ~300 |
| `md_validator.py` | Validates Markdown against schema rules S01–S09 | ~200 |
| `xml_utils.py` | Shared XML parsing helpers | ~50 |
| `converter.py` | Orchestrator: detect format, parse, emit | 76 |
| `MARKDOWN_SCHEMA.md` | Schema spec (9 validation rules) | 159 |

Tests: 5 test files + 3 gzipped TEI fixtures.

Dependencies: `lxml` (XML parsing).

---

## Phase 1: Repository setup and code migration

### 1.1 Python package structure

```
agr_abc_document_parsers/
├── docs/
│   └── plans/
│       └── 2026-03-09-library-implementation-plan.md
├── src/
│   └── agr_abc_document_parsers/
│       ├── __init__.py          # public API re-exports
│       ├── py.typed             # PEP 561 marker
│       ├── models.py            # Document model dataclasses
│       ├── jats_parser.py       # JATS/NXML → Document
│       ├── tei_parser.py        # TEI → Document
│       ├── md_emitter.py        # Document → Markdown
│       ├── md_validator.py      # Markdown validation (S01–S09)
│       ├── xml_utils.py         # XML parsing helpers
│       ├── converter.py         # Orchestrator (detect + parse + emit)
│       └── MARKDOWN_SCHEMA.md   # Schema specification
├── tests/
│   ├── conftest.py
│   ├── test_jats_parser.py
│   ├── test_tei_parser.py
│   ├── test_md_emitter.py
│   ├── test_md_validator.py
│   ├── test_converter.py
│   └── fixtures/
│       ├── tei_with_figures_keywords.tei.gz
│       ├── tei_with_tables.tei.gz
│       └── tei_no_abstract_no_doi.tei.gz
├── pyproject.toml               # PEP 621 metadata + build config
├── LICENSE                      # MIT (matching AGR convention)
├── README.md
├── Makefile                     # dev shortcuts: lint, test, build
└── .github/
    └── workflows/
        ├── ci.yml               # flake8 + mypy + pytest on PR/push
        └── publish.yml          # PyPI publish on tagged release
```

Uses `src/` layout (PEP 621 best practice) to prevent accidental imports from
the working directory during development.

### 1.2 Package metadata (pyproject.toml)

- Name: `agr-abc-document-parsers`
- Python: `>=3.10`
- Dependencies: `lxml>=4.9`
- Optional deps: `[dev]` group with `pytest`, `flake8`, `mypy`, `lxml-stubs`
- Build backend: `hatchling` or `setuptools` (whichever AGR typically uses)

### 1.3 Code migration steps

1. Copy modules from `agr_literature_service/lit_processing/xml2md/` to
   `src/agr_abc_document_parsers/`
2. Update all internal imports from
   `agr_literature_service.lit_processing.xml2md.X` to
   `agr_abc_document_parsers.X`
3. Update `__init__.py` to expose public API:
   - `convert_xml_to_markdown`, `detect_format`
   - `parse_jats`, `parse_tei`
   - `emit_markdown`
   - `validate_markdown`, `ValidationResult`, `ValidationIssue`, `Severity`
   - All model classes: `Document`, `Section`, `Author`, `Paragraph`, etc.
4. Copy tests and fixtures, update imports
5. Verify all tests pass in the new repo

### 1.4 CI/CD

**ci.yml** — runs on push/PR to main:
- `flake8` with project config
- `mypy --strict` (or matching the lit service config)
- `pytest` with coverage

**publish.yml** — runs on tag push (`v*`):
- Build sdist + wheel
- Publish to PyPI via trusted publisher (OIDC, no API token needed)

### 1.5 Acceptance criteria (Phase 1)

- [ ] GitHub repo created at `alliance-genome/agr_abc_document_parsers`
- [ ] `src/` layout with `pyproject.toml` (PEP 621)
- [ ] All 7 modules + schema doc moved and imports updated
- [ ] All 5 test files pass
- [ ] `py.typed` marker present
- [ ] CI workflow: flake8 + mypy + pytest
- [ ] PyPI publish workflow (triggered on tag)
- [ ] README with install instructions and basic usage examples
- [ ] Publish `v0.1.0` to PyPI (pre-release — full API not yet stable)

**Note:** Phase 1 publishes `v0.1.0`, not `1.0.0`. The `1.0.0` release comes
after Phase 2 adds md_reader and plain_text extraction and the API is stable.

---

## Phase 2: Markdown reader

### 2.1 `md_reader.py` — parse Markdown back to Document

Implements the reverse of `md_emitter.py`: reads an ABC-format Markdown string
and produces a `Document` model instance.

**Public API:**
```python
def read_markdown(text: str) -> Document:
    """Parse ABC-format Markdown into a Document model."""
```

**Parsing strategy:**

Use a line-by-line state machine rather than a full Markdown AST parser.
The ABC Markdown schema is constrained enough that regex-based line parsing
is simpler and has no external dependency:

- H1 line → `Document.title`
- Non-heading line after H1, before first H2 → author line (comma-split)
- `## Abstract` section → `Document.abstract` paragraphs
- `**Keywords:**` line → `Document.keywords`
- H2–H6 → recursive `Section` objects matching heading hierarchy
- GFM table blocks → `Table` / `TableCell` objects
- `**Figure N.**` lines → `Figure` objects
- `**Table N.**` caption lines → attach to preceding `Table`
- `## References` → `Reference` objects (parse numbered list entries)
- `## Acknowledgments` → `Document.acknowledgments`
- Inline formatting preserved as-is (no need to parse `*italic*` etc. into
  separate tokens — the model stores text with formatting)

**Why not `mistune` or another parser?**

The original plan listed `mistune` as a dependency. After reviewing the schema
and emitter, a line-based parser is simpler because:
- The schema is strict and predictable (no arbitrary nesting)
- We need to round-trip faithfully (AST parsers normalize whitespace)
- No external dependency to maintain
- Easier to debug schema-specific edge cases

If the line parser proves insufficient for complex inline content, `mistune`
can be added later as an optional dependency.

### 2.2 Round-trip testing

The key correctness test: for any `Document` produced by `parse_jats()` or
`parse_tei()`, the following should hold:

```python
original_md = emit_markdown(document)
round_tripped = read_markdown(original_md)
round_tripped_md = emit_markdown(round_tripped)
assert original_md == round_tripped_md
```

Note: `Document` object equality may differ on fields not in Markdown (e.g.,
`Author.orcid`, `Author.affiliations`, `Figure.graphic_url`). The test
compares emitted Markdown, not Document objects directly.

### 2.3 Acceptance criteria (Phase 2)

- [ ] `read_markdown(text) -> Document` parses all schema elements
- [ ] Round-trip test passes on all existing test fixtures
- [ ] Round-trip test passes on a sample of real converted production files
- [ ] No new external dependencies

---

## Phase 3: Plain text extraction

### 3.1 `plain_text.py` — extract ML-ready plain text

Downstream ML pipelines (agr_automated_information_extraction) need plain text
without Markdown formatting. Currently they use `AllianceTEI` to extract text
from GROBID TEI. This module replaces that with a simpler Markdown-based
approach.

**Public API:**
```python
@dataclass
class PlainTextDoc:
    title: str
    abstract: str
    fulltext: str
    sentences: list[str]
    keywords: list[str]

def extract_plain_text(
    md_text: str,
    supplements: list[str] | None = None,
) -> PlainTextDoc:
    """Extract plain text from ABC Markdown for ML pipelines."""
```

**Implementation:**
- Use `read_markdown()` to get a `Document`
- Strip inline formatting: `*italic*` → `italic`, `**bold**` → `bold`,
  `<sup>x</sup>` → `x`, `<sub>x</sub>` → `x`, `[text](url)` → `text`
- `title` = `Document.title`
- `abstract` = joined abstract paragraphs
- `fulltext` = body section text + supplement text (excluding References)
- `sentences` = split on sentence boundaries (regex-based: `.!?` followed by
  space + uppercase, handling common abbreviations)
- `keywords` = `Document.keywords`

### 3.2 Acceptance criteria (Phase 3)

- [ ] `PlainTextDoc` dataclass with title, abstract, fulltext, sentences, keywords
- [ ] `extract_plain_text()` strips all Markdown formatting
- [ ] Supplement text concatenated into fulltext
- [ ] Sentence splitting handles common abbreviations (Dr., Fig., et al., etc.)
- [ ] Test with real converted Markdown files

---

## Phase 4: Supplement support

### 4.1 Document model extension

Add `supplements: list[Document]` to the `Document` dataclass.

The emitter and reader need conventions for multi-document files. Options:
- **Separate files** (recommended): each supplement is its own Markdown file.
  The `Document.supplements` field is populated by the caller loading multiple
  files. No changes to the Markdown format itself.
- **Separator in single file**: use a `---` + metadata marker. More complex,
  less clear.

Recommend separate files — matches how S3 storage works (each file has its own
key) and keeps the schema simple.

### 4.2 Acceptance criteria (Phase 4)

- [ ] `Document.supplements: list[Document]` field
- [ ] `extract_plain_text()` accepts supplements parameter
- [ ] Helper function to load main + supplement files into a single Document
- [ ] No changes to Markdown schema (supplements are separate files)

---

## Release plan

| Version | Contents | Milestone |
|---|---|---|
| `v0.1.0` | Phase 1: moved modules, parsers, emitter, validator | Unblocks SCRUM-5865 (import into lit service) |
| `v0.2.0` | Phase 2: md_reader with round-trip support | Unblocks KANBAN-A, KANBAN-B |
| `v0.3.0` | Phase 3: plain_text extraction | Unblocks SCRUM-5873 (consumer migration) |
| `v0.4.0` | Phase 4: supplement support | Unblocks SCRUM-5789 |
| `v1.0.0` | Stable API, all phases complete | API freeze, semver from here |

---

## Dependencies on this library

| Jira | Story | Blocked by |
|---|---|---|
| SCRUM-5865 | Import library into agr_literature_service | v0.1.0 |
| KANBAN-A | PDF extraction service uses library | v0.2.0 |
| KANBAN-B | AI curation uses library | v0.2.0 |
| SCRUM-5873 | Automated info extraction consumes Markdown | v0.3.0 |
| SCRUM-5789 | Supplement conversion | v0.4.0 |
