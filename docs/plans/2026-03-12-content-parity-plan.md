# Content Parity & PMC Web Tests Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all known content gaps in JATS parser, add PMC-based functional tests, and update CI configuration.

**Architecture:** New model fields capture structured metadata (funding, author notes, competing interests, data availability). JATS parser extracts these from XML, emitter renders them as Markdown sections, reader parses them back. PMC web tests download real nXML + BioC text and compare sentence-by-sentence.

**Tech Stack:** Python 3.9+, lxml, pytest, urllib (stdlib), difflib

**Spec:** `docs/specs/2026-03-12-content-parity-and-ci-design.md`

---

## Chunk 1: Model + JATS Parser Fixes

### Task 1: Add new model fields and export

**Files:**
- Modify: `src/agr_abc_document_parsers/models.py`
- Modify: `src/agr_abc_document_parsers/__init__.py`

- [ ] **Step 1: Add FundingEntry dataclass and new Document fields**

In `models.py`, add `FundingEntry` dataclass after `SecondaryAbstract`:
```python
@dataclass
class FundingEntry:
    funder: str = ""
    award_ids: list[str] = field(default_factory=list)
```

Add to `Document` (after `article_type`):
```python
    funding: list[FundingEntry] = field(default_factory=list)
    funding_statement: str = ""
    data_availability: str = ""
    author_notes: list[str] = field(default_factory=list)
    competing_interests: str = ""
```

- [ ] **Step 2: Export FundingEntry from __init__.py**

Add `FundingEntry` to the `from agr_abc_document_parsers.models import` block.

- [ ] **Step 3: Run existing tests to verify no breakage**

Run: `pytest -v`
Expected: All 286 tests pass (new fields have defaults)

---

### Task 2: JATS parser - funding, author notes, competing interests, data availability

**Files:**
- Modify: `src/agr_abc_document_parsers/jats_parser.py`
- Modify: `tests/test_jats_parser.py`

- [ ] **Step 1: Write tests for new JATS parsing**

Add to `tests/test_jats_parser.py`:

```python
class TestFundingParsing:
    def test_parse_funding_group(self):
        """Parse funding-group with award-group entries."""
        xml = b"""<article>
          <front><article-meta>
            <funding-group>
              <award-group><funding-source>NIH</funding-source>
                <award-id>R01GM12345</award-id></award-group>
              <award-group><funding-source>Wellcome Trust</funding-source>
                <award-id>098765</award-id><award-id>054321</award-id></award-group>
              <funding-statement>Funded by NIH and Wellcome.</funding-statement>
            </funding-group>
          </article-meta></front>
          <body><sec><title>Intro</title><p>Text.</p></sec></body>
        </article>"""
        doc = parse_jats(xml)
        assert len(doc.funding) == 2
        assert doc.funding[0].funder == "NIH"
        assert doc.funding[0].award_ids == ["R01GM12345"]
        assert doc.funding[1].funder == "Wellcome Trust"
        assert doc.funding[1].award_ids == ["098765", "054321"]
        assert doc.funding_statement == "Funded by NIH and Wellcome."

    def test_parse_standalone_funding_statement(self):
        """Parse funding-statement without award-group."""
        xml = b"""<article>
          <front><article-meta>
            <funding-group>
              <funding-statement>This work was self-funded.</funding-statement>
            </funding-group>
          </article-meta></front>
          <body><sec><title>Intro</title><p>Text.</p></sec></body>
        </article>"""
        doc = parse_jats(xml)
        assert len(doc.funding) == 0
        assert doc.funding_statement == "This work was self-funded."


class TestAuthorNotesParsing:
    def test_parse_author_notes(self):
        """Parse author-notes with corresp and fn elements."""
        xml = b"""<article>
          <front><article-meta>
            <author-notes>
              <corresp id="cor1">Corresponding author: foo@bar.edu</corresp>
              <fn fn-type="equal"><p>These authors contributed equally.</p></fn>
              <fn fn-type="present-address"><p>Current address: MIT.</p></fn>
            </author-notes>
          </article-meta></front>
          <body><sec><title>Intro</title><p>Text.</p></sec></body>
        </article>"""
        doc = parse_jats(xml)
        assert len(doc.author_notes) == 3
        assert "foo@bar.edu" in doc.author_notes[0]
        assert "contributed equally" in doc.author_notes[1]
        assert "MIT" in doc.author_notes[2]


class TestCompetingInterestsParsing:
    def test_parse_coi_from_author_notes(self):
        """Parse competing interests from fn-type=conflict in author-notes."""
        xml = b"""<article>
          <front><article-meta>
            <author-notes>
              <fn fn-type="conflict"><p>The authors declare no competing interests.</p></fn>
            </author-notes>
          </article-meta></front>
          <body><sec><title>Intro</title><p>Text.</p></sec></body>
        </article>"""
        doc = parse_jats(xml)
        assert "no competing interests" in doc.competing_interests

    def test_parse_coi_from_back_fn_group(self):
        """Parse competing interests from fn-group in back."""
        xml = b"""<article>
          <front><article-meta></article-meta></front>
          <body><sec><title>Intro</title><p>Text.</p></sec></body>
          <back>
            <fn-group>
              <fn fn-type="COI-statement"><p>No conflicts.</p></fn>
            </fn-group>
          </back>
        </article>"""
        doc = parse_jats(xml)
        assert "No conflicts" in doc.competing_interests

    def test_coi_excluded_from_back_matter(self):
        """COI footnotes should NOT appear in back_matter."""
        xml = b"""<article>
          <front><article-meta></article-meta></front>
          <body><sec><title>Intro</title><p>Text.</p></sec></body>
          <back>
            <fn-group>
              <fn fn-type="conflict"><p>No conflicts.</p></fn>
              <fn fn-type="other"><p>Some other note.</p></fn>
            </fn-group>
          </back>
        </article>"""
        doc = parse_jats(xml)
        assert "No conflicts" in doc.competing_interests
        # The "other" fn should still be in back_matter
        all_notes = []
        for sec in doc.back_matter:
            all_notes.extend(sec.notes)
        assert any("Some other note" in n for n in all_notes)
        assert not any("No conflicts" in n for n in all_notes)


class TestDataAvailabilityParsing:
    def test_parse_from_back_notes(self):
        """Parse data availability from notes in back."""
        xml = b"""<article>
          <front><article-meta></article-meta></front>
          <body><sec><title>Intro</title><p>Text.</p></sec></body>
          <back>
            <notes notes-type="data-availability">
              <p>All data available at https://example.com.</p>
            </notes>
          </back>
        </article>"""
        doc = parse_jats(xml)
        assert "All data available" in doc.data_availability

    def test_parse_from_custom_meta(self):
        """Parse data availability from custom-meta-group."""
        xml = b"""<article>
          <front><article-meta>
            <custom-meta-group>
              <custom-meta>
                <meta-name>Data Availability</meta-name>
                <meta-value>Data deposited at NCBI GEO.</meta-value>
              </custom-meta>
            </custom-meta-group>
          </article-meta></front>
          <body><sec><title>Intro</title><p>Text.</p></sec></body>
        </article>"""
        doc = parse_jats(xml)
        assert "deposited at NCBI GEO" in doc.data_availability

    def test_data_avail_excluded_from_back_matter(self):
        """Data availability notes should NOT appear in back_matter."""
        xml = b"""<article>
          <front><article-meta></article-meta></front>
          <body><sec><title>Intro</title><p>Text.</p></sec></body>
          <back>
            <notes notes-type="data-availability">
              <p>Data at GEO.</p>
            </notes>
            <notes>
              <title>Publisher Note</title>
              <p>Some publisher note.</p>
            </notes>
          </back>
        </article>"""
        doc = parse_jats(xml)
        assert "Data at GEO" in doc.data_availability
        all_text_parts = []
        for sec in doc.back_matter:
            for p in sec.paragraphs:
                all_text_parts.append(p.text)
        assert any("publisher note" in t.lower() for t in all_text_parts)
        assert not any("Data at GEO" in t for t in all_text_parts)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_jats_parser.py -k "Funding or AuthorNotes or CompetingInterests or DataAvailability" -v`
Expected: FAIL (new parsing functions don't exist yet)

- [ ] **Step 3: Implement JATS parsing functions**

Add to `jats_parser.py` (import `FundingEntry` from models):

1. `_parse_funding(root)` — parse `<funding-group>` from article-meta
2. `_parse_author_notes(root)` — parse `<author-notes>` from article-meta
3. `_parse_competing_interests(root)` — extract from author-notes + back fn-group
4. `_parse_data_availability(root)` — extract from back notes + custom-meta

In `parse_jats()`, add calls:
```python
doc.funding, doc.funding_statement = _parse_funding(root)
doc.author_notes = _parse_author_notes(root)
doc.competing_interests = _parse_competing_interests(root)
doc.data_availability = _parse_data_availability(root)
```

Modify `_parse_back_sections()` to skip:
- `<fn-group>` children with `fn-type="conflict"` or `fn-type="COI-statement"` (already captured in competing_interests)
- `<notes notes-type="data-availability">` (already captured in data_availability)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_jats_parser.py -k "Funding or AuthorNotes or CompetingInterests or DataAvailability" -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest -v`
Expected: All tests pass

---

### Task 3: JATS parser - supplementary material expansion, inline-formula, fn-group

**Files:**
- Modify: `src/agr_abc_document_parsers/jats_parser.py`
- Modify: `tests/test_jats_parser.py`

- [ ] **Step 1: Write tests for supplementary material in back**

```python
class TestSupplementaryMaterialExpanded:
    def test_supp_material_in_back(self):
        """Supplementary material as direct child of back is captured."""
        xml = b"""<article>
          <front><article-meta></article-meta></front>
          <body><sec><title>Results</title><p>Text.</p></sec></body>
          <back>
            <supplementary-material>
              <label>S1 Table</label>
              <caption><p>List of primers used.</p></caption>
            </supplementary-material>
          </back>
        </article>"""
        doc = parse_jats(xml)
        all_text = []
        for sec in doc.back_matter:
            for p in sec.paragraphs:
                all_text.append(p.text)
        assert any("S1 Table" in t for t in all_text)
        assert any("primers" in t for t in all_text)

    def test_supp_material_in_app(self):
        """Supplementary material inside app element is captured."""
        xml = b"""<article>
          <front><article-meta></article-meta></front>
          <body><sec><title>Results</title><p>Text.</p></sec></body>
          <back>
            <app-group>
              <app>
                <title>Appendix A</title>
                <supplementary-material>
                  <label>S1 File</label>
                  <caption><p>Raw data.</p></caption>
                </supplementary-material>
              </app>
            </app-group>
          </back>
        </article>"""
        doc = parse_jats(xml)
        all_text = []
        for sec in doc.back_matter:
            for p in sec.paragraphs:
                all_text.append(p.text)
        assert any("S1 File" in t for t in all_text)


class TestInlineFormula:
    def test_inline_formula_preserved(self):
        """Inline formula text is preserved in paragraph."""
        xml = b"""<article>
          <front><article-meta></article-meta></front>
          <body><sec><title>Methods</title>
            <p>The value of <inline-formula>x = 2y + 1</inline-formula> was used.</p>
          </sec></body>
        </article>"""
        doc = parse_jats(xml)
        assert doc.sections
        para_text = doc.sections[0].paragraphs[0].text
        assert "x = 2y + 1" in para_text
        assert "was used" in para_text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_jats_parser.py -k "SupplementaryMaterialExpanded or InlineFormula" -v`

- [ ] **Step 3: Implement**

1. In `_parse_appendices()`: add `_parse_supplementary()` calls for `<supplementary-material>` children of `<app>`
2. In `_parse_back_sections()`: add handling for `<supplementary-material>` direct children of `<back>`
3. In `_inline_text()`: add `"inline-formula"` handling (use `all_text()`)
4. In `_parse_paragraph()`: add `"inline-formula"` to inline element handling

- [ ] **Step 4: Run tests**

Run: `pytest -v`
Expected: All pass

---

### Task 4: Markdown emitter - new sections

**Files:**
- Modify: `src/agr_abc_document_parsers/md_emitter.py`
- Modify: `tests/test_md_emitter.py`

- [ ] **Step 1: Write emitter tests**

```python
class TestMdEmitterNewSections:
    def test_emit_funding(self):
        doc = _make_doc(
            title="Paper",
            funding=[
                FundingEntry(funder="NIH", award_ids=["R01GM12345"]),
                FundingEntry(funder="Wellcome", award_ids=["098765", "054321"]),
            ],
            funding_statement="This work was supported by grants.",
        )
        md = emit_markdown(doc)
        assert "## Funding" in md
        assert "NIH: R01GM12345" in md
        assert "Wellcome: 098765, 054321" in md
        assert "This work was supported by grants." in md

    def test_emit_author_notes(self):
        doc = _make_doc(
            title="Paper",
            author_notes=["Corresponding author: foo@bar.edu",
                          "These authors contributed equally."],
        )
        md = emit_markdown(doc)
        assert "## Author Notes" in md
        assert "foo@bar.edu" in md
        assert "contributed equally" in md

    def test_emit_competing_interests(self):
        doc = _make_doc(
            title="Paper",
            competing_interests="The authors declare no competing interests.",
        )
        md = emit_markdown(doc)
        assert "## Competing Interests" in md
        assert "no competing interests" in md

    def test_emit_data_availability(self):
        doc = _make_doc(
            title="Paper",
            data_availability="All data at https://example.com.",
        )
        md = emit_markdown(doc)
        assert "## Data Availability" in md
        assert "https://example.com" in md

    def test_new_sections_before_references(self):
        """New sections appear between Acknowledgments and References."""
        doc = _make_doc(
            title="Paper",
            acknowledgments="Thanks.",
            funding_statement="Funded.",
            competing_interests="None.",
            references=[Reference(index=1, authors=["A B"],
                                  title="T", journal="J", year="2024")],
        )
        md = emit_markdown(doc)
        lines = md.split("\n")
        ack_idx = next(i for i, ln in enumerate(lines)
                       if "## Acknowledgments" in ln)
        fund_idx = next(i for i, ln in enumerate(lines)
                        if "## Funding" in ln)
        ref_idx = next(i for i, ln in enumerate(lines)
                       if "## References" in ln)
        assert ack_idx < fund_idx < ref_idx
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement emitter functions**

Add to `md_emitter.py`:
- `_emit_funding(doc, lines)` — entries as "Funder: ID1, ID2", then statement
- `_emit_author_notes(doc, lines)` — each note as paragraph
- `_emit_competing_interests(doc, lines)` — as section
- `_emit_data_availability(doc, lines)` — as section

In `emit_markdown()`, add calls between `_emit_acknowledgments` and `_emit_back_matter`:
```python
_emit_funding(doc, lines)
_emit_author_notes(doc, lines)
_emit_competing_interests(doc, lines)
_emit_data_availability(doc, lines)
```

Import `FundingEntry` from models (needed for type annotations).

- [ ] **Step 4: Run tests**

Run: `pytest -v`
Expected: All pass

---

## Chunk 2: Reader + Plain Text + Config

### Task 5: Markdown reader - parse new sections

**Files:**
- Modify: `src/agr_abc_document_parsers/md_reader.py`
- Modify: `tests/test_md_reader.py`

- [ ] **Step 1: Write reader tests**

Add round-trip tests that emit markdown with new fields, then read it back and verify the fields are populated.

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement reader**

In `md_reader.py`:
- Add `_FUNDING_ENTRY_RE = re.compile(r"^(.+?):\s+(.+)$")` for parsing funding entries
- Recognize `## Funding`, `## Author Notes`, `## Competing Interests`, `## Data Availability` as known H2 sections
- Parse their content into the corresponding Document fields
- Import `FundingEntry` from models

- [ ] **Step 4: Run tests**

Run: `pytest -v`
Expected: All pass

---

### Task 6: Plain text extractor - include new fields

**Files:**
- Modify: `src/agr_abc_document_parsers/plain_text.py`
- Modify: `tests/test_plain_text.py`

- [ ] **Step 1: Write tests**

Test that `extract_plain_text()` includes funding statement, author notes, competing interests, and data availability text.

- [ ] **Step 2: Implement**

In `extract_plain_text()`, after acknowledgments:
```python
if doc.funding_statement:
    parts.append(strip_markdown_formatting(doc.funding_statement))
for note in doc.author_notes:
    parts.append(strip_markdown_formatting(note))
if doc.competing_interests:
    parts.append(strip_markdown_formatting(doc.competing_interests))
if doc.data_availability:
    parts.append(strip_markdown_formatting(doc.data_availability))
```

- [ ] **Step 3: Run tests**

Run: `pytest -v`
Expected: All pass

---

### Task 7: pytest configuration and gitignore

**Files:**
- Modify: `pyproject.toml`
- Modify: `.gitignore`

- [ ] **Step 1: Add webtest marker to pyproject.toml**

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["webtest: tests that require network access to PMC (deselected by default)"]
addopts = "-m 'not webtest'"
```

- [ ] **Step 2: Add cache dir to .gitignore**

```
# PMC test data cache
tests/.pmcdata/
```

- [ ] **Step 3: Run tests to verify config works**

Run: `pytest -v`
Expected: All existing tests pass, no webtest marker warnings

---

## Chunk 3: PMC Web Test Infrastructure

### Task 8: conftest.py CLI options

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add CLI options**

```python
import os

def pytest_addoption(parser):
    parser.addoption("--count", type=int, default=500,
                     help="Number of PMC articles to test")
    parser.addoption("--ncbi-api-key", default=None,
                     help="NCBI API key (or set NCBI_API_KEY env var)")
    parser.addoption("--refresh-cache", action="store_true", default=False,
                     help="Force re-download of cached PMC data")
```

---

### Task 9: Fixed articles list

**Files:**
- Create: `tests/pmc_fixed_articles.txt`

- [ ] **Step 1: Create seed list**

Include ~10-15 PMCIDs known to exercise edge cases (sub-articles, funding, supplementary material, etc.).

---

### Task 10: PMC web test module

**Files:**
- Create: `tests/test_pmc_conversion.py`

- [ ] **Step 1: Implement PMC data helpers**

Functions:
- `_get_api_key(request)` — from CLI option or env var
- `_rate_limit(api_key)` — 3/sec without key, 10/sec with
- `_fetch_random_pmcids(count, api_key)` — esearch with random retstart
- `_fetch_nxml(pmcid, api_key)` — efetch rettype=xml
- `_fetch_bioc(pmcid)` — BioC JSON API
- `_load_fixed_articles()` — read pmc_fixed_articles.txt
- `_ensure_cached(pmcid, cache_dir, api_key, refresh)` — download if missing

- [ ] **Step 2: Implement comparison logic**

Functions:
- `_extract_bioc_sentences(bioc_json)` — parse BioC passages into sentences
- `_normalize_sentence(s)` — collapse whitespace, strip punctuation
- `_token_overlap(s1, s2)` — fast pre-filter
- `_find_best_match(sentence, candidates)` — SequenceMatcher with pre-filter
- `_compare_article(pmcid, cache_dir)` — full comparison, returns verdict dict

- [ ] **Step 3: Implement parametrized test**

```python
@pytest.mark.webtest
class TestPMCConversion:
    def test_conversion_parity(self, pmcid, pmc_cache_dir, ...):
        result = _compare_article(pmcid, pmc_cache_dir)
        if result["verdict"] == "FAIL":
            pytest.fail(f"PMC{pmcid}: {result['dropped']} dropped sentences")
```

Use `pytest_generate_tests` to parametrize from fixed list + random PMCIDs.

- [ ] **Step 4: Implement report generation**

Session-scoped fixture finalizer writes `report.json` to cache dir.

- [ ] **Step 5: Run a small web test to verify**

Run: `pytest -m webtest --count=5 -v`
Expected: Downloads 5 articles, compares, generates report

---

### Task 11: Version bump and final verification

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Bump version to 1.3.0**

- [ ] **Step 2: Run full test suite**

Run: `pytest -v`
Expected: All tests pass

- [ ] **Step 3: Run linting and type checks**

Run: `ruff check src/ tests/ && mypy src/`
Expected: Clean

---
