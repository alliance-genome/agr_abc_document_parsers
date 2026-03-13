# Content Parity, Web Tests, and CI Setup

**Date:** 2026-03-12
**Status:** Approved

## Problem

Analysis of 94 nXML articles shows the JATS parser drops significant content:
~18K words across 11 element types. The biggest gaps are supplementary-material
captions (8K words, 57 articles), author-notes (1.9K, 66 articles), funding
info (2.2K combined, 42 articles), and footnotes (2.2K, 45 articles).

Additionally, the project has no CI pipeline and no way to systematically
validate conversion quality against real-world PMC articles.

## Goals

1. Fix all known content gaps in the JATS parser.
2. Build a PMC-based functional test suite to validate conversion parity.
3. Set up GitHub Actions CI for lint, type-check, and unit tests.
4. Enable iterative improvement driven by test results.

---

## Part 1: Known Parser Fixes

### 1.1 New Model Fields

Add to `Document`:

```python
@dataclass
class FundingEntry:
    funder: str = ""
    award_ids: list[str] = field(default_factory=list)

@dataclass
class Document:
    # ... existing fields ...
    funding: list[FundingEntry] = field(default_factory=list)
    funding_statement: str = ""
    data_availability: str = ""
    author_notes: list[str] = field(default_factory=list)
    competing_interests: str = ""
```

Export `FundingEntry` from `__init__.py`.

### 1.2 JATS Parser Changes

#### Funding (`<funding-group>`)

Parse `<funding-group>` from `<article-meta>`:

```xml
<funding-group>
  <award-group>
    <funding-source>NIH</funding-source>
    <award-id>R01GM12345</award-id>
  </award-group>
</funding-group>
```

- Each `<award-group>` becomes a `FundingEntry`
- `<funding-group>/<funding-statement>` (child element per JATS 1.3) goes to
  `doc.funding_statement`. Also check for standalone `<funding-statement>` in
  `<article-meta>` as a fallback for older JATS versions.

#### Author Notes (`<author-notes>`)

Parse `<author-notes>` from `<article-meta>`:

```xml
<author-notes>
  <corresp id="cor1">*Corresponding author: <email>foo@bar.edu</email></corresp>
  <fn fn-type="equal"><p>These authors contributed equally.</p></fn>
  <fn fn-type="present-address"><p>Current address: ...</p></fn>
</author-notes>
```

- Each `<corresp>` and `<fn>` child becomes an entry in `doc.author_notes`
- Corresponding author emails are also captured in `Author.email` (existing)

#### Competing Interests

Extract from `<fn fn-type="conflict">` or `<fn fn-type="COI-statement">` in:
- `<author-notes>`
- `<fn-group>` in `<back>`

Stored in `doc.competing_interests`.

#### Data Availability

Extract from:
- `<notes notes-type="data-availability">` in `<back>`
- `<custom-meta-group>/<custom-meta>` with `<meta-name>Data Availability</meta-name>`

Stored in `doc.data_availability`.

#### Supplementary Material (expanded coverage)

Currently parsed only inside `<sec>`. Also parse from:
- Direct children of `<back>` (`<back>/<supplementary-material>`)
- Inside `<app>` elements (both inside `<app-group>` and standalone `<app>`
  directly under `<back>`)
- Inside `<sec>` children of `<back>`

All locations use the existing `_parse_supplementary()` helper.

#### Inline Formulas (`<inline-formula>`)

Add to `_inline_text()` and `_parse_paragraph()`:
- Extract text content from `<inline-formula>` (may contain `<tex-math>`,
  `<mml:math>` in namespace `http://www.w3.org/1998/Math/MathML`, or
  `<alternatives>`)
- Use `all_text()` to get readable representation
- Preserve inline (don't break into separate block)
- Note: MathML namespace requires namespace-aware XPath when searching
  for `<mml:math>` children

#### fn-group Improvements

The parser already handles `<fn-group>` in `<back>` and inside `<sec>`.
Ensure completeness:
- Parse `<fn-group>` inside `<boxed-text>`
- Parse `<fn-group>` inside `<app>` (appendices)

### 1.3 Markdown Emitter Changes

Add new sections between Acknowledgments and References:

```markdown
## Funding

NIH: R01GM12345, R01HG67890
Wellcome Trust: 098765

This work was supported by ...

## Author Notes

*Corresponding author: alice@example.edu
These authors contributed equally to this work.

## Competing Interests

The authors declare no competing interests.

## Data Availability

All data are available at ...
```

Emission order (updated):
1. Title
2. Metadata (journal, DOI, etc.)
3. Categories
4. Authors + affiliations
5. Abstract
6. Secondary abstracts
7. Keywords
8. Body sections
9. Doc-level figures/tables
10. Acknowledgments
11. **Funding** (new)
12. **Author Notes** (new)
13. **Competing Interests** (new)
14. **Data Availability** (new)
15. Back matter
16. References
17. Author role footnotes
18. Sub-articles

### 1.4 Markdown Reader Changes

Add parsing for the new sections:
- `## Funding` -> `doc.funding` + `doc.funding_statement`
  - Lines matching `Name: ID1, ID2` pattern are parsed as `FundingEntry`
  - Remaining prose lines become `doc.funding_statement`
- `## Author Notes` -> `doc.author_notes`
- `## Competing Interests` -> `doc.competing_interests`
- `## Data Availability` -> `doc.data_availability`

### 1.5 Plain Text Extractor Changes

Include new fields in `extract_plain_text()`:
- Funding statement
- Author notes
- Competing interests
- Data availability

### 1.6 Validator Changes

No new validation rules needed. The new sections (Funding, Author Notes,
Competing Interests, Data Availability) are emitted as H2 headings BEFORE
References in the emission order. Since S05 only requires References to be
the last H2 (ignoring sub-article H2s after `---`), and S06 only requires
Acknowledgments before References, the new sections do not violate any
existing rules. This is safe because the emission order places them between
Acknowledgments (item 10) and Back matter (item 15), both of which precede
References (item 16).

**Important for `_parse_back_sections`**: Elements that are now extracted
into dedicated fields (competing interests from `<fn fn-type="conflict">`,
data availability from `<notes notes-type="data-availability">`) must be
EXCLUDED from `back_matter` to avoid content duplication. The parser should
skip these elements in `_parse_back_sections` once they have been captured
into their dedicated Document fields.

---

## Part 2: PMC Web Test Infrastructure

### 2.1 Test File

`tests/test_pmc_conversion.py` — marked with `@pytest.mark.webtest`.

### 2.2 pytest Configuration

```toml
[tool.pytest.ini_options]
markers = ["webtest: tests that require network access to PMC (deselected by default)"]
addopts = "-m 'not webtest'"
```

Run with: `pytest -m webtest --count=500`

### 2.3 CLI Options

Added via `conftest.py`:
- `--count` (default: 500) — total number of articles to test
- `--ncbi-api-key` — optional NCBI API key for faster rate limits
  (also reads `NCBI_API_KEY` env var)

### 2.4 Data Sources

**Random OA articles:**
- NCBI E-utilities `esearch` with `db=pmc`, `term=open access[filter]`
- First query with `retmax=0` to get total count, then random `retstart`
  within that range with `sort=pub_date` (chronological, avoids relevance bias)
- Returns PMCIDs

**Fixed article list:**
- `tests/pmc_fixed_articles.txt` — one PMCID per line, `#` comments
- Checked into repo, curated for edge cases

**Downloads per article:**
- nXML: `efetch` with `db=pmc`, `rettype=xml`
- BioC JSON: PMC BioC API (`https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/bioc_json/{PMCID}/unicode`)

### 2.5 Cache

Directory: `tests/.pmcdata/` (`.gitignore`'d)

Structure:
```
tests/.pmcdata/
  PMC3225075/
    article.nxml
    bioc.json
  PMC7654321/
    article.nxml
    bioc.json
  report.json
```

Cache persists across runs. Files are only re-downloaded if missing.
A `--refresh-cache` CLI flag can force re-download if needed.

### 2.6 Comparison Logic

Per article:

1. Parse nXML -> `Document` via `parse_jats()`
2. Extract plain text via `extract_plain_text(doc, include_sub_articles=True)`
3. Parse BioC JSON -> extract passage texts
4. Split both into sentences (normalize: collapse whitespace, strip
   leading/trailing punctuation)
5. For each BioC sentence, find best match in our output:
   - Fast pre-filter: normalized token overlap (set intersection) >= 0.7
     to eliminate obviously non-matching candidates
   - Full match: `difflib.SequenceMatcher` ratio >= 0.95 on pre-filtered
     candidates only (avoids O(n^2) on full corpus)
6. Classify: matched (>= 0.95), dropped (< 0.95)

### 2.7 Per-Article Verdict

- **PASS**: 0 dropped sentences
- **WARN**: 1-3 dropped sentences (likely formatting noise)
- **FAIL**: 4+ dropped sentences

Test assertion: `pytest.fail()` on FAIL, print warning on WARN.

### 2.8 Report

Fixture finalizer writes `tests/.pmcdata/report.json`:

```json
{
  "generated_at": "2026-03-12T15:30:00Z",
  "parser_version": "1.3.0",
  "total_articles": 500,
  "pass": 480,
  "warn": 15,
  "fail": 5,
  "articles": {
    "PMC3225075": {
      "verdict": "PASS",
      "total_sentences": 342,
      "matched": 342,
      "dropped": 0,
      "dropped_sentences": []
    },
    "PMC7654321": {
      "verdict": "FAIL",
      "total_sentences": 210,
      "matched": 200,
      "dropped": 10,
      "dropped_sentences": [
        "This work was funded by NIH grant R01GM12345.",
        "..."
      ]
    }
  },
  "summary_by_type": {
    "most_common_dropped_patterns": ["funding", "author-notes", "..."]
  }
}
```

Also prints summary table to stdout.

---

## Part 3: GitHub Actions CI

### 3.1 Workflow: `.github/workflows/ci.yml` (update existing)

The existing `ci.yml` will be updated. Triggers: push to main, pull
requests to main.

```yaml
jobs:
  test:
    strategy:
      matrix:
        python-version: ["3.9", "3.11", "3.12"]
    runs-on: ubuntu-latest
    steps:
      - Checkout
      - Setup Python
      - pip install -e ".[dev]"
      - ruff check src/ tests/
      - mypy src/
      - pytest -v
```

The `addopts = "-m 'not webtest'"` in pyproject.toml ensures web tests
are automatically excluded from CI.

---

## Part 4: Iterative Improvement

After the known fixes are implemented:

1. Run `pytest -m webtest --count=500`
2. Review `report.json` for remaining FAIL/WARN articles
3. Identify patterns in dropped sentences
4. Fix parser for newly discovered gaps
5. Optionally promote specific articles to unit tests (copy nXML snippet
   into `tests/fixtures/`, write targeted test)
6. Repeat until FAIL count is acceptable

---

## Dependencies

New runtime dependencies: **none** (all PMC API calls use `urllib` from stdlib).

New dev dependencies:
- None beyond existing (pytest, ruff, mypy)

---

## Files Changed

**New files:**
- `tests/test_pmc_conversion.py`
- `tests/pmc_fixed_articles.txt`

**Modified files:**
- `.github/workflows/ci.yml` — update with lint + type-check steps
- `tests/conftest.py` — add `--count`, `--ncbi-api-key`, `--refresh-cache` options
- `src/agr_abc_document_parsers/models.py` — new dataclass + fields
- `src/agr_abc_document_parsers/jats_parser.py` — new parsing functions
- `src/agr_abc_document_parsers/md_emitter.py` — new emission sections
- `src/agr_abc_document_parsers/md_reader.py` — new section readers
- `src/agr_abc_document_parsers/plain_text.py` — include new fields
- `src/agr_abc_document_parsers/__init__.py` — export FundingEntry
- `pyproject.toml` — pytest markers, version bump
- `.gitignore` — add `tests/.pmcdata/`
- `tests/test_md_emitter.py` — tests for new sections
- `tests/test_jats_parser.py` — tests for new parsing
- `tests/test_md_reader.py` — tests for round-trip of new fields
