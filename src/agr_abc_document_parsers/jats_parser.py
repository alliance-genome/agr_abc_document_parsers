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
    NamedContent,
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
    doc.trans_titles = _parse_trans_titles(root)
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
    ack_sections: list[Section] = []
    doc.acknowledgments = _parse_acknowledgments(root, ack_sections)

    # Dedicated back-matter fields (extracted BEFORE generic back_matter
    # to allow deduplication — see _parse_back_sections skip logic)
    doc.funding, doc.funding_statement = _parse_funding(root)
    _extract_funding_body_sections(doc)
    doc.author_notes = _parse_author_notes_field(root)
    doc.competing_interests = _parse_competing_interests(root)
    doc.data_availability = _parse_data_availability(root)

    # Back matter: appendices + ack sub-sections + additional sections.
    # Elements already captured in dedicated fields above are skipped.
    back_matter = _parse_appendices(root)
    back_matter.extend(ack_sections)
    back_matter.extend(_parse_back_sections(root, doc))
    doc.back_matter = back_matter

    # Parse floats-group (figures/tables outside body, common in PMC nXML)
    _parse_floats_group(root, doc)

    # Sub-articles (decision letters, author responses, etc.)
    doc.sub_articles = _parse_sub_articles(root)

    return doc


def _parse_title(root: etree._Element) -> str:
    """Extract title from article-meta/title-group/article-title.

    Includes subtitle (if present) separated by ": ".
    Preserves inline formatting (italic, bold, sup, sub) as Markdown.
    """
    title_group = root.find(".//article-meta/title-group")
    if title_group is None:
        return ""
    title_elem = title_group.find("article-title")
    if title_elem is None:
        return ""
    title = _inline_text(title_elem).strip()
    subtitle_elem = title_group.find("subtitle")
    if subtitle_elem is not None:
        subtitle = _inline_text(subtitle_elem).strip()
        if subtitle:
            title = f"{title}: {subtitle}"
    return title


def _parse_trans_titles(root: etree._Element) -> list[str]:
    """Extract translated titles from title-group/trans-title-group."""
    titles: list[str] = []
    title_group = root.find(".//article-meta/title-group")
    if title_group is None:
        return titles
    for ttg in title_group.findall("trans-title-group"):
        lang = ttg.get("{http://www.w3.org/XML/1998/namespace}lang", "")
        title_elem = ttg.find("trans-title")
        if title_elem is None:
            continue
        title = _inline_text(title_elem).strip()
        subtitle_elem = ttg.find("trans-subtitle")
        if subtitle_elem is not None:
            subtitle = _inline_text(subtitle_elem).strip()
            if subtitle:
                title = f"{title}: {subtitle}"
        if title:
            if lang:
                title = f"{title} [{lang}]"
            titles.append(title)
    return titles


def _parse_doi(root: etree._Element) -> str:
    """Extract DOI from article-id[@pub-id-type='doi']."""
    doi_elem = root.find(".//article-meta/article-id[@pub-id-type='doi']")
    return text(doi_elem)


def _format_date(date_el: etree._Element) -> str:
    """Format a JATS date element as ISO-ish string (YYYY-MM-DD)."""
    year = text(date_el.find("year"))
    if not year:
        return ""
    month = text(date_el.find("month"))
    day = text(date_el.find("day"))
    parts = [year]
    if month:
        parts.append(month.zfill(2))
        if day:
            parts.append(day.zfill(2))
    return "-".join(parts)


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
        doc.pub_date = _format_date(pub_date)

    # License text
    license_el = meta.find(".//permissions/license/license-p")
    if license_el is not None:
        doc.license = all_text(license_el)

    # License URL
    lic_elem = meta.find(".//permissions/license")
    if lic_elem is not None:
        lic_href = lic_elem.get(
            "{http://www.w3.org/1999/xlink}href", ""
        )
        if not lic_href:
            lic_href = lic_elem.get("href", "")
        doc.license_url = lic_href

    # Copyright statement
    copyright_el = meta.find(".//permissions/copyright-statement")
    if copyright_el is not None:
        doc.copyright = all_text(copyright_el)

    # History dates (received, accepted)
    history = meta.find("history")
    if history is not None:
        for date_el in history.findall("date"):
            date_type = date_el.get("date-type", "")
            date_str = _format_date(date_el)
            if date_type == "received" and date_str:
                doc.received_date = date_str
            elif date_type in ("accepted", "acc") and date_str:
                doc.accepted_date = date_str

    # Self-URI (article PDF or landing page link)
    self_uri_el = meta.find("self-uri")
    if self_uri_el is not None:
        href = self_uri_el.get(
            "{http://www.w3.org/1999/xlink}href", ""
        )
        if not href:
            href = self_uri_el.get("href", "")
        if not href:
            href = text(self_uri_el)
        doc.self_uri = href

    # Counts (page-count, fig-count, table-count, etc.)
    counts_el = meta.find("counts")
    if counts_el is not None:
        for child in counts_el:
            tag = etree.QName(child.tag).localname if isinstance(
                child.tag, str
            ) else ""
            count_val = child.get("count", "")
            if tag and count_val:
                try:
                    doc.counts[tag] = int(count_val)
                except (ValueError, OverflowError):
                    pass


def _parse_keywords(root: etree._Element) -> list[str]:
    """Extract keywords from kwd-group/kwd.

    Handles ``<compound-kwd>`` (joins parts with space) and skips
    ``kwd-group-type="abbreviations"`` groups that aren't true keywords.
    """
    keywords: list[str] = []
    for kwd_group in root.findall(".//article-meta/kwd-group"):
        group_type = kwd_group.get("kwd-group-type", "")
        # Skip abbreviation lists — not really keywords
        if group_type == "abbreviations":
            continue
        for kwd in kwd_group.findall("kwd"):
            kwd_text = all_text(kwd)
            if kwd_text:
                keywords.append(kwd_text)
        # Compound keywords: <compound-kwd><compound-kwd-part>...</compound-kwd-part>
        for ckwd in kwd_group.findall("compound-kwd"):
            parts = [
                all_text(p) for p in ckwd.findall("compound-kwd-part")
                if all_text(p)
            ]
            if parts:
                keywords.append(" ".join(parts))
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
    """Parse paragraphs from an ``<abstract>`` element.

    Handles mixed content where direct ``<p>`` and ``<sec>`` children
    are interleaved (e.g. a lead paragraph followed by structured
    sections).
    """
    paragraphs: list[Paragraph] = []

    for child in abstract_elem:
        tag = (etree.QName(child.tag).localname
               if isinstance(child.tag, str) else "")
        if tag == "sec":
            title_elem = child.find("title")
            sec_title = (all_text(title_elem)
                         if title_elem is not None else "")
            for p_elem in child.findall("p"):
                para = _parse_paragraph(p_elem)
                if para.text and sec_title:
                    para.text = f"**{sec_title}:** {para.text}"
                if para.text:
                    paragraphs.append(para)
        elif tag == "p":
            para = _parse_paragraph(child)
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

    # Translated abstracts (<trans-abstract>)
    for tab in root.findall(".//article-meta/trans-abstract"):
        lang = tab.get("{http://www.w3.org/XML/1998/namespace}lang", "")
        title_elem = tab.find("title")
        if title_elem is not None:
            label = all_text(title_elem)
        else:
            label = f"Translated Abstract ({lang})" if lang else "Translated Abstract"
        paragraphs = _parse_abstract_content(tab)
        if paragraphs:
            results.append(SecondaryAbstract(
                abstract_type=f"trans-abstract-{lang}" if lang else "trans-abstract",
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


def _extract_funding_body_sections(doc: Document) -> None:
    """Move body sections named "Funding" into doc.funding_statement.

    Some articles have a ``<sec>`` in the body titled "Funding" that
    duplicates the structured ``<funding-group>`` from article-meta.
    To avoid duplicate ``## Funding`` headings in Markdown (which causes
    content loss on round-trip), merge these into funding_statement.
    """
    _FUNDING_HEADINGS = {"funding", "funding statement"}
    remaining: list[Section] = []
    extra_statements: list[str] = []
    for sec in doc.sections:
        if sec.heading.lower().strip() in _FUNDING_HEADINGS:
            for p in sec.paragraphs:
                if p.text:
                    extra_statements.append(p.text)
        else:
            remaining.append(sec)
    if extra_statements:
        doc.sections = remaining
        parts = []
        if doc.funding_statement:
            parts.append(doc.funding_statement)
        parts.extend(extra_statements)
        doc.funding_statement = "\n\n".join(parts)


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
    """Extract authors from contrib-group, resolving affiliations via xref.

    Handles both personal names (<name>) and group/collaborative
    authors (<collab>).
    """
    authors = []
    for contrib in root.findall(
        ".//article-meta/contrib-group/contrib[@contrib-type='author']"
    ):
        author = Author()
        name_elem = contrib.find("name")
        if name_elem is not None:
            author.surname = text(name_elem.find("surname"))
            author.given_name = text(name_elem.find("given-names"))
        else:
            # Group/collaborative author (e.g., consortia)
            collab_elem = contrib.find("collab")
            if collab_elem is not None:
                author.surname = all_text(collab_elem)

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
                    or preamble.formulas or preamble.subsections
                    or preamble.notes):
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
        elif tag == "graphic":
            preamble.figures.append(_parse_standalone_graphic(child))
        elif tag == "media":
            _parse_media_as_paragraph(child, preamble)
        elif tag in _SEC_BLOCK_TAGS:
            _dispatch_sec_block(child, tag, preamble)
        elif tag in _GROUP_CONTAINER_TAGS:
            _dispatch_group_container(child, tag, preamble, 1)

    # Flush trailing preamble
    if (preamble.paragraphs or preamble.figures
            or preamble.tables or preamble.lists
            or preamble.formulas or preamble.subsections
            or preamble.notes):
        sections.append(preamble)

    return sections


_BLOCK_TAGS = frozenset({
    "fig", "table-wrap", "disp-formula", "list", "graphic", "media",
})


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

# Container tags that wrap multiple figures, tables, or formulas.
_GROUP_CONTAINER_TAGS = frozenset({
    "fig-group", "table-wrap-group", "disp-formula-group",
})


def _dispatch_group_container(
    child: etree._Element, tag: str,
    section: Section, level: int,
) -> None:
    """Unpack group containers into their individual elements."""
    if tag == "fig-group":
        for fig_elem in child.findall("fig"):
            section.figures.append(_parse_fig(fig_elem))
    elif tag == "table-wrap-group":
        for tw_elem in child.findall("table-wrap"):
            section.tables.append(_parse_table_wrap(tw_elem))
    elif tag == "disp-formula-group":
        for df_elem in child.findall("disp-formula"):
            section.formulas.append(_parse_formula(df_elem))


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
    elif tag == "graphic":
        section.figures.append(_parse_standalone_graphic(child))
    elif tag == "media":
        _parse_media_as_paragraph(child, section)
    elif tag in _SEC_BLOCK_TAGS:
        _dispatch_sec_block(child, tag, section)
    elif tag in _GROUP_CONTAINER_TAGS:
        _dispatch_group_container(child, tag, section, level)
    else:
        # Fallback: extract text from unrecognized block elements
        # (e.g., <speech>, <verse-group>, <statement>, <code>,
        # <chem-struct-wrap>, <array>) to prevent silent content loss.
        fallback_text = all_text(child)
        if fallback_text:
            section.paragraphs.append(Paragraph(text=fallback_text))


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

    # Slow path — split around embedded block elements.
    # Accumulate text+refs into segments, flushing at each block boundary.
    parts: list[str] = []
    refs: list[InlineRef] = []
    annotations: list[NamedContent] = []

    def _flush() -> None:
        text = re.sub(r"\s+", " ", "".join(parts)).strip()
        if text:
            section.paragraphs.append(Paragraph(
                text=text, refs=list(refs),
                named_content=list(annotations),
            ))
        parts.clear()
        refs.clear()
        annotations.clear()

    def _collect_inline(child: etree._Element) -> None:
        tag = etree.QName(child.tag).localname if isinstance(
            child.tag, str
        ) else ""
        if tag == "xref":
            ref_text = all_text(child)
            rid = child.get("rid", "")
            if ref_text:
                refs.append(InlineRef(text=ref_text, target=rid))
                parts.append(ref_text)
        elif tag in ("ext-link", "uri"):
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
        elif tag == "email":
            parts.append(all_text(child))
        elif tag in _INLINE_FMT:
            inner = _inline_text(child)
            if inner:
                pre, suf = _INLINE_FMT[tag]
                parts.append(f"{pre}{inner}{suf}")
        else:
            inner = _inline_text(child)
            parts.append(inner)
            if tag in ("named-content", "styled-content") and inner:
                ctype = child.get("content-type", "")
                if ctype:
                    annotations.append(
                        NamedContent(text=inner, content_type=ctype)
                    )

    if p_elem.text:
        parts.append(p_elem.text)

    for child in p_elem:
        tag = etree.QName(child.tag).localname if isinstance(
            child.tag, str
        ) else ""

        if tag in _BLOCK_TAGS:
            _flush()
            if tag == "fig":
                section.figures.append(_parse_fig(child))
            elif tag == "table-wrap":
                section.tables.append(_parse_table_wrap(child))
            elif tag == "disp-formula":
                section.formulas.append(_parse_formula(child))
            elif tag == "list":
                section.lists.append(_parse_list(child))
            elif tag == "graphic":
                section.figures.append(_parse_standalone_graphic(child))
            elif tag == "media":
                _parse_media_as_paragraph(child, section)
            if child.tail:
                parts.append(child.tail)
        else:
            _collect_inline(child)
            if child.tail:
                parts.append(child.tail)

    _flush()


_INLINE_FMT: dict[str, tuple[str, str]] = {
    "italic": ("*", "*"),
    "bold": ("**", "**"),
    "sup": ("<sup>", "</sup>"),
    "sub": ("<sub>", "</sub>"),
    "monospace": ("`", "`"),
    "strike": ("~~", "~~"),
    "underline": ("<u>", "</u>"),
    "sc": ("", ""),        # small caps — no Markdown equivalent, preserve text
    "overline": ("", ""),  # overline — no Markdown equivalent, preserve text
    "roman": ("", ""),     # roman type in italic context — preserve text
}


def _inline_text(elem: etree._Element) -> str:
    """Recursively format inline content, preserving nested markup.

    Container-like inline elements (``<named-content>``, ``<styled-content>``,
    ``<abbrev>``, etc.) are recursed into so that nested formatting is
    preserved.  ``<break/>`` emits a newline.
    """
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
        elif tag == "break":
            parts.append("\n")
        else:
            # Recurse into container-like inline elements (named-content,
            # styled-content, abbrev, etc.) to preserve nested formatting.
            parts.append(_inline_text(child))
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
    annotations: list[NamedContent] = []

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
        elif tag in ("ext-link", "uri"):
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
        elif tag == "email":
            parts.append(all_text(child))
        elif tag in _INLINE_FMT:
            inner = _inline_text(child)
            if inner:
                pre, suf = _INLINE_FMT[tag]
                parts.append(f"{pre}{inner}{suf}")
        else:
            # Recurse via _inline_text to preserve nested formatting
            # inside container elements (named-content, styled-content, etc.)
            inner = _inline_text(child)
            parts.append(inner)
            # Collect content-type annotations from named-content/styled-content
            if tag in ("named-content", "styled-content") and inner:
                ctype = child.get("content-type", "")
                if ctype:
                    annotations.append(
                        NamedContent(text=inner, content_type=ctype)
                    )

        if child.tail:
            parts.append(child.tail)

    # Collapse XML-indentation whitespace (newlines + spaces) into
    # single spaces so parsed paragraphs read cleanly.
    para_text = re.sub(r"\s+", " ", "".join(parts)).strip()
    return Paragraph(text=para_text, refs=refs, named_content=annotations)


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

    # Alt-text: may appear as direct child of <fig> or inside <graphic>
    alt_elem = fig_elem.find("alt-text")
    if alt_elem is None:
        graphic_elem = fig_elem.find("graphic")
        if graphic_elem is not None:
            alt_elem = graphic_elem.find("alt-text")
    if alt_elem is not None:
        fig.alt_text = all_text(alt_elem).strip()

    attrib_elem = fig_elem.find("attrib")
    if attrib_elem is not None:
        fig.attrib = _inline_text(attrib_elem).strip()

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


def _parse_standalone_graphic(graphic_elem: etree._Element) -> Figure:
    """Parse a standalone <graphic> outside <fig> into a Figure.

    These appear as inline images, equation images, or decorative graphics
    in some PMC articles.
    """
    fig = Figure()
    href = graphic_elem.get(
        "{http://www.w3.org/1999/xlink}href", ""
    )
    if not href:
        href = graphic_elem.get("href", "")
    fig.graphic_url = href

    alt_elem = graphic_elem.find("alt-text")
    if alt_elem is not None:
        fig.alt_text = all_text(alt_elem).strip()

    label_elem = graphic_elem.find("label")
    if label_elem is not None:
        fig.label = all_text(label_elem)

    caption_elem = graphic_elem.find("caption")
    if caption_elem is not None:
        parts = []
        for p in caption_elem.findall("p"):
            parts.append(_inline_text(p).strip())
        fig.caption = " ".join(p for p in parts if p)

    return fig


def _parse_media_as_paragraph(
    media_elem: etree._Element, section: Section,
) -> None:
    """Parse a <media> element into a paragraph reference.

    Media elements (video, audio, datasets) are rendered as a descriptive
    paragraph with the media reference.
    """
    parts: list[str] = []

    label_elem = media_elem.find("label")
    if label_elem is not None:
        label = all_text(label_elem).strip()
        if label:
            parts.append(f"**{label}**")

    caption_elem = media_elem.find("caption")
    if caption_elem is not None:
        for p in caption_elem.findall("p"):
            cap_text = _inline_text(p).strip()
            if cap_text:
                parts.append(cap_text)

    if not parts:
        # Fallback: extract any text content
        fallback = all_text(media_elem).strip()
        if fallback:
            parts.append(fallback)

    if parts:
        section.paragraphs.append(Paragraph(text=" ".join(parts)))


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
    if table_elem is None:
        # Table may be inside <alternatives> wrapper
        table_elem = tw_elem.find("alternatives/table")
    if table_elem is not None:
        raw_rows: list[list[TableCell]] = []
        raw_spans: list[list[int]] = []

        def _collect_trs(
            parent: etree._Element, is_header: bool,
        ) -> None:
            for tr in parent.findall("tr"):
                cells, spans = _parse_table_row(tr, is_header=is_header)
                if cells:
                    raw_rows.append(cells)
                    raw_spans.append(spans)

        # Parse thead
        thead = table_elem.find("thead")
        if thead is not None:
            _collect_trs(thead, is_header=True)

        # Parse tbody
        tbody = table_elem.find("tbody")
        if tbody is not None:
            _collect_trs(tbody, is_header=False)

        # Parse tfoot (footer rows — append as data rows)
        tfoot = table_elem.find("tfoot")
        if tfoot is not None:
            _collect_trs(tfoot, is_header=False)

        # Direct tr elements (no thead/tbody)
        if thead is None and tbody is None and tfoot is None:
            _collect_trs(table_elem, is_header=False)

        # Expand rowspan cells into subsequent rows
        table.rows = _expand_rowspans(raw_rows, raw_spans)

    # Table footnotes from <table-wrap-foot>
    # Some articles have multiple <table-wrap-foot> elements per table.
    # Some use <fn> elements, others use bare <p> elements.
    for foot in tw_elem.findall("table-wrap-foot"):
        fn_elems = foot.findall(".//fn")
        if fn_elems:
            for fn in fn_elems:
                fn_text = all_text(fn)
                if fn_text:
                    table.foot_notes.append(fn_text)
        else:
            for p in foot.findall("p"):
                p_text = all_text(p)
                if p_text:
                    table.foot_notes.append(p_text)

    return table


def _parse_table_row(
    tr_elem: etree._Element, is_header: bool,
) -> tuple[list[TableCell], list[int]]:
    """Parse a <tr> element into a list of TableCells and rowspan counts.

    Returns:
        (cells, rowspans) where rowspans[i] is the rowspan value for
        cells[i].  Colspan is expanded inline with empty padding cells
        (rowspan 1).
    """
    cells: list[TableCell] = []
    rowspans: list[int] = []
    for child in tr_elem:
        tag = etree.QName(child.tag).localname if isinstance(
            child.tag, str
        ) else ""
        if tag in ("th", "td"):
            try:
                rowspan = max(int(child.get("rowspan", "1") or "1"), 1)
            except (ValueError, OverflowError):
                rowspan = 1
            try:
                colspan = min(int(child.get("colspan", "1") or "1"), 50)
            except (ValueError, OverflowError):
                colspan = 1
            cell_align = child.get("align", "")
            cell = TableCell(
                text=all_text(child),
                is_header=(tag == "th" or is_header),
                align=cell_align,
            )
            cells.append(cell)
            rowspans.append(rowspan)
            for _ in range(colspan - 1):
                cells.append(TableCell(
                    text="",
                    is_header=(tag == "th" or is_header),
                    align=cell_align,
                ))
                rowspans.append(rowspan)
    return cells, rowspans


def _expand_rowspans(
    rows: list[list[TableCell]],
    row_spans: list[list[int]],
) -> list[list[TableCell]]:
    """Expand rowspan cells into subsequent rows.

    For each cell with rowspan > 1, inserts an empty cell at the same
    column position in the subsequent rows.
    """
    if not rows:
        return rows

    # Build a grid, inserting carry-over cells from rowspans.
    # pending[col] = (remaining_rows, cell) for active rowspans.
    pending: dict[int, tuple[int, TableCell]] = {}
    result: list[list[TableCell]] = []

    for row_idx, (row, spans) in enumerate(zip(rows, row_spans)):
        expanded: list[TableCell] = []
        src_col = 0  # index into the original row
        out_col = 0  # index into the expanded row

        while src_col < len(row) or out_col in pending:
            if out_col in pending:
                remaining, orig_cell = pending[out_col]
                expanded.append(TableCell(
                    text="",
                    is_header=orig_cell.is_header,
                ))
                if remaining > 1:
                    pending[out_col] = (remaining - 1, orig_cell)
                else:
                    del pending[out_col]
                out_col += 1
            elif src_col < len(row):
                expanded.append(row[src_col])
                span = spans[src_col] if src_col < len(spans) else 1
                if span > 1:
                    pending[out_col] = (span - 1, row[src_col])
                src_col += 1
                out_col += 1
            else:
                break

        result.append(expanded)

    return result


def _parse_formula(formula_elem: etree._Element) -> Formula:
    """Parse a <disp-formula> element.

    Prefers ``<tex-math>`` content (raw LaTeX) over ``<mml:math>`` or plain
    text from ``all_text()``.  When an ``<alternatives>`` wrapper is present,
    selects the best available representation.
    """
    label_elem = formula_elem.find("label")
    label = all_text(label_elem)

    formula_text = _extract_formula_text(formula_elem)
    # Remove label from text — may appear at start or end
    if label:
        if formula_text.endswith(label):
            formula_text = formula_text[:-len(label)].strip()
        elif formula_text.startswith(label):
            formula_text = formula_text[len(label):].strip()

    return Formula(text=formula_text, label=label)


def _extract_formula_text(elem: etree._Element) -> str:
    """Extract the best text representation from a formula element.

    Priority order:
    1. ``<tex-math>`` — raw LaTeX, most readable for downstream use
    2. ``<mml:math>`` — extract text nodes from MathML
    3. ``all_text()`` — fallback for plain text formulas

    Handles ``<alternatives>`` containers that wrap multiple representations.
    """
    # Check for <alternatives> wrapper
    alt = elem.find("alternatives")
    search_in = alt if alt is not None else elem

    # 1. Try tex-math (raw LaTeX string)
    tex = search_in.find("tex-math")
    if tex is not None:
        tex_content = text(tex).strip()
        if tex_content:
            return tex_content

    # 2. Try MathML — extract text from annotation or mi/mn/mo elements
    for ns_prefix in ("", "{http://www.w3.org/1998/Math/MathML}"):
        mml = search_in.find(f"{ns_prefix}math")
        if mml is not None:
            # Prefer annotation with encoding="LaTeX" or "TeX"
            for ann in mml.iter(
                f"{ns_prefix}annotation",
                "{http://www.w3.org/1998/Math/MathML}annotation",
            ):
                encoding = (ann.get("encoding") or "").lower()
                if "tex" in encoding or "latex" in encoding:
                    ann_text = text(ann).strip()
                    if ann_text:
                        return ann_text
            # Fall back to all_text on the math element
            math_text = all_text(mml).strip()
            if math_text:
                return math_text

    # 3. Fallback
    return all_text(elem)


def _parse_list(list_elem: etree._Element) -> ListBlock:
    """Parse a <list> element.

    Each list-item may contain multiple <p> elements.  All paragraphs within
    a single list-item are joined with newlines into one item string so that
    no body text is lost.  Nested ``<list>`` children are flattened into the
    parent list.  Block elements (``<disp-formula>`` etc.) inside ``<p>``
    are skipped to avoid LaTeX noise.
    """
    list_type = list_elem.get("list-type", "")
    ordered = list_type in ("order", "ordered", "number")

    items: list[str] = []
    for item_elem in list_elem.findall("list-item"):
        # Prepend explicit <label> if present (e.g., "1.", "a)")
        label_elem = item_elem.find("label")
        label_prefix = all_text(label_elem).strip() + " " if (
            label_elem is not None and all_text(label_elem).strip()
        ) else ""
        paras = item_elem.findall("p")
        if paras:
            parts = [_p_text_skip_blocks(p) for p in paras]
            item_text = "\n".join(t for t in parts if t)
        else:
            item_text = all_text(item_elem)
        if item_text:
            items.append(label_prefix + item_text)
        # Flatten nested lists
        for nested in item_elem.findall("list"):
            nested_block = _parse_list(nested)
            items.extend(nested_block.items)

    return ListBlock(items=items, ordered=ordered)


def _p_text_skip_blocks(p_elem: etree._Element) -> str:
    """Extract text from a <p>, skipping LaTeX formula content.

    Formula elements containing ``<tex-math>`` produce LaTeX noise.
    This helper skips such formula *content* but preserves their tail text
    (which is regular prose).  Formulas without ``<tex-math>`` (plain text
    or MathML) are included via ``all_text()``.
    """
    parts: list[str] = []
    if p_elem.text:
        parts.append(p_elem.text)
    for child in p_elem:
        tag = etree.QName(child.tag).localname if isinstance(
            child.tag, str
        ) else ""
        if tag == "disp-formula":
            # Only skip content if it contains tex-math (LaTeX noise)
            if child.find(".//tex-math") is not None:
                pass  # skip LaTeX content, keep tail
            else:
                parts.append(all_text(child))
        elif tag in _INLINE_FMT:
            inner = _inline_text(child)
            if inner:
                pre, suf = _INLINE_FMT[tag]
                parts.append(f"{pre}{inner}{suf}")
        else:
            parts.append(all_text(child))
        if child.tail:
            parts.append(child.tail)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


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
    if title_elem is None:
        title_elem = elem.find("label")
    if title_elem is None:
        title_elem = elem.find("caption/title")
    if title_elem is not None:
        title_text = all_text(title_elem)
        if title_text:
            section.paragraphs.append(
                Paragraph(text=f"**{title_text}**")
            )
    for child in elem:
        tag = etree.QName(child.tag).localname if isinstance(
            child.tag, str
        ) else ""
        if tag == "p":
            _collect_from_p(child, section)
        elif tag == "list":
            section.lists.append(_parse_list(child))
        elif tag == "sec":
            section.subsections.append(_parse_sec(child, level=2))
        elif tag in ("fig", "table-wrap", "disp-formula"):
            if tag == "fig":
                section.figures.append(_parse_fig(child))
            elif tag == "table-wrap":
                section.tables.append(_parse_table_wrap(child))
            else:
                section.formulas.append(_parse_formula(child))


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


def _parse_acknowledgments(
    root: etree._Element,
    ack_sections: list[Section] | None = None,
) -> str:
    """Extract acknowledgments from back/ack.

    Any ``<sec>`` children within ``<ack>`` (e.g. CRediT authorship,
    ethical considerations) are appended to *ack_sections* if provided.
    """
    back = root.find("back")
    if back is None:
        back = root.find(".//back")
    ack = back.find("ack") if back is not None else None
    if ack is None:
        return ""

    parts: list[str] = []
    for p in ack.findall("./p"):
        p_text = all_text(p)
        if p_text:
            parts.append(p_text)

    # <sec> children within <ack> (author contributions, ethics, etc.)
    if ack_sections is not None:
        for sec in ack.findall("sec"):
            ack_sections.append(_parse_sec(sec, level=1))

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
            # Direct <p> children only (not descendants inside nested notes)
            for p in child.findall("./p"):
                p_text = all_text(p)
                if p_text:
                    section.paragraphs.append(Paragraph(text=p_text))
            # Nested <notes> and <sec> children → subsections
            for sub_notes in child.findall("./notes"):
                sub_sec = Section(level=2)
                sub_title = sub_notes.find("title")
                if sub_title is not None:
                    sub_sec.heading = all_text(sub_title)
                for p in sub_notes.findall(".//p"):
                    p_text = all_text(p)
                    if p_text:
                        sub_sec.paragraphs.append(Paragraph(text=p_text))
                if sub_sec.paragraphs or sub_sec.heading:
                    section.subsections.append(sub_sec)
            for sub_sec_elem in child.findall("./sec"):
                section.subsections.append(
                    _parse_sec(sub_sec_elem, level=2)
                )
            if (section.paragraphs or section.heading
                    or section.subsections):
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
        elif tag == "bio":
            section = Section(level=1)
            for p in child.findall(".//p"):
                p_text = all_text(p)
                if p_text:
                    section.paragraphs.append(Paragraph(text=p_text))
            if section.paragraphs:
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
        elif tag == "boxed-text":
            section = Section(level=1)
            _parse_boxed_text(child, section)
            if (section.paragraphs or section.subsections
                    or section.lists):
                doc.back_matter.append(section)


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
    for tag in ("element-citation", "mixed-citation", "nlm-citation"):
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

    # <uri> elements (URLs not wrapped in ext-link)
    for uri_elem in citation.findall("uri"):
        href = uri_elem.get(
            "{http://www.w3.org/1999/xlink}href", ""
        )
        if not href:
            href = uri_elem.get("href", "")
        if not href:
            href = text(uri_elem)
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
    # Title — prefer article-title, fall back to data-title (datasets)
    title_elem = citation.find("article-title")
    if title_elem is None:
        title_elem = citation.find("data-title")
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

    # Edition (for books)
    edition_elem = citation.find("edition")
    if edition_elem is not None:
        ref.edition = all_text(edition_elem)

    # Comment (e.g., "In press", "Epub ahead of print")
    comment_elem = citation.find("comment")
    if comment_elem is not None:
        ref.comment = all_text(comment_elem)

    # Date-in-citation (access date for URLs)
    date_cit = citation.find("date-in-citation")
    if date_cit is not None:
        access_date = all_text(date_cit).strip()
        if access_date:
            # Append to comment (e.g., "Accessed 2024-01-15")
            content_type = date_cit.get("content-type", "")
            prefix = "Accessed " if content_type == "access-date" else ""
            date_note = f"{prefix}{access_date}"
            if ref.comment:
                ref.comment = f"{ref.comment}; {date_note}"
            else:
                ref.comment = date_note

    # Editors
    _parse_ref_editors(citation, ref)

    _parse_ref_pages(citation, ref)
    _parse_ref_ids(citation, ref)

    return ref
