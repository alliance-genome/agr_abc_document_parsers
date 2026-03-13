"""Parse PMC nXML/JATS XML into the intermediate Document model."""
from __future__ import annotations

import logging
import re

from lxml import etree

from agr_abc_document_parsers.models import (
    Author,
    Document,
    Figure,
    Formula,
    FundingEntry,
    InlineRef,
    ListBlock,
    Paragraph,
    Reference,
    SecondaryAbstract,
    Section,
    Table,
    TableCell,
)
from agr_abc_document_parsers.xml_utils import (
    all_text,
    parse_xml,
    text,
)

logger = logging.getLogger(__name__)


def parse_jats(
    xml_content: bytes,
    root: etree._Element | None = None,
) -> Document:
    """Parse JATS/nXML content into a Document model.

    Handles both namespaced and non-namespaced JATS files.

    Args:
        xml_content: Raw bytes of a JATS XML file.
        root: Optional pre-parsed XML root element. When provided,
            *xml_content* is ignored and no re-parsing occurs.

    Returns:
        A populated Document dataclass.
    """
    if root is None:
        root = parse_xml(xml_content)
    doc = Document(source_format="jats")

    doc.title = _parse_title(root)
    doc.doi = _parse_doi(root)
    doc.keywords = _parse_keywords(root)

    main_abstract_elem = _find_main_abstract(root)
    doc.abstract = (
        _parse_abstract_content(main_abstract_elem)
        if main_abstract_elem is not None else []
    )
    doc.secondary_abstracts = _parse_secondary_abstracts(
        root, main_abstract_elem,
    )
    doc.categories = _parse_categories(root)

    # Article-level metadata
    _parse_article_meta(root, doc)

    # Parse affiliations first, then resolve into authors
    aff_map = _parse_affiliations(root)
    doc.authors = _parse_authors(root, aff_map)

    doc.sections = _parse_body(root)
    doc.references = _parse_bibliography(root)
    doc.acknowledgments = _parse_acknowledgments(root)

    # Dedicated back-matter fields (extracted BEFORE generic back_matter
    # to allow deduplication — see _parse_back_sections skip logic)
    doc.funding, doc.funding_statement = _parse_funding(root)
    doc.author_notes = _parse_author_notes_field(root)
    doc.competing_interests = _parse_competing_interests(root)
    doc.data_availability = _parse_data_availability(root)

    # Back matter: appendices + additional sections (fn-group, notes, etc.)
    # Elements already captured in dedicated fields above are skipped.
    back_matter = _parse_appendices(root)
    back_matter.extend(_parse_back_sections(root, doc))
    doc.back_matter = back_matter

    # Parse floats-group (figures/tables outside body, common in PMC nXML)
    _parse_floats_group(root, doc)

    # Sub-articles (decision letters, author responses, etc.)
    doc.sub_articles = _parse_sub_articles(root)

    return doc


def _parse_title(root: etree._Element) -> str:
    """Extract title from article-meta/title-group/article-title.

    Preserves inline formatting (italic, bold, sup, sub) as Markdown.
    """
    title_elem = root.find(".//article-meta/title-group/article-title")
    if title_elem is None:
        return ""
    return _inline_text(title_elem).strip()


def _parse_doi(root: etree._Element) -> str:
    """Extract DOI from article-id[@pub-id-type='doi']."""
    doi_elem = root.find(".//article-meta/article-id[@pub-id-type='doi']")
    return text(doi_elem)


def _parse_article_meta(root: etree._Element, doc: Document) -> None:
    """Extract article-level metadata: PMID, PMC ID, journal, dates, etc."""
    meta = root.find(".//article-meta")
    if meta is None:
        return

    # PMID
    pmid_el = meta.find("article-id[@pub-id-type='pmid']")
    if pmid_el is not None:
        doc.pmid = text(pmid_el)

    # PMC ID
    pmc_el = meta.find("article-id[@pub-id-type='pmc']")
    if pmc_el is not None:
        doc.pmcid = text(pmc_el)

    # Journal name
    journal_el = root.find(".//journal-meta/journal-title-group/journal-title")
    if journal_el is None:
        journal_el = root.find(".//journal-meta/journal-title")
    if journal_el is not None:
        doc.journal = text(journal_el)
    else:
        # Fallback: abbreviated journal name
        abbrev_el = root.find(
            ".//journal-meta/journal-id[@journal-id-type='nlm-ta']"
        )
        if abbrev_el is not None:
            doc.journal = text(abbrev_el)

    # Volume, issue, pages
    vol_el = meta.find("volume")
    if vol_el is not None:
        doc.volume = text(vol_el)
    issue_el = meta.find("issue")
    if issue_el is not None:
        doc.issue = text(issue_el)
    fpage = meta.find("fpage")
    lpage = meta.find("lpage")
    elocation = meta.find("elocation-id")
    if fpage is not None:
        fp = text(fpage)
        lp = text(lpage) if lpage is not None else ""
        doc.pages = f"{fp}-{lp}" if lp and lp != fp else fp
    elif elocation is not None:
        doc.pages = text(elocation)

    # Publication date (prefer epub, then collection, then ppub)
    pub_date = None
    for dtype in ["epub", "collection", "ppub"]:
        pub_date = meta.find(f"pub-date[@pub-type='{dtype}']")
        if pub_date is not None:
            break
    if pub_date is None:
        # Some JATS use date-type instead of pub-type
        for dtype in ["pub", "collection"]:
            pub_date = meta.find(f"pub-date[@date-type='{dtype}']")
            if pub_date is not None:
                break
    if pub_date is not None:
        year = text(pub_date.find("year"))
        month = text(pub_date.find("month"))
        day = text(pub_date.find("day"))
        if year:
            parts = [year]
            if month:
                parts.append(month.zfill(2))
                if day:
                    parts.append(day.zfill(2))
            doc.pub_date = "-".join(parts)

    # License
    license_el = meta.find(".//permissions/license/license-p")
    if license_el is not None:
        doc.license = all_text(license_el)


def _parse_keywords(root: etree._Element) -> list[str]:
    """Extract keywords from kwd-group/kwd."""
    keywords: list[str] = []
    for kwd in root.findall(".//article-meta/kwd-group/kwd"):
        kwd_text = all_text(kwd)
        if kwd_text:
            keywords.append(kwd_text)
    return keywords


def _find_main_abstract(
    root: etree._Element,
) -> etree._Element | None:
    """Find the main abstract element.

    Prefers the ``<abstract>`` with no ``abstract-type`` attribute.
    If all abstracts have a type, returns the first one.
    """
    for ab in root.findall(".//article-meta/abstract"):
        if ab.get("abstract-type") is None:
            return ab
    return root.find(".//article-meta/abstract")


def _parse_abstract_content(
    abstract_elem: etree._Element,
) -> list[Paragraph]:
    """Parse paragraphs from an ``<abstract>`` element."""
    paragraphs: list[Paragraph] = []

    # Check for structured abstract with <sec> children
    secs = abstract_elem.findall("sec")
    if secs:
        for sec in secs:
            title_elem = sec.find("title")
            sec_title = all_text(title_elem) if title_elem is not None else ""
            for p_elem in sec.findall("p"):
                para = _parse_paragraph(p_elem)
                if para.text and sec_title:
                    para.text = f"**{sec_title}:** {para.text}"
                if para.text:
                    paragraphs.append(para)
    else:
        for p_elem in abstract_elem.findall(".//p"):
            para = _parse_paragraph(p_elem)
            if para.text:
                paragraphs.append(para)

    return paragraphs


_SECONDARY_ABSTRACT_LABELS: dict[str, str] = {
    "summary": "Author Summary",
    "executive-summary": "eLife Digest",
    "toc": "Table of Contents Summary",
    "plain-language-summary": "Plain Language Summary",
}


def _parse_secondary_abstracts(
    root: etree._Element,
    main_abstract: etree._Element | None,
) -> list[SecondaryAbstract]:
    """Extract secondary abstracts (Author Summary, eLife Digest, etc.).

    Args:
        root: The XML root element.
        main_abstract: The element already claimed as the main abstract,
            to be excluded from secondary abstracts.
    """
    results: list[SecondaryAbstract] = []
    for ab in root.findall(".//article-meta/abstract"):
        if ab is main_abstract:
            continue
        ab_type = ab.get("abstract-type")
        if ab_type is None:
            continue
        # Determine label: prefer explicit <title>, then mapping, then title-case
        title_elem = ab.find("title")
        if title_elem is not None:
            label = all_text(title_elem)
        else:
            label = _SECONDARY_ABSTRACT_LABELS.get(
                ab_type, ab_type.replace("-", " ").title()
            )
        paragraphs = _parse_abstract_content(ab)
        results.append(SecondaryAbstract(
            abstract_type=ab_type,
            label=label,
            paragraphs=paragraphs,
        ))
    return results


def _parse_sub_articles(root: etree._Element) -> list[Document]:
    """Parse ``<sub-article>`` elements into Document objects."""
    results: list[Document] = []
    for sub_el in root.findall("sub-article"):
        results.append(_parse_sub_article(sub_el))
    return results


def _parse_sub_article(sub_el: etree._Element) -> Document:
    """Parse a single ``<sub-article>`` into a Document."""
    doc = Document(source_format="jats")
    doc.article_type = sub_el.get("article-type", "")

    # Front stub metadata
    front_stub = sub_el.find("front-stub")
    if front_stub is not None:
        title_el = front_stub.find("title-group/article-title")
        if title_el is not None:
            doc.title = _inline_text(title_el).strip()

        # Authors from front-stub/contrib-group
        aff_map: dict[str, str] = {}
        for aff_elem in front_stub.findall("aff"):
            aff_id = aff_elem.get("id", "")
            aff_text = all_text(aff_elem)
            if aff_id and aff_text:
                aff_map[aff_id] = aff_text
        for contrib in front_stub.findall(
            "contrib-group/contrib[@contrib-type='author']"
        ):
            author = Author()
            name_elem = contrib.find("name")
            if name_elem is not None:
                author.surname = text(name_elem.find("surname"))
                author.given_name = text(name_elem.find("given-names"))
            for role_el in contrib.findall("role"):
                role_text = all_text(role_el)
                if role_text:
                    author.roles.append(role_text)
            doc.authors.append(author)

        # Also parse editors and other contributors
        for contrib in front_stub.findall("contrib-group/contrib"):
            ctype = contrib.get("contrib-type", "")
            if ctype == "author":
                continue  # already handled
            name_elem = contrib.find("name")
            if name_elem is not None:
                author = Author()
                author.surname = text(name_elem.find("surname"))
                author.given_name = text(name_elem.find("given-names"))
                doc.authors.append(author)

    # Body
    doc.sections = _parse_body(sub_el)

    # References within sub-article
    doc.references = _parse_bibliography(sub_el)

    return doc


def _parse_categories(root: etree._Element) -> list[str]:
    """Extract subject categories from article-categories."""
    categories: list[str] = []
    for subj in root.findall(
        ".//article-meta/article-categories/subj-group/subject"
    ):
        subj_text = all_text(subj)
        if subj_text:
            categories.append(subj_text)
    return categories


_COI_FN_TYPES = frozenset({"conflict", "COI-statement"})


def _parse_funding(
    root: etree._Element,
) -> tuple[list[FundingEntry], str]:
    """Parse ``<funding-group>`` from article-meta.

    Returns (funding_entries, funding_statement).
    """
    entries: list[FundingEntry] = []
    statement = ""
    fg = root.find(".//article-meta/funding-group")
    if fg is None:
        return entries, statement
    for ag in fg.findall("award-group"):
        funder_elem = ag.find("funding-source")
        funder = all_text(funder_elem) if funder_elem is not None else ""
        award_ids: list[str] = []
        for aid in ag.findall("award-id"):
            aid_text = text(aid)
            if aid_text:
                award_ids.append(aid_text)
        if funder or award_ids:
            entries.append(FundingEntry(funder=funder, award_ids=award_ids))
    fs_elem = fg.find("funding-statement")
    if fs_elem is not None:
        statement = all_text(fs_elem)
    if not statement:
        fs_elem = root.find(".//article-meta/funding-statement")
        if fs_elem is not None:
            statement = all_text(fs_elem)
    return entries, statement


def _parse_author_notes_field(root: etree._Element) -> list[str]:
    """Parse ``<author-notes>`` from article-meta into flat strings.

    Skips COI footnotes (handled by ``_parse_competing_interests``).
    """
    notes: list[str] = []
    an = root.find(".//article-meta/author-notes")
    if an is None:
        return notes
    for child in an:
        tag = etree.QName(child.tag).localname if isinstance(
            child.tag, str
        ) else ""
        if tag == "corresp":
            t = all_text(child)
            if t:
                notes.append(t)
        elif tag == "fn":
            fn_type = child.get("fn-type", "")
            if fn_type in _COI_FN_TYPES:
                continue
            t = all_text(child)
            if t:
                notes.append(t)
    return notes


def _parse_competing_interests(root: etree._Element) -> str:
    """Extract competing-interest statements from author-notes and back."""
    parts: list[str] = []
    # From author-notes
    an = root.find(".//article-meta/author-notes")
    if an is not None:
        for fn in an.findall("fn"):
            if fn.get("fn-type", "") in _COI_FN_TYPES:
                fn_text = all_text(fn)
                if fn_text:
                    parts.append(fn_text)
    # From back/fn-group
    back = root.find("back")
    if back is None:
        back = root.find(".//back")
    if back is not None:
        for fg in back.findall("fn-group"):
            for fn in fg.findall("fn"):
                if fn.get("fn-type", "") in _COI_FN_TYPES:
                    fn_text = all_text(fn)
                    if fn_text:
                        parts.append(fn_text)
    return "\n\n".join(parts)


def _parse_data_availability(root: etree._Element) -> str:
    """Extract data-availability statement from back/notes or custom-meta."""
    parts: list[str] = []
    # From back/notes[@notes-type='data-availability']
    back = root.find("back")
    if back is None:
        back = root.find(".//back")
    if back is not None:
        for notes_elem in back.findall("notes"):
            if notes_elem.get("notes-type") == "data-availability":
                for p in notes_elem.findall(".//p"):
                    p_text = all_text(p)
                    if p_text:
                        parts.append(p_text)
    # From custom-meta-group
    if not parts:
        for cm in root.findall(
            ".//article-meta/custom-meta-group/custom-meta"
        ):
            meta_name = cm.find("meta-name")
            meta_value = cm.find("meta-value")
            if meta_name is not None and meta_value is not None:
                name_text = all_text(meta_name)
                if name_text and "data availability" in name_text.lower():
                    val_text = all_text(meta_value)
                    if val_text:
                        parts.append(val_text)
    return "\n\n".join(parts)


def _parse_affiliations(root: etree._Element) -> dict[str, str]:
    """Build a map of aff id -> affiliation text."""
    aff_map: dict[str, str] = {}
    for aff_elem in root.findall(".//article-meta/aff"):
        aff_id = aff_elem.get("id", "")
        aff_text = all_text(aff_elem)
        if aff_id and aff_text:
            aff_map[aff_id] = aff_text
    return aff_map


def _parse_authors(root: etree._Element, aff_map: dict[str, str]) -> list[Author]:
    """Extract authors from contrib-group, resolving affiliations via xref."""
    authors = []
    for contrib in root.findall(
        ".//article-meta/contrib-group/contrib[@contrib-type='author']"
    ):
        author = Author()
        name_elem = contrib.find("name")
        if name_elem is not None:
            author.surname = text(name_elem.find("surname"))
            author.given_name = text(name_elem.find("given-names"))

        email_elem = contrib.find("email")
        if email_elem is not None:
            author.email = text(email_elem)

        # ORCID — try contrib-id first, then uri
        orcid_elem = contrib.find(
            "contrib-id[@contrib-id-type='orcid']"
        )
        if orcid_elem is not None:
            author.orcid = text(orcid_elem)

        # Resolve affiliations via xref
        for xref in contrib.findall("xref[@ref-type='aff']"):
            rid = xref.get("rid", "")
            if rid in aff_map:
                author.affiliations.append(aff_map[rid])

        # CRediT roles from <role> elements
        for role_el in contrib.findall("role"):
            role_text = all_text(role_el)
            if role_text:
                author.roles.append(role_text)

        authors.append(author)
    return authors


def _parse_body(root: etree._Element) -> list[Section]:
    """Parse body content from <body>.

    Handles both <sec>-structured bodies and bare elements (<p>, <fig>,
    <table-wrap>) that appear as direct children of <body>.
    """
    sections: list[Section] = []
    body = root.find(".//body")
    if body is None:
        return sections

    # Collect bare (non-sec) elements before the first <sec> into a
    # preamble section, and handle any bare elements between sections.
    preamble = Section(level=1)

    for child in body:
        tag = etree.QName(child.tag).localname if isinstance(
            child.tag, str
        ) else ""

        if tag == "sec":
            # Flush any accumulated preamble content
            if (preamble.paragraphs or preamble.figures
                    or preamble.tables or preamble.lists
                    or preamble.formulas):
                sections.append(preamble)
                preamble = Section(level=1)
            sections.append(_parse_sec(child, level=1))
        elif tag == "p":
            _collect_from_p(child, preamble)
        elif tag == "fig":
            preamble.figures.append(_parse_fig(child))
        elif tag == "table-wrap":
            preamble.tables.append(_parse_table_wrap(child))
        elif tag == "disp-formula":
            preamble.formulas.append(_parse_formula(child))
        elif tag == "list":
            preamble.lists.append(_parse_list(child))

    # Flush trailing preamble
    if (preamble.paragraphs or preamble.figures
            or preamble.tables or preamble.lists
            or preamble.formulas):
        sections.append(preamble)

    return sections


_BLOCK_TAGS = frozenset({"fig", "table-wrap", "disp-formula", "list"})


def _dispatch_sec_block(
    child: etree._Element, tag: str, section: Section,
) -> None:
    """Handle supplementary, boxed-text, quote, def-list, etc."""
    if tag == "supplementary-material":
        _parse_supplementary(child, section)
    elif tag == "boxed-text":
        _parse_boxed_text(child, section)
    elif tag == "disp-quote":
        p_elems = child.findall("p")
        if p_elems:
            lines = [f"> {all_text(p)}" for p in p_elems
                     if all_text(p)]
            if lines:
                section.paragraphs.append(
                    Paragraph(text="\n".join(lines))
                )
        else:
            quote_text = all_text(child)
            if quote_text:
                section.paragraphs.append(
                    Paragraph(text=f"> {quote_text}")
                )
    elif tag == "def-list":
        _parse_def_list(child, section)
    elif tag == "fn-group":
        for fn in child.findall("fn"):
            fn_text = all_text(fn)
            if fn_text:
                section.notes.append(fn_text)
    elif tag == "preformat":
        pre_text = all_text(child)
        if pre_text:
            ticks = re.findall(r"`+", pre_text)
            max_ticks = max((len(t) for t in ticks), default=2)
            fence = "`" * max(3, max_ticks + 1)
            section.paragraphs.append(
                Paragraph(text=f"{fence}\n{pre_text}\n{fence}")
            )
    elif tag == "glossary":
        _parse_glossary(child, section, emit_title=True)


_SEC_BLOCK_TAGS = frozenset({
    "supplementary-material", "boxed-text", "disp-quote",
    "def-list", "fn-group", "preformat", "glossary",
})


def _dispatch_sec_child(
    child: etree._Element, tag: str,
    section: Section, level: int,
) -> None:
    """Handle a single child element of a <sec>."""
    if tag in ("title", "label"):
        return
    elif tag == "p":
        _collect_from_p(child, section)
    elif tag == "sec":
        section.subsections.append(_parse_sec(child, level + 1))
    elif tag == "fig":
        section.figures.append(_parse_fig(child))
    elif tag == "table-wrap":
        section.tables.append(_parse_table_wrap(child))
    elif tag == "disp-formula":
        section.formulas.append(_parse_formula(child))
    elif tag == "list":
        section.lists.append(_parse_list(child))
    elif tag in _SEC_BLOCK_TAGS:
        _dispatch_sec_block(child, tag, section)


def _parse_sec(sec_elem: etree._Element, level: int) -> Section:
    """Recursively parse a <sec> element into a Section."""
    section = Section(level=level)

    title_elem = sec_elem.find("title")
    if title_elem is not None:
        section.heading = all_text(title_elem)

    for child in sec_elem:
        tag = etree.QName(child.tag).localname if isinstance(
            child.tag, str
        ) else ""
        _dispatch_sec_child(child, tag, section, level)

    return section


def _collect_from_p(p_elem: etree._Element, section: Section) -> None:
    """Parse a <p> element, extracting any embedded block elements.

    JATS allows block-level elements (<table-wrap>, <fig>, <disp-formula>,
    <list>) to be nested inside <p>.  When that happens the paragraph text
    before/after the block element is emitted as separate paragraphs, and
    the block element is added to the appropriate section list.
    """
    child_tags = {
        etree.QName(c.tag).localname
        for c in p_elem
        if isinstance(c.tag, str)
    }
    if not child_tags & _BLOCK_TAGS:
        # Fast path — no embedded blocks, just parse normally
        section.paragraphs.append(_parse_paragraph(p_elem))
        return

    # Slow path — split around embedded block elements
    for child in p_elem:
        tag = etree.QName(child.tag).localname if isinstance(
            child.tag, str
        ) else ""
        if tag == "fig":
            section.figures.append(_parse_fig(child))
        elif tag == "table-wrap":
            section.tables.append(_parse_table_wrap(child))
        elif tag == "disp-formula":
            section.formulas.append(_parse_formula(child))
        elif tag == "list":
            section.lists.append(_parse_list(child))

    # Emit the paragraph text (with block elements excluded)
    para = _parse_paragraph(p_elem, skip_tags=_BLOCK_TAGS)
    if para.text:
        section.paragraphs.append(para)


_INLINE_FMT: dict[str, tuple[str, str]] = {
    "italic": ("*", "*"),
    "bold": ("**", "**"),
    "sup": ("<sup>", "</sup>"),
    "sub": ("<sub>", "</sub>"),
}


def _inline_text(elem: etree._Element) -> str:
    """Recursively format inline content, preserving nested markup."""
    parts: list[str] = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        tag = etree.QName(child.tag).localname if isinstance(
            child.tag, str
        ) else ""
        if tag in _INLINE_FMT:
            inner = _inline_text(child)
            if inner:
                pre, suf = _INLINE_FMT[tag]
                parts.append(f"{pre}{inner}{suf}")
        else:
            parts.append(all_text(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def _parse_paragraph(
    p_elem: etree._Element,
    skip_tags: frozenset[str] | None = None,
) -> Paragraph:
    """Parse a <p> element with mixed content, extracting inline refs.

    Args:
        p_elem: The ``<p>`` XML element.
        skip_tags: Optional set of child tag localnames to skip (used when
            block elements like ``<table-wrap>`` are extracted separately).
    """
    parts: list[str] = []
    refs: list[InlineRef] = []

    if p_elem.text:
        parts.append(p_elem.text)

    for child in p_elem:
        tag = etree.QName(child.tag).localname if isinstance(
            child.tag, str
        ) else ""

        if skip_tags and tag in skip_tags:
            # Still collect the tail text after the skipped element
            if child.tail:
                parts.append(child.tail)
            continue

        if tag == "xref":
            ref_text = all_text(child)
            rid = child.get("rid", "")
            if ref_text:
                refs.append(InlineRef(text=ref_text, target=rid))
                parts.append(ref_text)
        elif tag == "ext-link":
            link_text = all_text(child)
            href = child.get(
                "{http://www.w3.org/1999/xlink}href", ""
            )
            if not href:
                href = child.get("href", "")
            if link_text and href and link_text != href:
                parts.append(f"[{link_text}]({href})")
            elif href:
                parts.append(href)
            elif link_text:
                parts.append(link_text)
        elif tag in _INLINE_FMT:
            inner = _inline_text(child)
            if inner:
                pre, suf = _INLINE_FMT[tag]
                parts.append(f"{pre}{inner}{suf}")
        else:
            parts.append(all_text(child))

        if child.tail:
            parts.append(child.tail)

    # Collapse XML-indentation whitespace (newlines + spaces) into
    # single spaces so parsed paragraphs read cleanly.
    para_text = re.sub(r"\s+", " ", "".join(parts)).strip()
    return Paragraph(text=para_text, refs=refs)


def _parse_fig(fig_elem: etree._Element) -> Figure:
    """Parse a <fig> element."""
    fig = Figure()

    label_elem = fig_elem.find("label")
    if label_elem is not None:
        fig.label = all_text(label_elem)

    caption_elem = fig_elem.find("caption")
    if caption_elem is not None:
        # Caption may have <title> and/or <p>
        parts = []
        title = caption_elem.find("title")
        if title is not None:
            parts.append(_inline_text(title).strip())
        for p in caption_elem.findall("p"):
            parts.append(_inline_text(p).strip())
        fig.caption = " ".join(p for p in parts if p)

    graphic_elem = fig_elem.find("graphic")
    if graphic_elem is not None:
        # xlink:href attribute — try with and without namespace
        href = graphic_elem.get(
            "{http://www.w3.org/1999/xlink}href", ""
        )
        if not href:
            href = graphic_elem.get("href", "")
        fig.graphic_url = href

    return fig


def _parse_table_wrap(tw_elem: etree._Element) -> Table:
    """Parse a <table-wrap> element."""
    table = Table()

    label_elem = tw_elem.find("label")
    if label_elem is not None:
        table.label = all_text(label_elem)

    caption_elem = tw_elem.find("caption")
    if caption_elem is not None:
        parts = []
        title = caption_elem.find("title")
        if title is not None:
            parts.append(_inline_text(title).strip())
        for p in caption_elem.findall("p"):
            parts.append(_inline_text(p).strip())
        table.caption = " ".join(p for p in parts if p)

    table_elem = tw_elem.find("table")
    if table_elem is not None:
        # Parse thead
        thead = table_elem.find("thead")
        if thead is not None:
            for tr in thead.findall("tr"):
                row = _parse_table_row(tr, is_header=True)
                if row:
                    table.rows.append(row)

        # Parse tbody
        tbody = table_elem.find("tbody")
        if tbody is not None:
            for tr in tbody.findall("tr"):
                row = _parse_table_row(tr, is_header=False)
                if row:
                    table.rows.append(row)

        # Direct tr elements (no thead/tbody)
        if thead is None and tbody is None:
            for tr in table_elem.findall("tr"):
                row = _parse_table_row(tr, is_header=False)
                if row:
                    table.rows.append(row)

    # Table footnotes from <table-wrap-foot>
    foot = tw_elem.find("table-wrap-foot")
    if foot is not None:
        for fn in foot.findall(".//fn"):
            fn_text = all_text(fn)
            if fn_text:
                table.foot_notes.append(fn_text)

    return table


def _parse_table_row(tr_elem: etree._Element, is_header: bool) -> list[TableCell]:
    """Parse a <tr> element into a list of TableCells.

    Handles colspan by emitting empty padding cells so GFM tables
    stay aligned.
    """
    cells = []
    for child in tr_elem:
        tag = etree.QName(child.tag).localname if isinstance(
            child.tag, str
        ) else ""
        if tag in ("th", "td"):
            rowspan_val = child.get("rowspan", "1") or "1"
            if rowspan_val != "1":
                logger.warning(
                    "rowspan=%s on <%s> not supported; table may "
                    "be misaligned in Markdown output",
                    rowspan_val, tag,
                )
            try:
                colspan = min(int(child.get("colspan", "1") or "1"), 50)
            except (ValueError, OverflowError):
                colspan = 1
            cell = TableCell(
                text=all_text(child),
                is_header=(tag == "th" or is_header),
            )
            cells.append(cell)
            for _ in range(colspan - 1):
                cells.append(TableCell(
                    text="",
                    is_header=(tag == "th" or is_header),
                ))
    return cells


def _parse_formula(formula_elem: etree._Element) -> Formula:
    """Parse a <disp-formula> element."""
    label_elem = formula_elem.find("label")
    label = all_text(label_elem)

    formula_text = all_text(formula_elem)
    # Remove label from text — may appear at start or end
    if label:
        if formula_text.endswith(label):
            formula_text = formula_text[:-len(label)].strip()
        elif formula_text.startswith(label):
            formula_text = formula_text[len(label):].strip()

    return Formula(text=formula_text, label=label)


def _parse_list(list_elem: etree._Element) -> ListBlock:
    """Parse a <list> element."""
    list_type = list_elem.get("list-type", "")
    ordered = list_type in ("order", "ordered", "number")

    items: list[str] = []
    for item_elem in list_elem.findall("list-item"):
        # list-item typically contains <p>
        p = item_elem.find("p")
        if p is not None:
            item_text = all_text(p)
        else:
            item_text = all_text(item_elem)
        if item_text:
            items.append(item_text)

    return ListBlock(items=items, ordered=ordered)


def _parse_supplementary(elem: etree._Element, section: Section) -> None:
    """Parse <supplementary-material> into a paragraph."""
    label_elem = elem.find("label")
    label = all_text(label_elem)
    caption = elem.find("caption")
    caption_text = ""
    if caption is not None:
        parts = []
        title = caption.find("title")
        if title is not None:
            parts.append(all_text(title))
        for p in caption.findall("p"):
            parts.append(all_text(p))
        caption_text = " ".join(parts)

    if label and caption_text:
        section.paragraphs.append(
            Paragraph(text=f"**{label}.** {caption_text}")
        )
    elif label:
        section.paragraphs.append(Paragraph(text=f"**{label}.**"))
    elif caption_text:
        section.paragraphs.append(Paragraph(text=caption_text))


def _parse_boxed_text(elem: etree._Element, section: Section) -> None:
    """Parse <boxed-text> — emit its content as regular paragraphs."""
    title_elem = elem.find("title")
    if title_elem is not None:
        title_text = all_text(title_elem)
        if title_text:
            section.paragraphs.append(
                Paragraph(text=f"**{title_text}**")
            )
    for p in elem.findall(".//p"):
        p_text = all_text(p)
        if p_text:
            section.paragraphs.append(Paragraph(text=p_text))


def _parse_def_list(elem: etree._Element, section: Section) -> None:
    """Parse <def-list> into a list block."""
    items: list[str] = []
    for def_item in elem.findall("def-item"):
        term_elem = def_item.find("term")
        def_elem = def_item.find("def")
        term = all_text(term_elem) if term_elem is not None else ""
        defn = all_text(def_elem) if def_elem is not None else ""
        if term and defn:
            items.append(f"**{term}**: {defn}")
        elif term:
            items.append(f"**{term}**")
        elif defn:
            items.append(defn)
    if items:
        section.lists.append(ListBlock(items=items, ordered=False))


def _parse_glossary(
    elem: etree._Element, section: Section,
    emit_title: bool = False,
) -> None:
    """Parse <glossary> — def-list or paragraphs.

    Args:
        elem: The ``<glossary>`` XML element.
        section: Target section to populate.
        emit_title: If True, emit the ``<title>`` as a bold paragraph.
            Set to True when the glossary is inline (e.g. inside a
            ``<sec>``); False when the caller already uses the title
            as the section heading.
    """
    if emit_title:
        title_elem = elem.find("title")
        if title_elem is not None:
            title_text = all_text(title_elem)
            if title_text:
                section.paragraphs.append(
                    Paragraph(text=f"**{title_text}**")
                )
    for dl in elem.findall("def-list"):
        _parse_def_list(dl, section)
    for p in elem.findall("p"):
        p_text = all_text(p)
        if p_text:
            section.paragraphs.append(Paragraph(text=p_text))


def _parse_acknowledgments(root: etree._Element) -> str:
    """Extract acknowledgments from back/ack."""
    back = root.find("back")
    if back is None:
        back = root.find(".//back")
    ack = back.find("ack") if back is not None else None
    if ack is None:
        return ""

    parts: list[str] = []
    for p in ack.findall(".//p"):
        p_text = all_text(p)
        if p_text:
            parts.append(p_text)
    return "\n\n".join(parts)


def _parse_appendices(root: etree._Element) -> list[Section]:
    """Extract appendices from back/app-group."""
    sections: list[Section] = []
    back = root.find("back")
    if back is None:
        back = root.find(".//back")
    app_group = back.find("app-group") if back is not None else None
    if app_group is None:
        return sections

    for app in app_group.findall("app"):
        section = Section(level=1)
        title_elem = app.find("title")
        if title_elem is not None:
            section.heading = all_text(title_elem)
        # Parse sub-sections within appendix
        for sec in app.findall("sec"):
            section.subsections.append(_parse_sec(sec, level=2))
        for p in app.findall("p"):
            section.paragraphs.append(_parse_paragraph(p))
        for tw in app.findall("table-wrap"):
            section.tables.append(_parse_table_wrap(tw))
        for fig in app.findall("fig"):
            section.figures.append(_parse_fig(fig))
        for supp in app.findall("supplementary-material"):
            _parse_supplementary(supp, section)
        for fn_grp in app.findall("fn-group"):
            for fn in fn_grp.findall("fn"):
                fn_text = all_text(fn)
                if fn_text:
                    section.notes.append(fn_text)
        sections.append(section)

    # Also handle standalone <app> directly under <back> (without app-group)
    if back is not None:
        for app in back.findall("app"):
            section = Section(level=1)
            title_elem = app.find("title")
            if title_elem is not None:
                section.heading = all_text(title_elem)
            for sec in app.findall("sec"):
                section.subsections.append(_parse_sec(sec, level=2))
            for p in app.findall("p"):
                section.paragraphs.append(_parse_paragraph(p))
            for tw in app.findall("table-wrap"):
                section.tables.append(_parse_table_wrap(tw))
            for fig in app.findall("fig"):
                section.figures.append(_parse_fig(fig))
            for supp in app.findall("supplementary-material"):
                _parse_supplementary(supp, section)
            if (section.heading or section.paragraphs or section.tables
                    or section.figures or section.subsections):
                sections.append(section)

    return sections


def _parse_back_sections(
    root: etree._Element,
    doc: Document | None = None,
) -> list[Section]:
    """Extract additional back-matter sections (fn-group, notes, sec).

    These appear as direct children of <back> alongside <ack>,
    <ref-list>, and <app-group>.  They include footnotes, author
    contributions, data-availability statements, COI disclosures, etc.

    Elements that have already been captured into dedicated Document
    fields (competing interests, data availability) are skipped to
    avoid content duplication.
    """
    sections: list[Section] = []
    back = root.find("back")
    if back is None:
        back = root.find(".//back")
    if back is None:
        return sections

    for child in back:
        tag = etree.QName(child.tag).localname if isinstance(
            child.tag, str
        ) else ""

        if tag == "sec":
            sections.append(_parse_sec(child, level=1))
        elif tag == "fn-group":
            section = Section(level=1)
            title_elem = child.find("title")
            if title_elem is not None:
                section.heading = all_text(title_elem)
            for fn in child.findall("fn"):
                # Skip COI footnotes already captured in doc.competing_interests
                fn_type = fn.get("fn-type", "")
                if fn_type in _COI_FN_TYPES:
                    continue
                fn_text = all_text(fn)
                if fn_text:
                    section.notes.append(fn_text)
            if section.notes or section.heading:
                sections.append(section)
        elif tag == "notes":
            # Skip data-availability notes already captured
            if child.get("notes-type") == "data-availability":
                continue
            section = Section(level=1)
            title_elem = child.find("title")
            if title_elem is not None:
                section.heading = all_text(title_elem)
            for p in child.findall(".//p"):
                p_text = all_text(p)
                if p_text:
                    section.paragraphs.append(Paragraph(text=p_text))
            if section.paragraphs or section.heading:
                sections.append(section)
        elif tag == "supplementary-material":
            section = Section(level=1)
            _parse_supplementary(child, section)
            if section.paragraphs:
                sections.append(section)
        elif tag == "glossary":
            section = Section(level=1)
            title_elem = child.find("title")
            if title_elem is not None:
                section.heading = all_text(title_elem)
            else:
                section.heading = "Glossary"
            _parse_glossary(child, section)
            if (section.paragraphs or section.lists
                    or section.heading):
                sections.append(section)

    return sections


def _parse_floats_group(root: etree._Element, doc: Document) -> None:
    """Parse <floats-group> for figures and tables outside body/back.

    In many PMC nXML files, figures and tables are placed in a
    <floats-group> element that is a direct child of <article>,
    separate from <body> and <back>.
    """
    floats = root.find(".//floats-group")
    if floats is None:
        return

    for child in floats:
        tag = etree.QName(child.tag).localname if isinstance(
            child.tag, str
        ) else ""

        if tag == "fig":
            doc.figures.append(_parse_fig(child))
        elif tag == "table-wrap":
            doc.tables.append(_parse_table_wrap(child))


def _parse_bibliography(root: etree._Element) -> list[Reference]:
    """Extract references from back/ref-list/ref.

    Uses the direct ``<back>`` child to avoid picking up references
    from nested ``<sub-article>`` elements.
    """
    back = root.find("back")
    if back is None:
        # Fallback for non-standard structure
        back = root.find(".//back")
    if back is None:
        return []
    references = []
    for idx, ref_elem in enumerate(back.findall("ref-list/ref")):
        ref = _parse_ref(ref_elem, idx + 1)
        references.append(ref)
    return references


def _find_citation(ref_elem: etree._Element) -> etree._Element | None:
    """Locate the citation element within a <ref>.

    Checks direct children and ``<citation-alternatives>`` wrapper.
    """
    for tag in ("element-citation", "mixed-citation"):
        elem = ref_elem.find(tag)
        if elem is not None:
            return elem
        elem = ref_elem.find(f"citation-alternatives/{tag}")
        if elem is not None:
            return elem
    return None


def _parse_ref_authors(
    citation: etree._Element, ref: Reference,
) -> None:
    """Extract authors from a citation element into *ref*."""
    # Try person-group with type="author" first, then untyped groups,
    # then direct name children.
    author_names: list[etree._Element] = []
    for pg in citation.findall(".//person-group"):
        pg_type = pg.get("person-group-type", "")
        if pg_type and pg_type != "author":
            continue
        author_names.extend(pg.findall("name"))
    if not author_names:
        author_names = citation.findall("name")
    for name_elem in author_names:
        surname = text(name_elem.find("surname"))
        given = text(name_elem.find("given-names"))
        if surname:
            name = f"{surname} {given}" if given else surname
            ref.authors.append(name)

    # Fall back to string-name (alternate format in some nXML)
    if not ref.authors:
        for sn in citation.findall(".//string-name"):
            surname = text(sn.find("surname"))
            given = text(sn.find("given-names"))
            if surname:
                name = f"{surname} {given}" if given else surname
                ref.authors.append(name)
            else:
                sn_text = all_text(sn)
                if sn_text:
                    ref.authors.append(sn_text)

    # Group/collaborative authors
    for collab_elem in citation.findall(".//collab"):
        collab_text = all_text(collab_elem)
        if collab_text:
            ref.authors.append(collab_text)


def _parse_ref_editors(
    citation: etree._Element, ref: Reference,
) -> None:
    """Extract editors from a citation element into *ref*."""
    editor_group = citation.find(
        "person-group[@person-group-type='editor']"
    )
    if editor_group is None:
        return
    for name_elem in editor_group.findall("name"):
        surname = text(name_elem.find("surname"))
        given = text(name_elem.find("given-names"))
        if surname:
            name = f"{surname} {given}" if given else surname
            ref.editors.append(name)


def _parse_ref_pages(
    citation: etree._Element, ref: Reference,
) -> None:
    """Extract page range or elocation-id from a citation."""
    fpage = citation.find("fpage")
    lpage = citation.find("lpage")
    if fpage is not None:
        fpage_text = text(fpage)
        lpage_text = text(lpage) if lpage is not None else ""
        if fpage_text and lpage_text:
            ref.pages = f"{fpage_text}-{lpage_text}"
        elif fpage_text:
            ref.pages = fpage_text
    if not ref.pages:
        page_range = citation.find("page-range")
        if page_range is not None:
            ref.pages = text(page_range)
    if not ref.pages:
        eloc = citation.find("elocation-id")
        if eloc is not None:
            ref.pages = text(eloc)


def _parse_ref_ids(
    citation: etree._Element, ref: Reference,
) -> None:
    """Extract identifiers and external links from a citation."""
    for pub_id_type, attr in (
        ("doi", "doi"), ("pmid", "pmid"), ("pmcid", "pmcid"),
    ):
        elem = citation.find(f"pub-id[@pub-id-type='{pub_id_type}']")
        if elem is not None:
            setattr(ref, attr, text(elem))

    for ext_link in citation.findall("ext-link"):
        href = ext_link.get(
            "{http://www.w3.org/1999/xlink}href", ""
        )
        if not href:
            href = ext_link.get("href", "")
        if href:
            ref.ext_links.append(href)


def _parse_ref(ref_elem: etree._Element, index: int) -> Reference:
    """Parse a single <ref> element.

    Supports both <element-citation> and <mixed-citation>,
    including ``<citation-alternatives>`` wrappers.
    """
    ref = Reference(index=index)

    citation = _find_citation(ref_elem)
    if citation is None:
        return ref

    _parse_ref_authors(citation, ref)

    # Title
    title_elem = citation.find("article-title")
    if title_elem is not None:
        ref.title = all_text(title_elem)

    # Journal / Source
    source_elem = citation.find("source")
    if source_elem is not None:
        ref.journal = all_text(source_elem)

    # Chapter / part title (book chapters)
    part_title = citation.find("chapter-title")
    if part_title is None:
        part_title = citation.find("part-title")
    if part_title is not None:
        ref.chapter_title = all_text(part_title)

    # Simple text fields
    for tag, attr in (("year", "year"), ("volume", "volume"),
                      ("issue", "issue")):
        elem = citation.find(tag)
        if elem is not None:
            setattr(ref, attr, text(elem))

    # Publisher info
    pub_name = citation.find("publisher-name")
    if pub_name is not None:
        ref.publisher = all_text(pub_name)
    pub_loc = citation.find("publisher-loc")
    if pub_loc is not None:
        ref.publisher_loc = all_text(pub_loc)

    # Conference name
    conf = citation.find("conf-name")
    if conf is not None:
        ref.conference = all_text(conf)

    # Editors
    _parse_ref_editors(citation, ref)

    _parse_ref_pages(citation, ref)
    _parse_ref_ids(citation, ref)

    return ref
