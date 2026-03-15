# PMC Parity Edge Cases (5 remaining failures)

Status: 1054/1059 pass (99.5%) as of 2026-03-14

## 1. Funding section round-trip loss — PMC12979043

**Symptom:** The "Funding" back-matter paragraph is lost through the Markdown round-trip.

**Root cause:** The JATS parser emits both a structured `funding` metadata field and a "Funding"
back-matter section. The emitter produces two `## Funding` headings. `md_reader.py` treats the
second as a duplicate structured field and drops the paragraph text.

**Fix:** Either deduplicate in `md_emitter.py` (skip the back-matter section when structured
funding exists) or teach `md_reader.py` to preserve the second heading as back-matter.

**Files:** `src/agr_abc_document_parsers/md_emitter.py`, `src/agr_abc_document_parsers/md_reader.py`

## 2. LaTeX formula in list-item — PMC12979312

**Symptom:** Content "Generate the observed variables Y=HPT+E" is missing from output.

**Root cause:** `<inline-formula>` contains a LaTeX `\documentclass` block. `all_text()` extracts
no visible text from it. PMC text renders it as plain "Y=HPT+E".

**Fix:** In `xml_utils.py`, when `all_text()` encounters `<inline-formula>`, try extracting from
the `<mml:math>` MathML fallback or at least strip the LaTeX to get a basic text representation.

**Files:** `src/agr_abc_document_parsers/xml_utils.py`

## 3. Number-only table label — PMC12981014

**Symptom:** PMC text has "1 Vibrational Mode Designations..." (just number, no "Table" prefix).
Test classifier marks it as body, but it's a table caption.

**Root cause:** `_classify_pmc_paragraph()` only matches `^Table \d+` and `^Figure \d+`. This
article's supplementary table uses just `1` as the label.

**Fix:** Careful enhancement of `_classify_pmc_paragraph()` to detect number-prefixed captions
without false-positiving on numbered lists. Could cross-reference against our extracted table labels.

**Files:** `tests/test_pmc_conversion.py`

## 4. Systematic review search queries — PMC12987049

**Symptom:** 9 search strategy lines (PubMed/Embase queries) missing from output. BioC also lacks
them (no_bioc).

**Root cause:** These are inside `<boxed-text>` or `<table-wrap>` in the JATS. Our parser extracts
them differently than PMC plain text renders them. Since BioC also lacks them, this may be a PMC
text artifact.

**Impact:** Low — search strategy content, not primary body text.

**Files:** `src/agr_abc_document_parsers/jats_parser.py` (boxed-text handling)

## 5. MDPI inline references in list — PMC12987121

**Symptom:** 8 numbered references inside `<list-item>` elements are missing. BioC also lacks them.

**Root cause:** Our parser extracts `<list>` as a single list block. PMC text splits each
`<list-item>` as a separate paragraph. The content is reference-like but embedded in the body
(MDPI article format).

**Impact:** Low — these are bibliography entries embedded in list items.

**Files:** `tests/test_pmc_conversion.py` (reference detection) or parser list handling
