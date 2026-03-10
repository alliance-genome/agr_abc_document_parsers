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

## Phase 1: Repository setup and code migration ✅

**Status:** Complete (v0.1.0)

### 1.1 What was delivered

- `src/` layout with hatchling build backend, PEP 621 `pyproject.toml`
- Python `>=3.8`, runtime dep `lxml>=4.9`, dev extras: `pytest`, `pytest-cov`,
  `ruff`, `mypy`, `lxml-stubs`
- All 8 modules + `MARKDOWN_SCHEMA.md` migrated with updated imports
- 156 tests passing (5 test files + 3 gzipped TEI integration fixtures)
- `ruff` lint and `mypy` type-checking clean
- CI workflow: ruff + mypy + pytest (Python 3.9/3.11/3.12 matrix)
- PyPI publish workflow via trusted publisher (OIDC) on `v*` tag
- PEP 561 `py.typed` marker, MIT license, README, Makefile

### 1.2 Acceptance criteria (Phase 1)

- [x] `src/` layout with `pyproject.toml` (PEP 621)
- [x] All 7 modules + schema doc moved and imports updated
- [x] All 5 test files pass (156 tests)
- [x] `py.typed` marker present
- [x] CI workflow: ruff + mypy + pytest
- [x] PyPI publish workflow (triggered on tag)
- [x] README with install instructions and basic usage examples
- [ ] GitHub repo created at `alliance-genome/agr_abc_document_parsers`
- [ ] Publish `v0.1.0` to PyPI

---

## Phase 2: Markdown reader + supplement support

### 2.1 Model extension — `Document.supplements`

Add a `supplements` field to the `Document` dataclass:

```python
@dataclass
class Document:
    # ... existing fields ...
    supplements: list[Document] = field(default_factory=list)
```

Supplements are separate Markdown files (one per supplement), each parsed into
a `Document` via `read_markdown()`. They may have variable format — no title,
no abstract, just body sections — and that is fine because the `Document`
model already defaults all fields to empty values.

No changes to the Markdown schema itself. Supplements are separate files,
matching how S3 storage works (each file has its own key).

### 2.2 `md_reader.py` — parse Markdown back to Document

Implements the reverse of `md_emitter.py`: reads an ABC-format Markdown string
and produces a `Document` model instance. Works for both full papers and
supplements with variable/incomplete structure.

**Public API:**
```python
def read_markdown(text: str) -> Document:
    """Parse ABC-format Markdown into a Document model.

    Handles both complete documents (with title, abstract, sections,
    references) and partial documents like supplements (which may lack
    a title, abstract, or references section).
    """
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
- Footnotes (`[^N]: text`) → `Section.notes`
- Lists (`- item` / `1. item`) → `ListBlock` objects
- Formulas (plain text lines between block elements) — best-effort
- Inline formatting preserved as-is (no need to parse `*italic*` etc. into
  separate tokens — the model stores text with formatting)

**Graceful handling of incomplete documents:**

Supplements and other partial Markdown files are handled naturally:
- No H1 → `doc.title == ""`
- No `## Abstract` → `doc.abstract == []`
- No `## References` → `doc.references == []`
- Body starts with H2 directly → first section created normally
- Body has no headings at all → content goes into a preamble section

**Why not `mistune` or another parser?**

A line-based parser is simpler because:
- The schema is strict and predictable (no arbitrary nesting)
- We need to round-trip faithfully (AST parsers normalize whitespace)
- No external dependency to maintain
- Easier to debug schema-specific edge cases
- Supplements have variable format that a strict parser might reject

If the line parser proves insufficient for complex inline content, `mistune`
can be added later as an optional dependency.

### 2.3 Helper to load document with supplements

```python
def load_document_with_supplements(
    main_md: str,
    supplement_mds: list[str] | None = None,
) -> Document:
    """Parse a main document and its supplements into a single Document.

    Args:
        main_md: Markdown text of the main paper.
        supplement_mds: Optional list of Markdown texts for each supplement.

    Returns:
        A Document with supplements populated.
    """
```

### 2.4 Round-trip testing

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

Additional tests for supplements:
- Parse a Markdown file with no title → `doc.title == ""`
- Parse a Markdown file with no abstract → `doc.abstract == []`
- Parse a Markdown file with only body sections → sections populated
- `load_document_with_supplements()` populates `doc.supplements`
- `emit_markdown()` on main doc is unaffected by supplements (supplements
  are separate files, not embedded in the main Markdown)

### 2.5 Acceptance criteria (Phase 2)

- [ ] `Document.supplements: list[Document]` field added
- [ ] `read_markdown(text) -> Document` parses all schema elements
- [ ] `read_markdown()` handles incomplete/partial documents gracefully
- [ ] `load_document_with_supplements()` helper function
- [ ] Round-trip test passes on all existing test fixtures
- [ ] Round-trip test passes on a sample of real converted production files
- [ ] Supplement-specific tests (no title, no abstract, body-only)
- [ ] No new external dependencies
- [ ] `__init__.py` exports `read_markdown`, `load_document_with_supplements`

---

## Phase 3: Plain text extraction

### 3.1 `plain_text.py` — extract ML-ready plain text

Downstream ML pipelines (agr_automated_information_extraction) need plain text
without Markdown formatting. Currently they use `AllianceTEI` to extract text
from GROBID TEI. This module replaces that with a simpler Markdown-based
approach.

No separate dataclass — the `Document` model already has all the structured
data. Plain text extraction is a set of utility functions that operate on
`Document` objects.

**Public API:**
```python
def extract_plain_text(doc: Document, include_supplements: bool = True) -> str:
    """Extract plain text from a Document, stripping all Markdown formatting.

    Returns title + abstract + body sections + supplement text (excluding
    References). Supplements are included by default.
    """

def extract_abstract_text(doc: Document) -> str:
    """Extract plain-text abstract (formatting stripped)."""

def extract_sentences(doc: Document, include_supplements: bool = True) -> list[str]:
    """Split document text into sentences.

    Handles common abbreviations (Dr., Fig., et al., e.g., i.e., etc.)
    to avoid false sentence breaks.
    """

def strip_markdown_formatting(text: str) -> str:
    """Strip inline Markdown formatting from a string.

    Converts:
    - *italic* → italic
    - **bold** → bold
    - <sup>x</sup> → x
    - <sub>x</sub> → x
    - [text](url) → text
    """
```

**Implementation:**
- `extract_plain_text()` walks `doc.title`, `doc.abstract`, `doc.sections`,
  and `doc.supplements[*].sections`, calling `strip_markdown_formatting()`
  on each paragraph/caption/note. Excludes References section.
- `extract_sentences()` calls `extract_plain_text()` then splits on sentence
  boundaries (regex: `.!?` followed by space + uppercase, with abbreviation
  exceptions).
- `strip_markdown_formatting()` is a standalone utility useful for callers
  who need to clean individual strings.

### 3.2 Acceptance criteria (Phase 3)

- [ ] `extract_plain_text(doc)` returns stripped text from all sections
- [ ] `extract_abstract_text(doc)` returns stripped abstract
- [ ] `extract_sentences(doc)` splits on sentence boundaries correctly
- [ ] `strip_markdown_formatting()` handles all inline formats
- [ ] Supplement text included when `include_supplements=True`
- [ ] Sentence splitting handles common abbreviations (Dr., Fig., et al., etc.)
- [ ] Test with real converted Markdown files
- [ ] No new external dependencies

---

## Release plan

| Version | Contents | Milestone |
|---|---|---|
| `v0.1.0` | Phase 1: moved modules, parsers, emitter, validator | Unblocks SCRUM-5865 (import into lit service) |
| `v0.2.0` | Phase 2: md_reader + supplement support on Document | Unblocks KANBAN-A, KANBAN-B, SCRUM-5789 |
| `v0.3.0` | Phase 3: plain_text extraction | Unblocks SCRUM-5873 (consumer migration) |
| `v1.0.0` | Stable API, all phases complete | API freeze, semver from here |

---

## Dependencies on this library

| Jira | Story | Blocked by |
|---|---|---|
| SCRUM-5865 | Import library into agr_literature_service | v0.1.0 |
| KANBAN-A | PDF extraction service uses library | v0.2.0 |
| KANBAN-B | AI curation uses library | v0.2.0 |
| SCRUM-5789 | Supplement conversion | v0.2.0 |
| SCRUM-5873 | Automated info extraction consumes Markdown | v0.3.0 |
