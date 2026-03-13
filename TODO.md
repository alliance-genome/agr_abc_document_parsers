# PMC Parity — Remaining Work

Current status: **79/79** testable cached articles pass parity checks (16 fixed + 63 random).
3 articles SKIP (no PMC text on S3). Zero failures.

## Completed

All original 5 failures and 3 additional edge cases fixed:

1. **`<alt-text>` in `<fig>`** — Added `alt_text` field to Figure model
2. **`<attrib>` in `<fig>`** — Added `attrib` field to Figure model
3. **`<disp-formula>` paragraph splitting** — Rewrote `_collect_from_p` to split text at block boundaries
4. **`<bio>` in `<back>`** — Added bio element handling in `_parse_back_sections`
5. **Table footnotes as bare `<p>`** — Fixed `<table-wrap-foot>` to handle `<p>` fallback
6. **`<boxed-text>` at body level** — Added `_SEC_BLOCK_TAGS` dispatch in `_parse_body`
7. **Duplicate Funding heading** — Extract body "Funding" sections into `funding_statement`
8. **Nested lists** — `_parse_list` now flattens nested `<list>` children
9. **List-item labels** — Extract `<label>` from `<list-item>` (e.g., "1.", "a)")
10. **LaTeX-aware list text** — Skip `<tex-math>` formula content in list items, include non-LaTeX formulas
11. **TEI→Markdown parity test** — `tests/test_tei_conversion.py` validates TEI→MD content
    preservation using real articles from Alliance prod DB/S3. 50/50 pass on first run.
12. **PubMed NXML gap analysis** — Full analysis in `docs/nxml-parser-gap-analysis.md`

13. **JATS parser improvements (from gap analysis):**
    - `<monospace>` → `` `...` `` inline formatting
    - `<strike>` → `~~...~~` strikethrough formatting
    - `<underline>` → `<u>...</u>` formatting
    - `<subtitle>` extraction in `_parse_title`
    - `<collab>` group author handling at article level
    - `<nlm-citation>` support (older PMC articles)
    - `<fig-group>`, `<table-wrap-group>`, `<disp-formula-group>` container unpacking
    - Fallback text extraction for unknown block elements in `_dispatch_sec_child`
    - `<tfoot>` parsing in `_parse_table_wrap`
    - `<uri>` extraction in references
    - `<edition>` and `<comment>` fields in references
    - 37 new tests for all improvements + `<boxed-text>`, `<floats-group>`, `<bio>`

14. **JATS parser improvements (round 2):**
    - `<sc>`, `<overline>`, `<roman>` pass-through inline formatting (text preserved, nested formatting works)
    - `<graphic>` outside `<fig>` → standalone Figure (in `<sec>`, `<body>`, inside `<p>`)
    - `<media>` elements → descriptive paragraph with label and caption
    - Improved `<tex-math>` / MathML formula extraction (prefers LaTeX, handles `<alternatives>`, MathML `<annotation>`)
    - `<data-title>` fallback for reference titles (dataset citations)
    - 18 new tests for all improvements

15. **JATS parser improvements (round 3):**
    - `<named-content>` / `<styled-content>` recursive inline formatting (nested markup preserved)
    - `<break/>` emits newline in inline text
    - `<history>` dates: `received_date`, `accepted_date` fields on Document
    - `<copyright-statement>` → `Document.copyright`
    - `<license>` URL → `Document.license_url`
    - `<date-in-citation>` in references → appended to `comment` field
    - Refactored `_format_date` helper (shared by pub_date and history dates)
    - Fixed `_parse_paragraph` and `_collect_from_p` to recurse via `_inline_text`
      for unknown inline containers (was `all_text`, lost nested formatting)
    - 15 new tests for all improvements

16. **JATS parser improvements (round 4 — closing remaining gaps):**
    - `<self-uri>` → `Document.self_uri` field
    - `<trans-abstract>` → secondary abstracts with language-tagged type
    - `<kwd-group>` improvements: skip `abbreviations` type, handle `<compound-kwd>`
    - Table `rowspan` expansion: cells properly inserted into subsequent rows
    - Refactored `_parse_table_row` to return rowspan info + new `_expand_rowspans`
    - 13 new tests for all improvements

17. **JATS parser improvements (round 5 — final metadata and inline gaps):**
    - `<trans-title-group>` → `Document.trans_titles` with language tags, subtitle support
    - `<counts>` → `Document.counts` dict (fig-count, page-count, ref-count, etc.)
    - `<uri>` rendered as Markdown link `[text](href)` in paragraphs (both paths)
    - `<email>` explicitly handled in paragraph parsing (text preserved)
    - Translated titles emitted as italic lines in Markdown output
    - 17 new tests for all improvements

18. **JATS parser improvements (round 6 — cosmetic gaps):**
    - `<named-content>` / `<styled-content>` `content-type` → `Paragraph.named_content` annotations
    - New `NamedContent` dataclass for annotated text spans (text + content_type)
    - Table cell `align` attribute → `TableCell.align` field
    - Colspan padding cells inherit source cell alignment
    - GFM column alignment in Markdown emitter (`:---:`, `---:` separators)
    - 10 new tests for all improvements

## Next Steps

### Run on a larger random sample (200+ articles)
- Current 82-article cache has 100% pass rate
- A larger sample will surface rarer edge cases
- Consider adding interesting failures to the fixed article set

### All gap analysis items addressed
All elements from `docs/nxml-parser-gap-analysis.md` have been implemented.

**Full details:** See `docs/nxml-parser-gap-analysis.md`
