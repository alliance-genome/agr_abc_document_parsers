# Secondary Abstracts, Sub-Articles, and Metadata Enrichment

**Date:** 2026-03-12
**Status:** Approved
**Library:** agr-abc-document-parsers

## Problem

Comparison of our nXML-to-Markdown conversion against PMC's plain text files (6 real Alliance articles) revealed three content gaps in the JATS parser:

1. **Secondary abstracts** (Author Summary, eLife Digest, TOC summary) — stored as `<abstract abstract-type="...">` in nXML, currently only the main abstract is parsed.
2. **Sub-articles** (Decision letters, Author responses) — stored as `<sub-article>` elements, completely skipped. In the eLife sample, this accounted for ~40% of the article's word count.
3. **Article metadata** — subject categories from `<article-categories>` and CRediT author roles from `<role>` inside `<contrib>` are not extracted.

Body text coverage for the main article content is 94-99% for most journals, confirming the core parser is solid. These gaps are additive features.

## Design

### 1. Document Model Changes (`models.py`)

#### New dataclass: `SecondaryAbstract`

```python
@dataclass
class SecondaryAbstract:
    abstract_type: str = ""   # "summary", "executive-summary", "toc", etc.
    label: str = ""           # "Author Summary", "eLife Digest", etc.
    paragraphs: list[Paragraph] = field(default_factory=list)
```

Rationale: Separate from `Section` because secondary abstracts have `abstract_type` for semantic filtering and no subsections/figures/tables. Separate from the main `abstract` field because they serve different purposes (plain language vs technical).

#### New fields on `Author`

```python
@dataclass
class Author:
    # ... existing fields ...
    roles: list[str] = field(default_factory=list)  # CRediT roles
```

#### New fields on `Document`

```python
@dataclass
class Document:
    # ... existing fields ...
    secondary_abstracts: list[SecondaryAbstract] = field(default_factory=list)
    sub_articles: list[Document] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    article_type: str = ""  # e.g., "decision-letter", "reply", "editor-report"
```

- `sub_articles` is `list[Document]` — each sub-article is a full Document with its own title, authors, sections, references.
- `article_type` stores the JATS `article-type` attribute for sub-articles (e.g., `"decision-letter"`, `"reply"`). Empty for top-level articles. This avoids overloading `source_format`, which describes the file format (`"jats"`, `"tei"`), not content semantics.
- This is distinct from the existing `supplements` field, which represents separate uploaded files (supplementary methods, data files). Sub-articles are editorially embedded content (peer review, responses).

### 2. JATS Parser Changes (`jats_parser.py`)

#### New function: `_parse_secondary_abstracts(root) -> list[SecondaryAbstract]`

- Find all `<abstract>` elements in `<article-meta>` that have an `abstract-type` attribute.
- Known types and their labels:
  - `"summary"` -> `"Author Summary"`
  - `"executive-summary"` -> `"eLife Digest"`
  - `"toc"` -> `"Table of Contents Summary"`
  - `"plain-language-summary"` -> `"Plain Language Summary"`
  - Other types -> use the `abstract-type` value, title-cased, as the label.
- If the `<abstract>` element contains a `<title>` child, prefer its text as the label over the type-based mapping above.
- Parse paragraphs using existing `_parse_paragraph` machinery (supports structured sub-sections within the abstract).

#### New function: `_parse_sub_articles(root) -> list[Document]`

- Find all `<sub-article>` children of the root `<article>` element.
- For each sub-article:
  - It has the same general structure as a top-level article but uses `<front-stub>` instead of `<front>`. The `<front-stub>` contains a subset of `<article-meta>` fields.
  - Use a dedicated `_parse_sub_article(sub_el)` helper (not the top-level `parse_jats()`) that handles the structural differences:
    - `<front-stub>` does NOT contain `<article-meta>` — its children (title-group, contrib-group, etc.) are direct children of `<front-stub>`, not nested under article-meta. The helper must use XPaths like `front-stub/title-group/article-title` instead of `front/article-meta/title-group/article-title`.
    - Missing elements are expected: no journal-meta, possibly no abstract, no keywords.
  - Store the `article-type` attribute (e.g., `"decision-letter"`, `"reply"`, `"editor-report"`) in the new `Document.article_type` field.
  - Parse `<front-stub>` for: title (from `<title-group>/<article-title>`), contributors, and any other available metadata.

#### New function: `_parse_categories(root) -> list[str]`

- Extract from `<article-meta>/<article-categories>/<subj-group>/<subject>`.
- Flatten all subject groups into a single list (subjects from different `subj-group` elements are all included).

#### Modify `_parse_authors()`

- For each `<contrib>`, additionally look for `<role>` child elements.
- Populate `Author.roles` with the text content of each `<role>`.

#### Modify `_parse_abstract()`

- Current behavior: finds the first `<abstract>` in `<article-meta>`.
- New behavior: find the `<abstract>` element that has NO `abstract-type` attribute. If all abstracts have a type, use the first one **and exclude it from `_parse_secondary_abstracts`** to prevent the same abstract appearing in both `doc.abstract` and `doc.secondary_abstracts`. The secondary abstracts parser must accept the set of already-claimed abstract elements (or use a shared selection step).

#### Wire into `parse_jats()`

After existing parsing calls:
```python
doc.secondary_abstracts = _parse_secondary_abstracts(root)
doc.sub_articles = _parse_sub_articles(root)
doc.categories = _parse_categories(root)
```

### 3. Markdown Emitter Changes (`md_emitter.py`)

#### Emission order

1. Title (existing)
2. Metadata — journal, DOI, PMID, etc. (existing)
3. **Categories** — `**Categories:** Cell Biology, Genetics` (NEW, single line like keywords)
4. Authors (existing, unchanged)
5. Abstract (existing)
6. **Secondary abstracts** — each as `## {label}` section with paragraphs (NEW)
7. Keywords (existing)
8. Body sections (existing)
9. Doc-level figures/tables (existing)
10. Acknowledgments (existing)
11. Back matter (existing)
12. References (existing)
13. **Author role footnotes** — `[^N]: Name: Role1, Role2` (NEW, after references)
14. **Sub-articles** — each preceded by `---` separator (NEW, always last)

#### Secondary abstracts emission

```markdown
## Author Summary

The RAS-MAPK pathway plays a central role in...

## eLife Digest

In all higher organisms, life begins with a single cell...
```

#### Sub-articles emission

Each sub-article is rendered by a dedicated `_emit_sub_article()` helper (NOT `emit_markdown()`). This helper renders the sub-article's title as `##` (H2), its body sections at `###` (H3) and below, and its references as `###`. This avoids producing a second H1 title, which would violate the validator's single-H1 rule (S01).

Each sub-article is preceded by a horizontal rule separator:

```markdown
---

## Decision letter

Patricia J Wittkopp (Reviewing Editor), Justin Crocker (Reviewer)

{body paragraphs...}

---

## Author response

{body paragraphs...}

### References

{sub-article references, if any}
```

Sub-article references are emitted inline within their section, not merged into the main reference list.

#### Author roles emission

Emitted as footnotes at the end of the document, after references, before sub-articles:

```markdown
[^1]: Rachel Waymack: Conceptualization, Software, Formal analysis, Investigation
[^2]: Alvaro Fletcher: Conceptualization, Software, Formal analysis
```

Only emitted when at least one author has roles populated.

#### Categories emission

```markdown
**Categories:** Research Article, Chromosomes and Gene Expression
```

Single line, emitted after metadata block and before authors.

### 4. Markdown Reader Updates (`md_reader.py`)

Round-trip support for the new content:

- Detect `## Author Summary` / `## eLife Digest` / `## Plain Language Summary` headers between Abstract/Keywords and the first body section -> parse into `SecondaryAbstract` objects. Use known secondary abstract labels for detection, but also accept any `##` heading in that position that doesn't match a known body section pattern.
- Detect sub-articles using a delimiter-based algorithm: after the References section (and optional role footnotes), any `---` separator followed by `## {title}` starts a new sub-article. Each sub-article extends until the next `---` or end-of-document. This avoids hardcoding heading names like "Decision letter" or "Author response", making it robust against arbitrary sub-article types.
- Parse `**Categories:**` line into `Document.categories`.
- Parse author role footnotes (pattern: `[^N]: {name}: {roles}`) back into `Author.roles`.

### 5. Plain Text Module Updates (`plain_text.py`)

- `extract_plain_text()`: include secondary abstracts in output (they are valuable for search and NLP).
- `extract_plain_text()`: accept an `include_sub_articles: bool = False` parameter. Default excludes sub-articles (peer review content is noise for most text mining). When True, append sub-article text after main article text.

### 6. Validator (`md_validator.py`)

One existing rule needs updating:

- **S05** ("References is the last H2") — currently warns if any `##` heading appears after `## References`. Sub-articles will emit `## Decision letter`, `## Author response`, etc. after References. Update S05 to stop scanning at the first `---` separator, so that H2 headings within sub-articles don't trigger spurious warnings.

No new validation rules are needed beyond this S05 fix.

## Testing

### Test fixtures

- Add a synthetic JATS XML fixture with `<sub-article>` elements (modeled on eLife structure) to `tests/fixtures/`.
- Add inline XML constants in test files for focused unit tests.

### New tests in `test_jats_parser.py`

- `test_parse_secondary_abstracts` — Author Summary and eLife Digest extracted with correct type, label, paragraphs.
- `test_parse_main_abstract_excludes_secondary` — main abstract doesn't grab secondary ones.
- `test_parse_sub_articles` — Decision letter and Author response parsed as full Documents with own titles, authors, body.
- `test_parse_sub_article_front_stub` — graceful handling of `<front-stub>`.
- `test_parse_categories` — subject categories extracted.
- `test_parse_author_roles` — CRediT roles populated on Author.

### New tests in `test_md_emitter.py`

- `test_emit_secondary_abstracts` — correct positioning after main abstract, before keywords.
- `test_emit_sub_articles` — `---` separator, heading, authors, body, inline references.
- `test_emit_categories` — `**Categories:**` line in correct position.
- `test_emit_author_roles` — footnote format.

### New tests in `test_md_reader.py`

- Round-trip tests: emit -> read -> verify model equality for secondary abstracts, sub-articles, categories, roles.

### New tests in `test_plain_text.py`

- Secondary abstracts included in plain text output.
- Sub-articles excluded by default, included with `include_sub_articles=True`.

### Integration test

- Use a real nXML file (eLife PMC7556877 from our comparison sample) to verify the full pipeline: parse -> emit -> validate -> read round-trip. This fixture contains secondary abstracts (`executive-summary`, `toc`), sub-articles (`decision-letter`, `reply`), and `<custom-meta>` elements.

## Backwards Compatibility

All new fields have default empty values (`field(default_factory=list)`). Existing code that creates `Document`, `Author`, or calls `parse_jats()` / `emit_markdown()` will continue to work unchanged. The emitter only emits new sections when the fields are populated.

The Markdown output format is additive — existing documents without secondary abstracts or sub-articles produce identical output. The reader handles the new patterns but falls through gracefully when they're absent.

## Public API Changes

New exports from `__init__.py`:
- `SecondaryAbstract` dataclass

New fields on existing exports:
- `Document.article_type: str` — sub-article type identifier
- `Document.secondary_abstracts: list[SecondaryAbstract]`
- `Document.sub_articles: list[Document]`
- `Document.categories: list[str]`
- `Author.roles: list[str]`

No changes to existing function signatures.