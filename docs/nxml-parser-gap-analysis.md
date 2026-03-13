# PubMed NXML (JATS) Parser Gap Analysis

**Date:** 2026-03-13
**Parser:** `src/agr_abc_document_parsers/jats_parser.py`
**Spec:** JATS 1.3 (Journal Article Tag Suite, NISO Z39.96-2019)

## Summary

The JATS parser handles the most common elements well. The PMC parity tests pass
at 100% on 79+ articles. However, several JATS elements that appear in real PMC
articles are either not handled or handled in a lossy way.

**Current coverage:** ~80% of JATS elements by frequency in real articles.
**Key gaps:** Math content, some inline formatting, group containers, older citation
formats.

---

## Priority 1: High-Impact Gaps

### Math content (`<mml:math>`, `<tex-math>`, `<inline-formula>`)
- **Impact:** Math-heavy papers (physics, CS, engineering) will have garbled or
  missing formulas
- **Current behavior:** `<inline-formula>` text preserved via `all_text()` fallback,
  but MathML elements produce garbled text. `<tex-math>` is actively skipped in
  list items.
- **Fix:** Extract readable text from `<tex-math>` (preserve LaTeX), extract
  `<mml:math>` text nodes intelligently, select best representation from
  `<alternatives>` containers

### Inline `<monospace>` formatting
- **Impact:** Gene names, code snippets, file paths lose their formatting
- **Current behavior:** Text preserved but not wrapped in backticks
- **Fix:** Add `"monospace": ("\`", "\`")` to `_INLINE_FMT` dict

### Block elements silently dropped in `<sec>`
- **Impact:** Content loss for articles using these elements
- **Elements:** `<speech>`, `<verse-group>`, `<statement>`, `<code>`,
  `<fig-group>`, `<table-wrap-group>`, `<disp-formula-group>`, `<array>`,
  `<chem-struct-wrap>`
- **Current behavior:** Not in `_SEC_BLOCK_TAGS` or `_BLOCK_TAGS`, so they are
  silently ignored by `_dispatch_sec_child`
- **Fix:** Add fallback in `_dispatch_sec_child` to extract text from unknown
  block elements, or add explicit handlers for the common ones

### `<collab>` (group authors) at article level
- **Impact:** Articles by consortia/groups lose the group author name
- **Current behavior:** Only `<name>` is looked for in `_parse_authors`;
  `<collab>` is only handled in reference citations
- **Fix:** Check for `<collab>` in `_parse_authors` as fallback when no `<name>`

---

## Priority 2: Medium-Impact Gaps

### Missing inline formatting elements
| Element | Purpose | Suggested rendering |
|---|---|---|
| `<sc>` | Small caps | Preserve text as-is |
| `<underline>` | Underline | `<u>...</u>` or plain text |
| `<strike>` | Strikethrough | `~~...~~` (GFM) |
| `<overline>` | Overline | Preserve text as-is |
| `<roman>` | Roman type in italic context | Preserve text as-is |

### `<named-content>` and `<styled-content>`
- Appear frequently (gene names, species, etc.)
- Text preserved via fallback but `content-type` attribute is lost
- Could be useful for downstream NLP (e.g., identifying gene mentions)

### `<graphic>` outside `<fig>`
- Standalone graphics (inline images, equation images)
- Currently ignored entirely
- Fix: Extract `xlink:href` and create a Figure with no label

### `<media>` elements
- Video/audio references in articles
- Currently ignored
- Fix: Extract as supplementary material references

### `<subtitle>` in `<title-group>`
- Article subtitles are lost
- Fix: Append to title with separator (e.g., ": ")

### `<tfoot>` in tables
- Table footer rows are not parsed
- Fix: Extract `<tr>` from `<tfoot>` and add to table footnotes

### `<nlm-citation>` (older format)
- Pre-JATS citation format still found in older PMC articles
- `_find_citation()` only checks `element-citation` and `mixed-citation`
- Fix: Add `nlm-citation` to the search in `_find_citation()`

### Missing reference sub-elements
- `<comment>` (e.g., "In press", "Epub ahead of print")
- `<edition>` (book editions)
- `<date-in-citation>` (access dates for URLs)
- `<data-title>` (dataset titles)
- `<uri>` in citations (only `<ext-link>` is extracted)

---

## Priority 3: Low-Impact Gaps

### Front matter metadata
- `<history>` (received/accepted dates) -- not extracted
- `<copyright-statement>`, `<copyright-year>`, `<copyright-holder>` -- only license
  text is extracted
- `<license>` attributes (`license-type`, `xlink:href`) -- license URL not captured
- `<self-uri>` -- not extracted
- `<trans-title-group>`, `<trans-abstract>` -- translated content not extracted
- `<kwd-group>` attributes (`kwd-group-type`, `xml:lang`) -- not differentiated
- `<counts>` (`page-count`, `fig-count`, etc.) -- not extracted

### Inline elements (text preserved via fallback)
- `<email>` -- text preserved but not rendered as link
- `<uri>` -- text preserved but not rendered as link
- `<abbrev>` -- text preserved but expansion lost
- `<break/>` -- no output (line break lost)
- `<fn>` inline in paragraphs -- content preserved but not distinguished

### Table attributes
- `<td>/<th>` attributes: `align`, `valign`, `scope`, `headers` -- all ignored
- `<table>` attributes: `frame`, `rules` -- ignored
- `rowspan` detected but table structure not corrected

### Untested but handled elements
- `<boxed-text>` -- handler exists, no test
- `<floats-group>` -- handler exists, no test
- `<bio>` in back -- handler exists, no test

---

## Architecture Notes

1. **Safety net:** `all_text()` extracts text from ANY unrecognized element, so
   most inline content is preserved even without explicit handling. The main risk
   is with block-level elements in `<sec>` that get silently dropped.

2. **`_INLINE_FMT` dict:** Only 4 entries (italic, bold, sup, sub). Easy to extend.

3. **`_SEC_BLOCK_TAGS` gating:** Unknown block children of `<sec>` are silently
   dropped. Adding a fallback `else` clause to `_dispatch_sec_child` would prevent
   content loss.

4. **`_BLOCK_TAGS` for `<p>` splitting:** Elements like `<disp-formula>`,
   `<fig>`, `<table-wrap>` trigger paragraph splitting when found inside `<p>`.
   New block elements may need to be added here too.

---

## Recommended Quick Wins

1. Add `<monospace>` to `_INLINE_FMT` (1 line change)
2. Add `<collab>` handling in `_parse_authors` (~5 lines)
3. Add `<nlm-citation>` to `_find_citation` (1 line change)
4. Add fallback text extraction for unknown block elements in `_dispatch_sec_child`
5. Add `<subtitle>` extraction in `_parse_title`
6. Add `<tfoot>` parsing in `_parse_table_wrap`
7. Add tests for `<boxed-text>`, `<floats-group>`, `<bio>`
