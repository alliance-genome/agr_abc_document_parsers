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

## Next Steps

### Run on a larger random sample (200+ articles)
- Current 82-article cache has 100% pass rate
- A larger sample will surface rarer edge cases
- Consider adding interesting failures to the fixed article set

### JATS parser improvements (from NXML gap analysis)

**Quick wins:**
- Add `<monospace>` → `` `...` `` to `_INLINE_FMT` (1 line)
- Add `<collab>` group author handling in `_parse_authors`
- Add `<nlm-citation>` to `_find_citation()` for older articles
- Add fallback text extraction for unknown block elements in `_dispatch_sec_child`
- Add `<subtitle>` extraction in `_parse_title`
- Add `<tfoot>` parsing in `_parse_table_wrap`
- Add tests for `<boxed-text>`, `<floats-group>`, `<bio>`

**Medium effort:**
- Improve MathML / `<tex-math>` handling in formulas
- Handle `<graphic>` outside `<fig>` (standalone images)
- Handle `<fig-group>`, `<table-wrap-group>`, `<disp-formula-group>` containers
- Add `<sc>`, `<underline>`, `<strike>` inline formatting
- Extract missing reference sub-elements (comment, edition, uri, data-title)

**Full details:** See `docs/nxml-parser-gap-analysis.md`
