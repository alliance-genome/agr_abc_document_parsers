"""Parse PMC nXML/JATS XML into the intermediate Document model."""

from __future__ import annotations

import logging
import re
from copy import deepcopy

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


def _extract_tex_body(tex_content: str) -> str:
    """Extract the formula body from a LaTeX document string.

    Given tex-math content like ``\\documentclass...\\begin{document}
    $$formula$$\\end{document}``, return just ``formula`` (stripping
    the ``$$`` delimiters).  Returns empty string if the markers are
    not found or the body is empty.
    """
    marker = "\\begin{document}"
    idx = tex_content.find(marker)
    if idx == -1:
        return ""
    start = idx + len(marker)
    end = tex_content.find("\\end{document}", start)
    if end == -1:
        return ""
    body = tex_content[start:end].strip()
    # Strip $$ delimiters that commonly wrap the formula body.
    if body.startswith("$$") and body.endswith("$$"):
        body = body[2:-2].strip()
    elif body.startswith("$") and body.endswith("$"):
        body = body[1:-1].strip()
    return body


def _inline_formula_text(elem: etree._Element) -> str:
    """Extract readable text from an ``<inline-formula>`` element.

    When ``<alternatives>`` provides both ``<tex-math>`` (raw LaTeX) and
    MathML, prefers MathML to avoid dumping LaTeX preamble noise
    (``\\documentclass…``) into paragraph text.  Falls back to
    ``all_text()`` when MathML is unavailable.
    """
    alt = elem.find("alternatives")
    search_in = alt if alt is not None else elem

    # If alternatives has MathML, use it (skip noisy tex-math).
    for ns_prefix in ("", "{http://www.w3.org/1998/Math/MathML}"):
        mml = search_in.find(f"{ns_prefix}math")
        if mml is not None:
            mml_text = all_text(mml).strip()
            if mml_text:
                return mml_text

    # Fallback: extract formula body from tex-math preamble if present.
    tex = search_in.find("tex-math")
    if tex is not None:
        tex_content = text(tex).strip()
        if tex_content and "\\begin{document}" in tex_content:
            body = _extract_tex_body(tex_content)
            if body:
                return body

    # Final fallback: all_text (covers standalone short tex-math or
    # plain text).
    return all_text(elem)


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
        _parse_abstract_content(main_abstract_elem) if main_abstract_elem is not None else []
    )
    doc.secondary_abstracts = _parse_secondary_abstracts(
        root,
        main_abstract_elem,
    )
    doc.categories = _parse_categories(root)

    # Article-level metadata
    _parse_article_meta(root, doc)

    # Parse affiliations and contribution footnotes, then resolve into authors
    aff_map = _parse_affiliations(root)
    con_map = _parse_con_footnotes(root)
    doc.authors = _parse_authors(root, aff_map, con_map)

    doc.sections = _parse_body(root)
    doc.references = _parse_bibliography(root)
    ack_sections: list[Section] = []
    doc.acknowledgments = _parse_acknowledgments(root, ack_sections)

    # Dedicated back-matter fields (extracted BEFORE generic back_matter
    # to allow deduplication — see _parse_back_sections skip logic)
    doc.funding, doc.funding_statement = _parse_funding(root)
    doc.author_notes = _parse_author_notes_field(root)
    _extract_emails_from_notes(doc)
    doc.competing_interests = _parse_competing_interests(root)
    doc.data_availability = _parse_data_availability(root)

    # Back matter: appendices + ack sub-sections + additional sections.
    # Elements already captured in dedicated fields above are skipped.
    back_matter = _parse_appendices(root)
    back_matter.extend(ack_sections)
    back_matter.extend(_parse_back_sections(root, doc))
    doc.back_matter = back_matter

    # Deduplicate "Funding" sections from both body and back-matter
    # after all sections have been populated.
    _extract_funding_body_sections(doc)

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
        abbrev_el = root.find(".//journal-meta/journal-id[@journal-id-type='nlm-ta']")
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
        lic_href = lic_elem.get("{http://www.w3.org/1999/xlink}href", "")
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
        href = self_uri_el.get("{http://www.w3.org/1999/xlink}href", "")
        if not href:
            href = self_uri_el.get("href", "")
        if not href:
            href = text(self_uri_el)
        doc.self_uri = href

    # Counts (page-count, fig-count, table-count, etc.)
    counts_el = meta.find("counts")
    if counts_el is not None:
        for child in counts_el:
            tag = etree.QName(child.tag).localname if isinstance(child.tag, str) else ""
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
            parts = [all_text(p) for p in ckwd.findall("compound-kwd-part") if all_text(p)]
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
    sections).  Also handles nested ``<sec>`` within ``<sec>``
    (e.g. ``<abstract><sec><sec>...``).
    """
    paragraphs: list[Paragraph] = []

    def _collect_list(list_elem: etree._Element) -> None:
        """Collect paragraphs from a ``<list>`` inside an abstract."""
        for item in list_elem.findall("list-item"):
            for p in item.findall("p"):
                para = _parse_paragraph(p)
                if para.text:
                    paragraphs.append(para)

    def _collect_sec(sec_elem: etree._Element) -> None:
        """Recursively collect paragraphs from a ``<sec>``."""
        title_elem = sec_elem.find("title")
        sec_title = all_text(title_elem) if title_elem is not None else ""
        has_direct_content = False
        for child in sec_elem:
            ctag = etree.QName(child.tag).localname if isinstance(child.tag, str) else ""
            if ctag == "p":
                has_direct_content = True
                para = _parse_paragraph(child)
                if para.text and sec_title:
                    para.text = f"**{sec_title}:** {para.text}"
                    sec_title = ""  # only prepend to first
                if para.text:
                    paragraphs.append(para)
            elif ctag == "list":
                has_direct_content = True
                # Prepend section title to first list item if present
                first_item = True
                for item in child.findall("list-item"):
                    for p in item.findall("p"):
                        para = _parse_paragraph(p)
                        if para.text and sec_title and first_item:
                            para.text = f"**{sec_title}:** {para.text}"
                            sec_title = ""
                            first_item = False
                        if para.text:
                            paragraphs.append(para)
            elif ctag == "sec":
                _collect_sec(child)
        if not has_direct_content and sec_title:
            # Empty sec with title only (skip)
            pass

    for child in abstract_elem:
        tag = etree.QName(child.tag).localname if isinstance(child.tag, str) else ""
        if tag == "sec":
            _collect_sec(child)
        elif tag == "p":
            para = _parse_paragraph(child)
            if para.text:
                paragraphs.append(para)
        elif tag == "list":
            _collect_list(child)

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
            label = _SECONDARY_ABSTRACT_LABELS.get(ab_type, ab_type.replace("-", " ").title())
        paragraphs = _parse_abstract_content(ab)
        results.append(
            SecondaryAbstract(
                abstract_type=ab_type,
                label=label,
                paragraphs=paragraphs,
            )
        )

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
            results.append(
                SecondaryAbstract(
                    abstract_type=f"trans-abstract-{lang}" if lang else "trans-abstract",
                    label=label,
                    paragraphs=paragraphs,
                )
            )

    return results


def _collect_inline_aff(
    contrib: etree._Element,
    author: Author,
) -> None:
    """Collect inline ``<aff>`` data from within a ``<contrib>``.

    eLife sub-articles embed affiliation details (institution-id,
    institution, country) directly inside the contrib element rather
    than using top-level ``<aff>`` with xref linking.  This helper
    extracts those pieces and appends a single affiliation string.
    """
    for aff_el in contrib.findall("aff"):
        parts: list[str] = []
        # institution-wrap may contain institution-id and institution
        for inst in aff_el.findall(".//institution"):
            inst_text = (inst.text or "").strip()
            if inst_text:
                parts.append(inst_text)
        for addr in aff_el.findall(".//addr-line"):
            addr_text = (addr.text or "").strip()
            if addr_text:
                parts.append(addr_text)
        for country in aff_el.findall(".//country"):
            c_text = (country.text or "").strip()
            if c_text:
                parts.append(c_text)
        if not parts:
            # Fallback: use all text from the aff element
            fallback = all_text(aff_el)
            if fallback:
                parts.append(fallback)
        aff_text = " ".join(parts)
        if aff_text and aff_text not in author.affiliations:
            author.affiliations.append(aff_text)


def _parse_sub_articles(root: etree._Element) -> list[Document]:
    """Parse ``<sub-article>`` and ``<response>`` elements (including nested)."""
    results: list[Document] = []
    for sub_el in root.findall(".//sub-article"):
        results.append(_parse_sub_article(sub_el))
    for resp_el in root.findall(".//response"):
        results.append(_parse_sub_article(resp_el))
    return results


def _parse_sub_article(sub_el: etree._Element) -> Document:
    """Parse a single ``<sub-article>`` into a Document."""
    doc = Document(source_format="jats")
    doc.article_type = sub_el.get("article-type", "")

    # Front stub metadata — some publishers use <front>/<article-meta>
    # instead of the abbreviated <front-stub>.
    front_stub = sub_el.find("front-stub")
    if front_stub is None:
        front_stub = sub_el.find("front/article-meta")
    if front_stub is not None:
        # DOI from front-stub
        doi_el = front_stub.find("article-id[@pub-id-type='doi']")
        if doi_el is not None and doi_el.text:
            doc.doi = doi_el.text.strip()

        title_el = front_stub.find("title-group/article-title")
        if title_el is not None:
            doc.title = _inline_text(title_el).strip()

        # Authors from front-stub/contrib-group
        aff_map: dict[str, str] = {}
        for aff_elem in front_stub.findall("aff"):
            aff_id = aff_elem.get("id", "")
            # Extract text excluding <label> to avoid double-numbering.
            parts: list[str] = []
            for child in aff_elem:
                tag = etree.QName(child.tag).localname
                if tag == "label":
                    if child.tail:
                        parts.append(child.tail)
                    continue
                parts.append(all_text(child))
                if child.tail:
                    parts.append(child.tail)
            if not parts and aff_elem.text:
                parts.append(aff_elem.text)
            aff_text = " ".join("".join(parts).split())
            if aff_id and aff_text:
                aff_map[aff_id] = aff_text
        for contrib in front_stub.findall("contrib-group/contrib[@contrib-type='author']"):
            author = Author()
            name_elem = contrib.find("name")
            if name_elem is not None:
                author.surname = text(name_elem.find("surname"))
                author.given_name = text(name_elem.find("given-names"))
            # Assign affiliations via xref
            for xref in contrib.findall("xref[@ref-type='aff']"):
                rid = xref.get("rid", "")
                if rid and rid in aff_map:
                    author.affiliations.append(aff_map[rid])
            # Inline affiliations within the contrib element
            _collect_inline_aff(contrib, author)
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
                for xref in contrib.findall("xref[@ref-type='aff']"):
                    rid = xref.get("rid", "")
                    if rid and rid in aff_map:
                        author.affiliations.append(aff_map[rid])
                # Inline affiliations within the contrib element
                _collect_inline_aff(contrib, author)
                for role_el in contrib.findall("role"):
                    role_text = all_text(role_el)
                    if role_text:
                        author.roles.append(role_text)
                doc.authors.append(author)

        # Corresponding author notes
        for notes_el in front_stub.findall("author-notes"):
            for corresp in notes_el.findall("corresp"):
                ct = all_text(corresp)
                if ct:
                    doc.author_notes.append(ct)

    # Abstract from front-stub (conference abstract supplements may have
    # all content in <front-stub>/<abstract> with no <body>)
    if front_stub is not None:
        for abs_elem in front_stub.findall("abstract"):
            abs_parts = _parse_abstract_content(abs_elem)
            if abs_parts:
                doc.abstract.extend(abs_parts)

    # Body
    doc.sections = _parse_body(sub_el)

    # References within sub-article
    doc.references = _parse_bibliography(sub_el)

    # Back-matter sections (fn-groups, notes, etc.)
    doc.competing_interests = _parse_competing_interests(sub_el)
    doc.back_matter = _parse_back_sections(sub_el, doc)

    return doc


def _parse_categories(root: etree._Element) -> list[str]:
    """Extract subject categories from article-categories."""
    categories: list[str] = []
    for subj in root.findall(".//article-meta/article-categories/subj-group/subject"):
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
    """Move sections named "Funding" into doc.funding_statement.

    Some articles have a ``<sec>`` in the body or back-matter titled
    "Funding" that duplicates the structured ``<funding-group>`` from
    article-meta.  To avoid duplicate ``## Funding`` headings in
    Markdown (which causes content loss on round-trip), merge these
    into funding_statement.
    """
    _FUNDING_HEADINGS = {"funding", "funding statement"}
    extra_statements: list[str] = []

    # Check both body sections and back-matter sections.
    for attr in ("sections", "back_matter"):
        source = getattr(doc, attr, [])
        remaining: list[Section] = []
        for sec in source:
            if sec.heading.lower().strip() in _FUNDING_HEADINGS:
                for p in sec.paragraphs:
                    if p.text:
                        extra_statements.append(p.text)
                # Preserve non-funding subsections (e.g., COI under Funding)
                for subsec in sec.subsections:
                    remaining.append(subsec)
            else:
                remaining.append(sec)
        setattr(doc, attr, remaining)

    if extra_statements:
        parts = []
        if doc.funding_statement:
            parts.append(doc.funding_statement)
        parts.extend(extra_statements)
        doc.funding_statement = "\n\n".join(parts)


def _parse_author_notes_field(root: etree._Element) -> list[str]:
    """Parse ``<author-notes>`` from article-meta into flat strings.

    Skips COI footnotes (handled by ``_parse_competing_interests``).
    Resolves footnote labels to linked author names when possible.
    """
    notes: list[str] = []
    an = root.find(".//article-meta/author-notes")
    if an is None:
        return notes

    # Build map: fn id -> list of author names that reference it
    fn_to_authors: dict[str, list[str]] = {}
    for contrib in root.findall(
        ".//article-meta/contrib-group/contrib[@contrib-type='author']"
    ):
        name_elem = contrib.find("name")
        if name_elem is None:
            continue
        given = text(name_elem.find("given-names"))
        surname = text(name_elem.find("surname"))
        full_name = f"{given} {surname}".strip()
        if not full_name:
            continue
        for xref in contrib.findall("xref[@ref-type='fn']"):
            rid = xref.get("rid", "")
            if rid:
                fn_to_authors.setdefault(rid, []).append(full_name)

    for child in an:
        tag = etree.QName(child.tag).localname if isinstance(child.tag, str) else ""
        if tag == "corresp":
            # Strip <label> from corresp
            label = child.find("label")
            if label is not None:
                raw = all_text(child)
                label_text = all_text(label)
                if label_text and raw.startswith(label_text):
                    raw = raw[len(label_text):].strip()
                t = raw
            else:
                t = all_text(child)
            if t:
                notes.append(t)
        elif tag == "fn":
            fn_type = child.get("fn-type", "")
            if fn_type in _COI_FN_TYPES:
                continue
            # Extract text, skipping <label>
            paras = child.findall("p")
            if paras:
                t = " ".join(all_text(p) for p in paras if all_text(p))
            else:
                t = all_text(child)
                # Strip leading label text
                label = child.find("label")
                if label is not None:
                    label_text = all_text(label)
                    if label_text and t.startswith(label_text):
                        t = t[len(label_text):].strip()
            if not t:
                continue
            # Prepend linked author names
            fn_id = child.get("id", "")
            linked_authors = fn_to_authors.get(fn_id, [])
            if linked_authors:
                prefix = ", ".join(linked_authors)
                t = f"{prefix}: {t}"
            notes.append(t)
    return notes


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")

# Patterns that indicate a note is a correspondence note (not a
# "present address" or "contributed equally" note).
_CORRESP_PATTERNS = re.compile(
    r"correspond|for\s+correspondence|^\*\s*[A-Z].*@",
    re.IGNORECASE,
)


def _extract_emails_from_notes(doc: Document) -> None:
    """Move emails from ``author_notes`` into ``Author.email`` fields.

    Scans each author note for email addresses.  When an email is found
    and can be matched to an author (by name or surname appearing in the
    same note), it is assigned to ``Author.email``.  Notes that only
    contained correspondence information are removed from
    ``doc.author_notes``; notes with other content (equal contribution,
    present address) are kept.
    """
    if not doc.author_notes or not doc.authors:
        return

    # Build lookup helpers
    authors_by_surname: dict[str, list[Author]] = {}
    authors_by_name: dict[str, Author] = {}
    authors_by_initials: dict[str, Author] = {}
    for author in doc.authors:
        sn = author.surname.lower()
        if sn:
            authors_by_surname.setdefault(sn, []).append(author)
        full = f"{author.given_name} {author.surname}".strip()
        if full:
            authors_by_name[full.lower()] = author
        # Build initials like "C.M.L." from "Catherine M Lutz"
        initials = "".join(
            p[0] + "." for p in (author.given_name + " " + author.surname).split() if p
        )
        if initials:
            authors_by_initials[initials.upper()] = author

    remaining: list[str] = []
    for note in doc.author_notes:
        emails = _EMAIL_RE.findall(note)
        if not emails:
            remaining.append(note)
            continue

        # For notes with multiple emails, split into per-email
        # segments so each email is matched against its local context.
        segments = _split_note_by_emails(note, emails)

        # Try to match each email to an author
        assigned = 0
        for email, segment in zip(emails, segments):
            # Skip if any author already has this email
            if any(a.email == email for a in doc.authors):
                assigned += 1
                continue
            matched = _match_email_to_author(
                email,
                segment,
                doc.authors,
                authors_by_surname,
                authors_by_name,
                authors_by_initials,
            )
            if matched:
                assigned += 1

        # Keep note if it has non-correspondence content
        is_corresp_only = bool(_CORRESP_PATTERNS.search(note))
        if not is_corresp_only or assigned < len(emails):
            remaining.append(note)

    doc.author_notes = remaining


def _split_note_by_emails(note: str, emails: list[str]) -> list[str]:
    """Split a note into segments, one per email.

    For a note like ``"Name1 email1@x; Name2 email2@x"``, returns
    ``["Name1 email1@x", "Name2 email2@x"]`` so each email is matched
    against only its local context.
    """
    if len(emails) <= 1:
        return [note]
    segments: list[str] = []
    positions = []
    for email in emails:
        idx = note.find(email)
        positions.append(idx if idx >= 0 else len(note))
    for i, _pos in enumerate(positions):
        start = positions[i - 1] + len(emails[i - 1]) if i > 0 else 0
        end = positions[i] + len(emails[i])
        segments.append(note[start:end])
    return segments


def _match_email_to_author(
    email: str,
    note_text: str,
    authors: list[Author],
    by_surname: dict[str, list[Author]],
    by_name: dict[str, Author],
    by_initials: dict[str, Author],
) -> bool:
    """Try to match an email to an author and assign it.

    Matching strategies (in order):
    1. Full name appears in the note text
    2. Surname appears near the email in the note
    3. Initials like (C.M.L.) appear in the note
    4. Email local part contains surname
    5. Single author without email — assign by default

    Returns True if matched.
    """
    note_lower = note_text.lower()
    local_part = email.split("@")[0].lower()

    # Strategy 1: full name in note
    for full_name, author in by_name.items():
        if not author.email and full_name in note_lower:
            author.email = email
            return True

    # Strategy 2: surname as whole word near email
    for surname, author_list in by_surname.items():
        if len(surname) >= 3 and re.search(r"\b" + re.escape(surname) + r"\b", note_lower):
            for author in author_list:
                if not author.email:
                    author.email = email
                    return True

    # Strategy 3: initials like (C.M.L.)
    for initials, author in by_initials.items():
        if not author.email and initials in note_text:
            author.email = email
            return True

    # Strategy 4: email local part contains surname (strip punctuation)
    for surname, author_list in by_surname.items():
        clean_surname = re.sub(r"['\u2018\u2019\u0060\-]", "", surname)
        if clean_surname and clean_surname in local_part:
            for author in author_list:
                if not author.email:
                    author.email = email
                    return True

    # Strategy 5: single unmatched author
    without_email = [a for a in authors if not a.email]
    if len(without_email) == 1:
        without_email[0].email = email
        return True

    return False


_COI_TITLES = {
    "competing interests",
    "competing interest",
    "conflicts of interest",
    "conflict of interest",
    "conflict of interests",
}


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
    # From back/fn-group (direct children and inside notes)
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
        for notes_el in back.findall("notes"):
            for fg in notes_el.findall("fn-group"):
                for fn in fg.findall("fn"):
                    if fn.get("fn-type", "") in _COI_FN_TYPES:
                        fn_text = all_text(fn)
                        if fn_text:
                            parts.append(fn_text)
        # From back/notes with COI-statement type or matching title
        if not parts:
            for notes_elem in back.findall("notes"):
                ntype = notes_elem.get("notes-type", "")
                is_coi = ntype in _COI_FN_TYPES
                if not is_coi:
                    title_elem = notes_elem.find("title")
                    if title_elem is not None:
                        title_text = all_text(title_elem).strip().lower()
                        is_coi = title_text in _COI_TITLES
                if is_coi:
                    for p in notes_elem.findall(".//p"):
                        p_text = all_text(p)
                        if p_text:
                            parts.append(p_text)
    return "\n\n".join(parts)


_DATA_AVAIL_TITLES = {
    "data availability",
    "data availability statement",
    "availability of data and materials",
    "availability of data and material",
}


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
        # From back/notes with matching title or sec-type
        if not parts:
            for notes_elem in back.findall("notes"):
                ntype = notes_elem.get("notes-type", "")
                if ntype and ntype != "data-availability":
                    continue
                # Check notes title
                title_elem = notes_elem.find("title")
                if title_elem is not None:
                    title_text = all_text(title_elem).strip().lower()
                    if title_text in _DATA_AVAIL_TITLES:
                        for p in notes_elem.findall(".//p"):
                            p_text = all_text(p)
                            if p_text:
                                parts.append(p_text)
                # Check nested <sec> with sec-type or title
                for sec in notes_elem.findall("sec"):
                    sec_type = sec.get("sec-type", "")
                    sec_title = sec.find("title")
                    sec_title_text = (
                        all_text(sec_title).strip().lower() if sec_title is not None else ""
                    )
                    if sec_type == "data-availability" or sec_title_text in _DATA_AVAIL_TITLES:
                        for p in sec.findall("p"):
                            p_text = all_text(p)
                            if p_text:
                                parts.append(p_text)
    # From custom-meta-group
    if not parts:
        for cm in root.findall(".//article-meta/custom-meta-group/custom-meta"):
            meta_name = cm.find("meta-name")
            meta_value = cm.find("meta-value")
            if meta_name is not None and meta_value is not None:
                name_text = all_text(meta_name)
                if name_text and "data availability" in name_text.lower():
                    val_text = all_text(meta_value)
                    if val_text:
                        parts.append(val_text)
    return "\n\n".join(parts)


def _aff_text(aff_elem: etree._Element) -> str:
    """Extract clean affiliation text, skipping labels and institution IDs."""
    parts: list[str] = []
    for child in aff_elem:
        tag = etree.QName(child.tag).localname if isinstance(child.tag, str) else ""
        if tag in ("label", "institution-id"):
            continue
        if tag == "institution-wrap":
            for sub in child:
                sub_tag = etree.QName(sub.tag).localname if isinstance(sub.tag, str) else ""
                if sub_tag == "institution-id":
                    continue
                t = all_text(sub)
                if t:
                    parts.append(t)
        else:
            t = all_text(child)
            if t:
                parts.append(t)
    if parts:
        return ", ".join(parts)
    # Fallback for plain-text affs (no child elements, just text node):
    # skip leading label text by removing the <label> content.
    label = aff_elem.find("label")
    raw = all_text(aff_elem)
    if label is not None and label.text and raw.startswith(label.text):
        raw = raw[len(label.text) :].strip()
    return raw


_NOT_AFFILIATION = re.compile(
    r"^(these authors |contributed equally|lead contact|present address)",
    re.IGNORECASE,
)


def _parse_affiliations(root: etree._Element) -> dict[str, str]:
    """Build a map of aff id -> affiliation text.

    Handles ``<aff>`` as direct children of ``<article-meta>`` *and*
    inside ``<contrib-group>`` (eLife style).  Filters out entries
    that are footnotes rather than affiliations (e.g. "These authors
    contributed equally", "Lead contact").
    """
    aff_map: dict[str, str] = {}
    for path in (
        ".//article-meta/aff",
        ".//article-meta/contrib-group/aff",
    ):
        for aff_elem in root.findall(path):
            aff_id = aff_elem.get("id", "")
            if aff_id and aff_id not in aff_map:
                aff_text = _aff_text(aff_elem)
                if aff_text and not _NOT_AFFILIATION.match(aff_text):
                    aff_map[aff_id] = aff_text
    return aff_map


def _parse_con_footnotes(root: etree._Element) -> dict[str, str]:
    """Build a map of fn id -> contribution text for fn-type='con' footnotes.

    eLife stores CRediT roles as ``<fn fn-type="con">`` referenced via
    ``<xref ref-type="fn" rid="con1">`` from each contributor.
    """
    con_map: dict[str, str] = {}
    for fn in root.findall(".//fn[@fn-type='con']"):
        fn_id = fn.get("id", "")
        if fn_id:
            fn_text = all_text(fn)
            if fn_text:
                con_map[fn_id] = fn_text
    return con_map


def _parse_authors(
    root: etree._Element,
    aff_map: dict[str, str],
    con_map: dict[str, str] | None = None,
) -> list[Author]:
    """Extract authors from contrib-group, resolving affiliations via xref.

    Handles both personal names (<name>) and group/collaborative
    authors (<collab>).
    """
    if con_map is None:
        con_map = {}
    authors = []
    for contrib in root.findall(".//article-meta/contrib-group/contrib[@contrib-type='author']"):
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
        if email_elem is None:
            email_elem = contrib.find(".//address/email")
        if email_elem is not None:
            author.email = text(email_elem)

        # ORCID — try contrib-id first, then uri
        orcid_elem = contrib.find("contrib-id[@contrib-id-type='orcid']")
        if orcid_elem is not None:
            author.orcid = text(orcid_elem)

        # Resolve affiliations via xref
        for xref in contrib.findall("xref[@ref-type='aff']"):
            rid = xref.get("rid", "")
            if rid in aff_map:
                author.affiliations.append(aff_map[rid])

        # Inline affiliations within the contrib element
        _collect_inline_aff(contrib, author)

        # CRediT roles from <role> elements
        for role_el in contrib.findall("role"):
            role_text = all_text(role_el)
            if role_text:
                author.roles.append(role_text)

        # CRediT roles from fn-type="con" xrefs (eLife style)
        if not author.roles:
            for xref in contrib.findall("xref[@ref-type='fn']"):
                rid = xref.get("rid", "")
                if rid and rid in con_map:
                    author.roles.append(con_map[rid])

        authors.append(author)

    # If no author has affiliations but aff_map has entries,
    # assign all affiliations to all authors (shared affiliation).
    if aff_map and authors and not any(a.affiliations for a in authors):
        shared = list(aff_map.values())
        for author in authors:
            author.affiliations = list(shared)

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
        tag = etree.QName(child.tag).localname if isinstance(child.tag, str) else ""

        if tag == "sec":
            # Flush any accumulated preamble content
            if (
                preamble.paragraphs
                or preamble.figures
                or preamble.tables
                or preamble.lists
                or preamble.formulas
                or preamble.subsections
                or preamble.notes
            ):
                sections.append(preamble)
                preamble = Section(level=1)
            sections.append(_parse_sec(child, level=1))
        elif tag == "p":
            _collect_from_p(child, preamble)
        elif tag == "fig":
            preamble.figures.extend(_parse_fig(child))
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
        elif tag == "speech":
            _parse_speech(child, preamble)
        elif tag in _SEC_BLOCK_TAGS:
            _dispatch_sec_block(child, tag, preamble)
        elif tag in _GROUP_CONTAINER_TAGS:
            _dispatch_group_container(child, tag, preamble, 1)
        elif tag:
            # Fallback: extract text from unrecognized body-level blocks
            # (e.g., <verse-group>) to prevent silent content loss.
            fallback_text = all_text(child)
            if fallback_text:
                preamble.paragraphs.append(Paragraph(text=fallback_text))

    # Flush trailing preamble
    if (
        preamble.paragraphs
        or preamble.figures
        or preamble.tables
        or preamble.lists
        or preamble.formulas
        or preamble.subsections
        or preamble.notes
    ):
        sections.append(preamble)

    return sections


_BLOCK_TAGS = frozenset(
    {
        "fig",
        "table-wrap",
        "disp-formula",
        "list",
        "graphic",
        "media",
    }
)


def _dispatch_sec_block(
    child: etree._Element,
    tag: str,
    section: Section,
) -> None:
    """Handle supplementary, boxed-text, quote, def-list, etc."""
    if tag == "supplementary-material":
        _parse_supplementary(child, section)
    elif tag == "boxed-text":
        box_sec = Section(level=section.level + 1, is_boxed=True)
        # Use boxed-text title/label/caption as heading
        for t_tag in ("title", "label", "caption/title"):
            t_elem = child.find(t_tag)
            if t_elem is not None:
                t_text = all_text(t_elem).strip()
                if t_text:
                    box_sec.heading = t_text
                    break
        _parse_boxed_text(child, box_sec)
        # Remove duplicate bold title added by _parse_boxed_text
        if box_sec.heading and box_sec.paragraphs:
            bold_title = f"**{box_sec.heading}**"
            box_sec.paragraphs = [p for p in box_sec.paragraphs if p.text != bold_title]
        if (
            box_sec.paragraphs
            or box_sec.subsections
            or box_sec.lists
            or box_sec.figures
            or box_sec.tables
            or box_sec.formulas
            or box_sec.notes
        ):
            section.subsections.append(box_sec)
    elif tag == "disp-quote":
        lines: list[str] = []
        for dq_child in child:
            dq_tag = etree.QName(dq_child.tag).localname if isinstance(dq_child.tag, str) else ""
            if dq_tag == "p":
                t = all_text(dq_child)
                if t:
                    lines.append(f"> {t}")
            elif dq_tag == "list":
                for li in dq_child.findall("list-item"):
                    li_p = li.find("p")
                    li_t = _inline_text(li_p).strip() if li_p is not None else all_text(li).strip()
                    if li_t:
                        lines.append(f"> {li_t}")
            elif dq_tag == "attrib":
                attrib_text = all_text(dq_child)
                if attrib_text:
                    lines.append(f"> {attrib_text}")
        if lines:
            section.paragraphs.append(Paragraph(text="\n".join(lines)))
        elif not list(child):
            quote_text = all_text(child)
            if quote_text:
                section.paragraphs.append(Paragraph(text=f"> {quote_text}"))
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
            section.paragraphs.append(Paragraph(text=f"{fence}\n{pre_text}\n{fence}"))
    elif tag == "glossary":
        _parse_glossary(child, section, emit_title=True)


_SEC_BLOCK_TAGS = frozenset(
    {
        "supplementary-material",
        "boxed-text",
        "disp-quote",
        "def-list",
        "fn-group",
        "preformat",
        "glossary",
    }
)

# Container tags that wrap multiple figures, tables, or formulas.
_GROUP_CONTAINER_TAGS = frozenset(
    {
        "fig-group",
        "table-wrap-group",
        "disp-formula-group",
    }
)


def _dispatch_group_container(
    child: etree._Element,
    tag: str,
    section: Section,
    level: int,
) -> None:
    """Unpack group containers into their individual elements."""
    if tag == "fig-group":
        # Capture group-level label/caption for propagation
        # to child figures that lack their own.
        grp_label_elem = child.find("label")
        grp_label = all_text(grp_label_elem).strip() if grp_label_elem is not None else ""
        grp_cap_elem = child.find("caption")
        grp_caption = ""
        grp_cap_paragraphs: list[str] = []
        if grp_cap_elem is not None:
            cap_title = grp_cap_elem.find("title")
            if cap_title is not None:
                grp_caption = _inline_text(cap_title).strip()
            cap_ps = [
                _inline_text(p).strip()
                for p in grp_cap_elem.findall("p")
                if _inline_text(p).strip()
            ]
            if grp_caption and cap_ps:
                grp_cap_paragraphs = cap_ps
            elif cap_ps and not grp_caption:
                grp_caption = cap_ps[0]
                grp_cap_paragraphs = cap_ps[1:]

        child_figs: list[Figure] = []
        for fig_elem in child.findall("fig"):
            child_figs.extend(_parse_fig(fig_elem))

        if child_figs:
            # Propagate group label/caption to the first child
            # figure when it lacks its own.
            first = child_figs[0]
            if grp_label and not first.label:
                first.label = grp_label
            if grp_caption and not first.caption:
                first.caption = grp_caption
                if grp_cap_paragraphs:
                    first.caption_paragraphs = grp_cap_paragraphs + first.caption_paragraphs
            elif grp_caption and first.caption:
                # Both have captions — combine
                first.caption_paragraphs = (
                    [grp_caption] + grp_cap_paragraphs + first.caption_paragraphs
                )
            if grp_label and not first.label:
                first.label = grp_label
        elif grp_label or grp_caption:
            # No child figs — create a standalone figure from
            # the group-level metadata.
            fig = Figure()
            fig.label = grp_label
            fig.caption = grp_caption
            fig.caption_paragraphs = grp_cap_paragraphs
            child_figs = [fig]
        section.figures.extend(child_figs)
    elif tag == "table-wrap-group":
        # Capture group-level label/caption for propagation
        group_label_elem = child.find("label")
        group_label = all_text(group_label_elem).strip() if group_label_elem is not None else ""
        group_cap_elem = child.find("caption")
        group_caption = ""
        if group_cap_elem is not None:
            cap_title = group_cap_elem.find("title")
            if cap_title is not None:
                group_caption = all_text(cap_title).strip()
            if not group_caption:
                for cp in group_cap_elem.findall("p"):
                    ct = all_text(cp).strip()
                    if ct:
                        group_caption = ct
                        break
        for tw_elem in child.findall("table-wrap"):
            table = _parse_table_wrap(tw_elem)
            # Prepend group label/caption when the child lacks its own
            if group_label and not table.label:
                table.label = group_label
            if group_caption and not table.caption:
                table.caption = group_caption
            section.tables.append(table)
    elif tag == "disp-formula-group":
        for df_elem in child.findall("disp-formula"):
            section.formulas.append(_parse_formula(df_elem))


def _parse_speech(speech_elem: etree._Element, section: Section) -> None:
    """Parse a <speech> element into paragraphs.

    A <speech> contains a <speaker> followed by one or more <p> elements.
    The speaker text is prepended to the first paragraph; subsequent
    paragraphs are emitted standalone.
    """
    speaker_elem = speech_elem.find("speaker")
    speaker_text = all_text(speaker_elem).strip() if speaker_elem is not None else ""
    paragraphs = speech_elem.findall("p")
    for i, p_elem in enumerate(paragraphs):
        p_text = all_text(p_elem)
        if not p_text:
            continue
        if i == 0 and speaker_text:
            # Ensure a space between speaker label and content
            if speaker_text.endswith(":"):
                p_text = speaker_text + " " + p_text
            else:
                p_text = speaker_text + ": " + p_text
        section.paragraphs.append(Paragraph(text=p_text))
    # Fallback: if no <p> children, emit speaker text alone
    if not paragraphs and speaker_text:
        section.paragraphs.append(Paragraph(text=speaker_text))


def _dispatch_sec_child(
    child: etree._Element,
    tag: str,
    section: Section,
    level: int,
) -> None:
    """Handle a single child element of a <sec>."""
    if tag in ("title", "label"):
        return
    elif tag == "p":
        _collect_from_p(child, section)
    elif tag == "sec":
        section.subsections.append(_parse_sec(child, level + 1))
    elif tag == "fig":
        section.figures.extend(_parse_fig(child))
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
    elif tag == "speech":
        _parse_speech(child, section)
    elif tag in _SEC_BLOCK_TAGS:
        _dispatch_sec_block(child, tag, section)
    elif tag in _GROUP_CONTAINER_TAGS:
        _dispatch_group_container(child, tag, section, level)
    elif tag == "statement":
        # Theorem/proof blocks: iterate children like a mini-section
        label_el = child.find("label")
        if label_el is not None:
            label_text = all_text(label_el).strip()
            if label_text:
                section.paragraphs.append(Paragraph(text=f"**{label_text}**"))
        for stmt_child in child:
            st = etree.QName(stmt_child.tag).localname if isinstance(stmt_child.tag, str) else ""
            if st == "p":
                _collect_from_p(stmt_child, section)
            elif st == "disp-formula":
                section.formulas.append(_parse_formula(stmt_child))
            elif st == "list":
                section.lists.append(_parse_list(stmt_child))
            elif st not in ("label", "title"):
                ft = all_text(stmt_child)
                if ft:
                    section.paragraphs.append(Paragraph(text=ft))
    else:
        # Fallback: extract text from unrecognized block elements
        # (e.g., <verse-group>, <code>, <chem-struct-wrap>, <array>)
        # to prevent silent content loss.
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
        tag = etree.QName(child.tag).localname if isinstance(child.tag, str) else ""
        _dispatch_sec_child(child, tag, section, level)

    return section


def _collect_from_p(p_elem: etree._Element, section: Section) -> None:
    """Parse a <p> element, extracting any embedded block elements.

    JATS allows block-level elements (<table-wrap>, <fig>, <disp-formula>,
    <list>) to be nested inside <p>.  When that happens the paragraph text
    before/after the block element is emitted as separate paragraphs, and
    the block element is added to the appropriate section list.
    """
    child_tags = {etree.QName(c.tag).localname for c in p_elem if isinstance(c.tag, str)}
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
            section.paragraphs.append(
                Paragraph(
                    text=text,
                    refs=list(refs),
                    named_content=list(annotations),
                )
            )
        parts.clear()
        refs.clear()
        annotations.clear()

    def _collect_inline(child: etree._Element) -> None:
        tag = etree.QName(child.tag).localname if isinstance(child.tag, str) else ""
        if tag == "xref":
            # Preserve inline formatting (sup/sub) inside citations
            ref_text = all_text(child)
            display_text = _inline_text(child) if child.find("sup") is not None or child.find("sub") is not None else ref_text
            rid = child.get("rid", "")
            if ref_text:
                refs.append(InlineRef(text=ref_text, target=rid))
                parts.append(display_text)
        elif tag in ("ext-link", "uri"):
            link_text = all_text(child)
            href = child.get("{http://www.w3.org/1999/xlink}href", "")
            if not href:
                href = child.get("href", "")
            if link_text and href and link_text != href:
                parts.append(f"[{link_text}]({href})")
            elif link_text:
                parts.append(link_text)
            # Skip self-closing/empty ext-link — no visible text.
        elif tag == "email":
            parts.append(all_text(child))
        elif tag == "inline-formula":
            parts.append(_inline_formula_text(child))
        elif tag in _INLINE_FMT:
            inner = _inline_text(child)
            if inner:
                parts.append(_wrap_inline(tag, inner))
        else:
            inner = _inline_text(child)
            parts.append(inner)
            if tag in ("named-content", "styled-content") and inner:
                ctype = child.get("content-type", "")
                if ctype:
                    annotations.append(NamedContent(text=inner, content_type=ctype))

    if p_elem.text:
        parts.append(p_elem.text)

    for child in p_elem:
        tag = etree.QName(child.tag).localname if isinstance(child.tag, str) else ""

        if tag in _BLOCK_TAGS:
            _flush()
            if tag == "fig":
                section.figures.extend(_parse_fig(child))
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
    "sc": ("", ""),  # small caps — no Markdown equivalent, preserve text
    "overline": ("", ""),  # overline — no Markdown equivalent, preserve text
    "roman": ("", ""),  # roman type in italic context — preserve text
}


def _wrap_inline(tag: str, inner: str) -> str:
    """Wrap *inner* with the markdown markers for *tag*, escaping conflicts.

    When ``<bold>*</bold>`` is naively wrapped as ``***``, the result is
    ambiguous markdown.  This helper escapes inner ``*`` characters when
    the wrapper itself uses ``*`` to avoid such collisions.
    """
    pre, suf = _INLINE_FMT[tag]
    if "*" in pre and inner.strip("*") == "":
        # Inner text is only asterisks — escape each one.
        inner = inner.replace("*", r"\*")
    return f"{pre}{inner}{suf}"


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
        tag = etree.QName(child.tag).localname if isinstance(child.tag, str) else ""
        if tag == "inline-formula":
            parts.append(_inline_formula_text(child))
        elif tag in _INLINE_FMT:
            inner = _inline_text(child)
            if inner:
                parts.append(_wrap_inline(tag, inner))
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
        tag = etree.QName(child.tag).localname if isinstance(child.tag, str) else ""

        if skip_tags and tag in skip_tags:
            # Still collect the tail text after the skipped element
            if child.tail:
                parts.append(child.tail)
            continue

        if tag == "xref":
            ref_text = all_text(child)
            display_text = _inline_text(child) if child.find("sup") is not None or child.find("sub") is not None else ref_text
            rid = child.get("rid", "")
            if ref_text:
                refs.append(InlineRef(text=ref_text, target=rid))
                parts.append(display_text)
        elif tag in ("ext-link", "uri"):
            link_text = all_text(child)
            href = child.get("{http://www.w3.org/1999/xlink}href", "")
            if not href:
                href = child.get("href", "")
            if link_text and href and link_text != href:
                parts.append(f"[{link_text}]({href})")
            elif link_text:
                parts.append(link_text)
            # Skip self-closing/empty ext-link — no visible text.
        elif tag == "email":
            parts.append(all_text(child))
        elif tag == "inline-formula":
            parts.append(_inline_formula_text(child))
        elif tag in _INLINE_FMT:
            inner = _inline_text(child)
            if inner:
                parts.append(_wrap_inline(tag, inner))
        else:
            # Recurse via _inline_text to preserve nested formatting
            # inside container elements (named-content, styled-content, etc.)
            inner = _inline_text(child)
            parts.append(inner)
            # Collect content-type annotations from named-content/styled-content
            if tag in ("named-content", "styled-content") and inner:
                ctype = child.get("content-type", "")
                if ctype:
                    annotations.append(NamedContent(text=inner, content_type=ctype))

        if child.tail:
            parts.append(child.tail)

    # Collapse XML-indentation whitespace (newlines + spaces) into
    # single spaces so parsed paragraphs read cleanly.
    para_text = re.sub(r"\s+", " ", "".join(parts)).strip()
    return Paragraph(text=para_text, refs=refs, named_content=annotations)


def _parse_fig(fig_elem: etree._Element) -> list[Figure]:
    """Parse a <fig> element, including any nested child-fig elements.

    Returns a list: [main_figure, *child_figures].
    """
    fig = Figure()

    # Extract figure-level DOI from <object-id pub-id-type="doi">
    # (direct child of <fig>, or inside <media> for video figures)
    for oid in fig_elem.findall("object-id"):
        if oid.get("pub-id-type") == "doi" and oid.text:
            fig.doi = oid.text.strip()
            break
    if not fig.doi:
        media_elem = fig_elem.find("media")
        if media_elem is not None:
            for oid in media_elem.findall("object-id"):
                if oid.get("pub-id-type") == "doi" and oid.text:
                    fig.doi = oid.text.strip()
                    break

    label_elem = fig_elem.find("label")
    if label_elem is not None:
        fig.label = all_text(label_elem)

    p_parts: list[str] = []
    for caption_elem in fig_elem.findall("caption"):
        # Caption may have <title> and/or <p>
        title = caption_elem.find("title")
        if title is not None and not fig.caption:
            fig.caption = _inline_text(title).strip()
        for p in caption_elem.findall("p"):
            # When a <p> wraps a <list>, extract each list-item
            # as a separate caption paragraph so they match the
            # PMC text paragraph boundaries.
            list_elem = p.find("list")
            if list_elem is not None:
                for li in list_elem.findall("list-item"):
                    li_p = li.find("p")
                    if li_p is not None:
                        li_text = _inline_text(li_p).strip()
                        if li_text:
                            p_parts.append(li_text)
                    else:
                        li_text = all_text(li).strip()
                        if li_text:
                            p_parts.append(li_text)
                # Capture text after the list (tail + siblings)
                for lst in p.findall("list"):
                    tail = (lst.tail or "").strip()
                    if tail:
                        p_parts.append(tail)
            else:
                p_text = _inline_text(p).strip()
                if p_text:
                    p_parts.append(p_text)
    if fig.caption and p_parts:
        # Title goes in caption, body <p>s in caption_paragraphs
        fig.caption_paragraphs = p_parts
    elif p_parts and not fig.caption:
        # No title: first <p> is the caption, rest are body
        fig.caption = p_parts[0]
        fig.caption_paragraphs = p_parts[1:]

    # Some articles use <abstract abstract-type="fig_caption"> for a
    # translated caption (e.g. English translation of a Chinese caption).
    for abs_elem in fig_elem.findall("abstract"):
        if abs_elem.get("abstract-type") == "fig_caption":
            parts: list[str] = []
            title_el = abs_elem.find("title")
            if title_el is not None:
                parts.append(_inline_text(title_el).strip())
            parts.extend(
                _inline_text(p).strip() for p in abs_elem.findall("p") if _inline_text(p).strip()
            )
            if parts:
                if fig.caption:
                    fig.caption = f"{fig.caption}\n{parts[0]}"
                    fig.caption_paragraphs.extend(parts[1:])
                else:
                    fig.caption = parts[0]
                    fig.caption_paragraphs = parts[1:]
            break

    # Per-figure permissions (copyright/license statements)
    for perm in fig_elem.findall("permissions"):
        cs = perm.find("copyright-statement")
        if cs is not None:
            cs_text = all_text(cs).strip()
            if cs_text:
                fig.caption_paragraphs.append(cs_text)
        for lp in perm.findall("license/license-p"):
            lp_text = all_text(lp).strip()
            if lp_text:
                fig.caption_paragraphs.append(lp_text)

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
        href = graphic_elem.get("{http://www.w3.org/1999/xlink}href", "")
        if not href:
            href = graphic_elem.get("href", "")
        fig.graphic_url = href

    # Footnotes inside <fig>/<p>/<fn> or <fig>/<fn>
    fn_parts: list[str] = []
    for fn in fig_elem.findall(".//fn"):
        fn_text = all_text(fn).strip()
        if fn_text:
            fn_parts.append(fn_text)
    if fn_parts:
        fn_line = " ".join(fn_parts)
        if fig.caption:
            fig.caption = f"{fig.caption} {fn_line}"
        else:
            fig.caption = fn_line

    # <abstract> children inside <fig> (used by some publishers for
    # figure notes or multilingual captions)
    for ab in fig_elem.findall("abstract"):
        ab_parts = []
        for p in ab.findall("p"):
            ab_parts.append(_inline_text(p).strip())
        ab_text = " ".join(t for t in ab_parts if t)
        if ab_text:
            if fig.caption:
                fig.caption = f"{fig.caption} {ab_text}"
            else:
                fig.caption = ab_text

    # Direct <list> children of <fig> (not inside <caption>).
    # Some publishers put list items directly under <fig>.
    for list_elem in fig_elem.findall("list"):
        for item_elem in list_elem.findall("list-item"):
            item_text = all_text(item_elem).strip()
            if item_text:
                fig.caption_paragraphs.append(item_text)

    # Direct <table-wrap> children of <fig>.
    # Some publishers embed tables directly within a figure element.
    for tw in fig_elem.findall("table-wrap"):
        tw_table = _parse_table_wrap(tw)
        # Emit table label/caption as caption paragraph text
        tw_parts: list[str] = []
        if tw_table.label:
            tw_parts.append(tw_table.label)
        if tw_table.caption:
            tw_parts.append(tw_table.caption)
        if tw_parts:
            fig.caption_paragraphs.append(" ".join(tw_parts))
        for row in tw_table.rows:
            cells = [c.text.strip() for c in row if c.text.strip()]
            if cells:
                fig.caption_paragraphs.append(" ".join(cells))
        for foot_note in tw_table.foot_notes:
            if foot_note.strip():
                fig.caption_paragraphs.append(foot_note.strip())

    # Direct <p> children of <fig> (not inside <caption> or <abstract>).
    # Some publishers put extra text like "Reagents and conditions: ..."
    # as bare <p> elements within <fig>, after the <graphic>.
    child_figs: list[Figure] = []
    for p in fig_elem.findall("p"):
        # Extract nested child-fig elements (e.g. eLife figure
        # supplements) as separate Figure objects.
        nested = p.findall("fig")
        if nested:
            for nf in nested:
                child_figs.extend(_parse_fig(nf))
            # Include any remaining text in <p> outside the <fig>
            p_copy = deepcopy(p)
            for nf in p_copy.findall("fig"):
                p_copy.remove(nf)
            remaining = _inline_text(p_copy).strip()
            if remaining:
                fig.caption_paragraphs.append(remaining)
            continue
        # Skip <p> elements that contain only <fn> children (already
        # handled above) — check if all meaningful text is inside <fn>.
        fn_children = p.findall("fn")
        if fn_children:
            # If removing all <fn> leaves no text, skip this <p>
            p_copy = deepcopy(p)
            for fn in p_copy.findall("fn"):
                p_copy.remove(fn)
            if not all_text(p_copy).strip():
                continue
        p_text = _inline_text(p).strip()
        if p_text:
            fig.caption_paragraphs.append(p_text)

    return [fig] + child_figs


def _parse_standalone_graphic(graphic_elem: etree._Element) -> Figure:
    """Parse a standalone <graphic> outside <fig> into a Figure.

    These appear as inline images, equation images, or decorative graphics
    in some PMC articles.
    """
    fig = Figure()
    href = graphic_elem.get("{http://www.w3.org/1999/xlink}href", "")
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
    media_elem: etree._Element,
    section: Section,
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

    # Some articles use <abstract abstract-type="table_caption"> for a
    # translated caption (e.g. English translation of a Chinese caption).
    for abs_elem in tw_elem.findall("abstract"):
        if abs_elem.get("abstract-type") == "table_caption":
            tparts: list[str] = []
            title_el = abs_elem.find("title")
            if title_el is not None:
                tparts.append(_inline_text(title_el).strip())
            tparts.extend(
                _inline_text(p).strip() for p in abs_elem.findall("p") if _inline_text(p).strip()
            )
            if tparts:
                translated = " ".join(tparts)
                if table.caption:
                    table.caption = f"{table.caption}\n{translated}"
                else:
                    table.caption = translated
            break

    table_elems = tw_elem.findall("table")
    if not table_elems:
        # Table may be inside <alternatives> wrapper
        alt_table = tw_elem.find("alternatives/table")
        if alt_table is not None:
            table_elems = [alt_table]

    if table_elems:
        raw_rows: list[list[TableCell]] = []
        raw_spans: list[list[int]] = []

        def _collect_trs(
            parent: etree._Element,
            is_header: bool,
        ) -> None:
            for tr in parent.findall("tr"):
                cells, spans = _parse_table_row(tr, is_header=is_header)
                if cells:
                    raw_rows.append(cells)
                    raw_spans.append(spans)

        for table_elem in table_elems:
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
    # A foot may contain <fn> elements, bare <p> elements, or both.
    # Process all direct children in document order to capture everything.
    for foot in tw_elem.findall("table-wrap-foot"):
        for child in foot:
            child_tag = etree.QName(child.tag).localname if isinstance(child.tag, str) else ""
            if child_tag == "fn":
                fn_text = all_text(child)
                if fn_text:
                    table.foot_notes.append(fn_text)
            elif child_tag == "p":
                p_text = all_text(child)
                if p_text:
                    table.foot_notes.append(p_text)

    return table


def _formula_aware_text(elem: etree._Element) -> str:
    """Extract text from an element, handling inline-formulas properly.

    Like ``all_text()`` but uses ``_inline_formula_text()`` for any
    ``<inline-formula>`` descendants to avoid dumping LaTeX preamble
    noise from ``<tex-math>`` elements.  Falls back to ``all_text()``
    when no inline-formulas are present (fast path).
    """
    # Fast path: if no inline-formula descendants, use all_text directly.
    has_formula = False
    for _ in elem.iter("inline-formula"):
        has_formula = True
        break
    if not has_formula:
        return all_text(elem)

    # Slow path: walk children, using _inline_formula_text for formulas.
    return _formula_aware_text_walk(elem)


def _formula_aware_text_walk(elem: etree._Element) -> str:
    """Recursively extract text from an element, handling inline-formulas."""
    parts: list[str] = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        tag = etree.QName(child.tag).localname if isinstance(child.tag, str) else ""
        if tag == "inline-formula":
            parts.append(_inline_formula_text(child))
        else:
            parts.append(_formula_aware_text_walk(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts).strip()


def _parse_table_row(
    tr_elem: etree._Element,
    is_header: bool,
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
        tag = etree.QName(child.tag).localname if isinstance(child.tag, str) else ""
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
            # Preserve paragraph boundaries in multi-<p> cells.
            # Use _inline_text to retain formatting (italic, sup, sub).
            p_children = child.findall("p")
            if p_children:
                parts = [_inline_text(p).strip() for p in p_children]
                cell_text = "\n".join(t for t in parts if t)
            else:
                cell_text = _inline_text(child).strip()
            cell = TableCell(
                text=cell_text,
                is_header=(tag == "th" or is_header),
                align=cell_align,
            )
            cells.append(cell)
            rowspans.append(rowspan)
            for _ in range(colspan - 1):
                cells.append(
                    TableCell(
                        text="",
                        is_header=(tag == "th" or is_header),
                        align=cell_align,
                    )
                )
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

    for _row_idx, (row, spans) in enumerate(zip(rows, row_spans)):
        expanded: list[TableCell] = []
        src_col = 0  # index into the original row
        out_col = 0  # index into the expanded row

        while src_col < len(row) or out_col in pending:
            if out_col in pending:
                remaining, orig_cell = pending[out_col]
                expanded.append(
                    TableCell(
                        text="",
                        is_header=orig_cell.is_header,
                    )
                )
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
            formula_text = formula_text[: -len(label)].strip()
        elif formula_text.startswith(label):
            formula_text = formula_text[len(label) :].strip()

    return Formula(text=formula_text, label=label)


def _extract_formula_text(elem: etree._Element) -> str:
    """Extract text from a formula element.

    Priority: clean tex-math > MathML (for preamble articles) > raw tex-math.
    PMC S3 uses MathML text when available, raw LaTeX otherwise.
    """
    # Check for <alternatives> wrapper
    alt = elem.find("alternatives")
    search_in = alt if alt is not None else elem

    # 1. Clean tex-math (no preamble) — most readable
    tex = search_in.find("tex-math")
    tex_content = ""
    if tex is not None:
        tex_content = text(tex).strip()
        if tex_content and "\\documentclass" not in tex_content:
            return tex_content

    # 2. MathML — for articles with preamble-only tex-math
    for ns_prefix in ("", "{http://www.w3.org/1998/Math/MathML}"):
        mml = search_in.find(f"{ns_prefix}math")
        if mml is not None:
            mml_text = all_text(mml).strip()
            if mml_text:
                return mml_text

    # 3. Raw tex-math (may contain preamble) — matches PMC S3
    if tex_content:
        return tex_content

    # 4. Fallback
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

    # Extract optional <title> child
    list_title = ""
    title_elem = list_elem.find("title")
    if title_elem is not None:
        list_title = all_text(title_elem).strip()

    items: list[str] = []
    for item_elem in list_elem.findall("list-item"):
        # Prepend explicit <label> if present (e.g., "1.", "a)")
        label_elem = item_elem.find("label")
        label_prefix = (
            all_text(label_elem).strip() + " "
            if (label_elem is not None and all_text(label_elem).strip())
            else ""
        )
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

    return ListBlock(items=items, ordered=ordered, title=list_title)


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
        tag = etree.QName(child.tag).localname if isinstance(child.tag, str) else ""
        if tag == "disp-formula":
            # Only skip content if it contains tex-math (LaTeX noise)
            if child.find(".//tex-math") is not None:
                pass  # skip LaTeX content, keep tail
            else:
                parts.append(all_text(child))
        elif tag == "inline-formula":
            parts.append(_inline_formula_text(child))
        elif tag in _INLINE_FMT:
            inner = _inline_text(child)
            if inner:
                parts.append(_wrap_inline(tag, inner))
        else:
            parts.append(all_text(child))
        if child.tail:
            parts.append(child.tail)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _parse_supplementary(elem: etree._Element, section: Section) -> None:
    """Parse <supplementary-material> into paragraphs and tables."""
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
        section.paragraphs.append(Paragraph(text=f"**{label}.** {caption_text}"))
    elif label:
        section.paragraphs.append(Paragraph(text=f"**{label}.**"))
    elif caption_text:
        section.paragraphs.append(Paragraph(text=caption_text))

    # Extract inline table-wrap elements within supplementary material
    for tw in elem.findall("table-wrap"):
        section.tables.append(_parse_table_wrap(tw))


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
            section.paragraphs.append(Paragraph(text=f"**{title_text}**"))
    for child in elem:
        tag = etree.QName(child.tag).localname if isinstance(child.tag, str) else ""
        if tag == "p":
            _collect_from_p(child, section)
        elif tag == "list":
            section.lists.append(_parse_list(child))
        elif tag == "sec":
            section.subsections.append(_parse_sec(child, level=2))
        elif tag in ("fig", "table-wrap", "disp-formula"):
            if tag == "fig":
                section.figures.extend(_parse_fig(child))
            elif tag == "table-wrap":
                section.tables.append(_parse_table_wrap(child))
            else:
                section.formulas.append(_parse_formula(child))
        elif tag == "fn-group":
            for fn in child.findall("fn"):
                _extract_fn_paragraphs(fn, section)
        elif tag == "def-list":
            _parse_def_list(child, section)
        elif tag == "glossary":
            _parse_glossary(child, section, emit_title=True)


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
    elem: etree._Element,
    section: Section,
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
                section.paragraphs.append(Paragraph(text=f"**{title_text}**"))
    for dl in elem.findall("def-list"):
        _parse_def_list(dl, section)
    for arr in elem.findall("array"):
        # <array> with <tbody>/<tr>/<td> rows — used for abbreviation tables
        items: list[str] = []
        for tr in arr.findall(".//tr"):
            cells = [all_text(td) for td in tr.findall("td") if all_text(td)]
            if cells:
                items.append("\t".join(cells))
        if items:
            section.paragraphs.append(Paragraph(text="\n".join(items)))
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

    # Check if <ack> title is a non-standard heading (e.g. COI disclosure)
    ack_title_elem = ack.find("title")
    ack_title = all_text(ack_title_elem) if ack_title_elem is not None else ""
    _ACK_TITLES = {"acknowledgments", "acknowledgements", "acknowledgment", "acknowledgement"}
    is_standard_ack = not ack_title or ack_title.lower().rstrip(":") in _ACK_TITLES

    parts: list[str] = []
    for p in ack.findall("./p"):
        p_text = all_text(p)
        if p_text:
            parts.append(p_text)

    # <sec> children within <ack> (author contributions, ethics, etc.)
    if ack_sections is not None:
        for sec in ack.findall("sec"):
            ack_sections.append(_parse_sec(sec, level=1))

    # Non-standard <ack> title: route entire content to back_matter
    if not is_standard_ack and ack_sections is not None:
        section = Section(heading=ack_title, level=1)
        for p_text in parts:
            section.paragraphs.append(Paragraph(text=p_text))
        if section.paragraphs or section.heading:
            ack_sections.insert(0, section)
        return ""

    return "\n\n".join(parts)


def _parse_appendices(root: etree._Element) -> list[Section]:
    """Extract appendices from back/app-group and standalone back/app."""
    sections: list[Section] = []
    back = root.find("back")
    if back is None:
        back = root.find(".//back")
    if back is None:
        return sections

    # Process ALL <app-group> elements (some articles have multiple).
    for app_group in back.findall("app-group"):
        for app in app_group.findall("app"):
            sections.append(_parse_single_app(app))

    # Also handle standalone <app> directly under <back> (without app-group)
    for app in back.findall("app"):
        section = _parse_single_app(app)
        if (
            section.heading
            or section.paragraphs
            or section.tables
            or section.figures
            or section.subsections
        ):
            sections.append(section)

    return sections


def _parse_single_app(app: etree._Element) -> Section:
    """Parse a single ``<app>`` element into a Section."""
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
        section.figures.extend(_parse_fig(fig))
    for list_elem in app.findall("list"):
        section.lists.append(_parse_list(list_elem))
    for boxed in app.findall("boxed-text"):
        _parse_boxed_text(boxed, section)
    for stmt in app.findall("statement"):
        for sp in stmt.findall("p"):
            section.paragraphs.append(_parse_paragraph(sp))
    for supp in app.findall("supplementary-material"):
        _parse_supplementary(supp, section)
    for fn_grp in app.findall("fn-group"):
        for fn in fn_grp.findall("fn"):
            fn_text = all_text(fn)
            if fn_text:
                section.notes.append(fn_text)
    return section


def _extract_fn_notes(fn: etree._Element, section: Section) -> None:
    """Extract notes from a ``<fn>`` element.

    When a ``<fn>`` has multiple ``<p>`` children, each ``<p>`` is
    emitted as a separate note (the first is typically a heading).
    A ``<label>`` prefix is prepended with a space separator.
    """
    p_elems = fn.findall("p")
    label_elem = fn.find("label")
    label_prefix = ""
    if label_elem is not None:
        label_text = all_text(label_elem).strip()
        if label_text:
            label_prefix = label_text + " "

    if len(p_elems) >= 2:
        for p in p_elems:
            p_text = all_text(p).strip()
            if p_text:
                section.notes.append(label_prefix + p_text)
                label_prefix = ""  # only prepend to first
    else:
        fn_text = all_text(fn).strip()
        if fn_text:
            section.notes.append(fn_text)


_FN_FIELD_ROUTES = {
    "author contributions": "author_contributions",
    "funding": "funding_statement",
    "data availability": "data_availability",
    "data and resource availability": "data_availability",
}


def _route_fn_to_fields(
    fn: etree._Element,
    fn_type: str,
    doc: Document | None,
) -> bool:
    """Route an ``<fn>`` to a dedicated Document field if recognisable.

    Detects footnotes by ``fn-type`` attribute (e.g. ``"con"``,
    ``"financial-disclosure"``) or by bold title text in the first
    ``<p>`` (e.g. ``"Author contributions"``, ``"Funding"``).

    Returns True if the footnote was consumed (caller should skip it).
    """
    if doc is None:
        return False

    # Route by fn-type
    if fn_type == "con":
        return False  # handled via con_map → Author.roles
    if fn_type == "financial-disclosure":
        # Extract text from <p> children (skip title <p>)
        texts = []
        for p in fn.findall("p"):
            t = all_text(p).strip()
            bold = p.find("bold")
            if bold is not None and t.lower().startswith(bold.text.lower()):
                continue  # skip title paragraph
            if t:
                texts.append(t)
        if texts and not doc.funding_statement:
            doc.funding_statement = "\n\n".join(texts)
        return True

    # Route by bold title in first <p>
    paras = fn.findall("p")
    if not paras:
        return False
    first_p = paras[0]
    bold = first_p.find("bold")
    if bold is None or not bold.text:
        return False
    title_lower = bold.text.strip().lower()

    field = _FN_FIELD_ROUTES.get(title_lower)
    if field is None:
        return False

    # Collect text from subsequent <p> elements (skip the title <p>)
    texts = []
    for p in paras[1:]:
        t = _inline_text(p).strip()
        if t:
            texts.append(t)
    content = "\n\n".join(texts)

    if field == "author_contributions":
        # Store as author_notes for now (will be in Author Notes section)
        if content and content not in doc.author_notes:
            doc.author_notes.append(content)
    elif field == "funding_statement":
        if content and not doc.funding_statement:
            doc.funding_statement = content
    elif field == "data_availability":
        if content and not doc.data_availability:
            doc.data_availability = content

    return True


def _extract_fn_paragraphs(fn: etree._Element, section: Section) -> None:
    """Extract paragraphs from a ``<fn>`` element.

    Like :func:`_extract_fn_notes` but stores content as paragraphs
    rather than footnotes.  Used for back-matter ``<fn-group>`` entries
    that are standalone statements (not inline footnotes).
    """
    p_elems = fn.findall("p")
    label_elem = fn.find("label")
    label_prefix = ""
    if label_elem is not None:
        label_text = all_text(label_elem).strip()
        if label_text:
            label_prefix = label_text + " "

    if p_elems:
        for p in p_elems:
            para = _parse_paragraph(p)
            p_text = para.text.strip()
            if p_text:
                para.text = label_prefix + p_text
                section.paragraphs.append(para)
                label_prefix = ""
    else:
        fn_text = all_text(fn).strip()
        if fn_text:
            section.paragraphs.append(Paragraph(text=fn_text))


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
        tag = etree.QName(child.tag).localname if isinstance(child.tag, str) else ""

        if tag == "sec":
            sections.append(_parse_sec(child, level=1))
        elif tag == "fn-group":
            section = Section(level=1)
            title_elem = child.find("title")
            if title_elem is not None:
                section.heading = all_text(title_elem)
            for fn in child.findall("fn"):
                fn_type = fn.get("fn-type", "")
                # Skip COI footnotes already captured in doc.competing_interests
                if fn_type in _COI_FN_TYPES:
                    continue
                # Detect bold-titled subsections and route to dedicated fields
                routed = _route_fn_to_fields(fn, fn_type, doc)
                if routed:
                    continue
                # Remaining notes go into the generic back-matter section
                _extract_fn_paragraphs(fn, section)
            if section.paragraphs:
                sections.append(section)
        elif tag == "notes":
            section = Section(level=1)
            title_elem = child.find("title")
            if title_elem is not None:
                section.heading = all_text(title_elem)
            # Direct <p> children only (not descendants inside nested notes)
            for p in child.findall("./p"):
                # If <p> contains a <list>, extract list items separately
                list_elem = p.find("list")
                if list_elem is not None:
                    # Text before the list
                    pre_parts = []
                    if p.text:
                        pre_parts.append(p.text.strip())
                    for sib in p:
                        if sib is list_elem:
                            break
                        pre_parts.append(all_text(sib).strip())
                        if sib.tail:
                            pre_parts.append(sib.tail.strip())
                    pre_text = " ".join(t for t in pre_parts if t)
                    if pre_text:
                        section.paragraphs.append(Paragraph(text=pre_text))
                    # List items as separate paragraphs
                    for li in list_elem.findall("list-item"):
                        li_text = all_text(li).strip()
                        if li_text:
                            section.paragraphs.append(Paragraph(text=li_text))
                else:
                    p_text = all_text(p)
                    if p_text:
                        section.paragraphs.append(Paragraph(text=p_text))
            # Direct <list> children (not inside <p>).
            for list_elem in child.findall("./list"):
                for li in list_elem.findall("list-item"):
                    li_text = all_text(li).strip()
                    if li_text:
                        section.paragraphs.append(Paragraph(text=li_text))
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
                section.subsections.append(_parse_sec(sub_sec_elem, level=2))
            # <def-list> children (abbreviation tables, etc.)
            for dl in child.findall("./def-list"):
                _parse_def_list(dl, section)
            # <fn-group> children inside <notes>
            for fg in child.findall("./fn-group"):
                for fn in fg.findall("fn"):
                    fn_type = fn.get("fn-type", "")
                    if fn_type in _COI_FN_TYPES:
                        continue
                    _extract_fn_paragraphs(fn, section)
            if section.paragraphs or section.heading or section.subsections or section.lists:
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
            if section.paragraphs or section.lists or section.heading:
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
    """Parse <floats-group> / <floats-wrap> for figures/tables outside body.

    In many PMC nXML files, figures and tables are placed in a
    <floats-group> or <floats-wrap> element that is a direct child
    of <article>, separate from <body> and <back>.
    """
    floats = root.find(".//floats-group")
    if floats is None:
        floats = root.find(".//floats-wrap")
    if floats is None:
        return

    for child in floats:
        tag = etree.QName(child.tag).localname if isinstance(child.tag, str) else ""

        if tag == "fig":
            doc.figures.extend(_parse_fig(child))
        elif tag == "fig-group":
            # Use _dispatch_group_container logic to handle
            # group-level label/caption propagation.
            dummy_sec = Section(level=1)
            _dispatch_group_container(
                child,
                tag,
                dummy_sec,
                1,
            )
            doc.figures.extend(dummy_sec.figures)
        elif tag == "table-wrap":
            doc.tables.append(_parse_table_wrap(child))
        elif tag == "table-wrap-group":
            # Use _dispatch_group_container logic to handle
            # group-level label/caption propagation.
            dummy_sec = Section(level=1)
            _dispatch_group_container(
                child,
                tag,
                dummy_sec,
                1,
            )
            doc.tables.extend(dummy_sec.tables)
        elif tag == "boxed-text":
            section = Section(level=1, is_boxed=True)
            # Use boxed-text title/caption as section heading so
            # it survives markdown roundtrip as a headed section.
            for t_tag in ("title", "label", "caption/title"):
                t_elem = child.find(t_tag)
                if t_elem is not None:
                    t_text = all_text(t_elem).strip()
                    if t_text:
                        section.heading = t_text
                        break
            _parse_boxed_text(child, section)
            # Remove duplicate bold title paragraph added by
            # _parse_boxed_text since we already used it as heading.
            if section.heading and section.paragraphs:
                bold_title = f"**{section.heading}**"
                section.paragraphs = [p for p in section.paragraphs if p.text != bold_title]
            if section.paragraphs or section.subsections or section.lists:
                doc.back_matter.append(section)


def _parse_bibliography(root: etree._Element) -> list[Reference]:
    """Extract references from back/ref-list/ref.

    Uses the direct ``<back>`` child to avoid picking up references
    from nested ``<sub-article>`` elements.  Also handles nested
    ``<ref-list>`` elements (e.g. annotated bibliography sections).
    """
    back = root.find("back")
    if back is None:
        # Fallback for non-standard structure
        back = root.find(".//back")
    if back is None:
        return []
    references: list[Reference] = []
    for ref_list in back.findall("ref-list"):
        # Direct refs
        for ref_elem in ref_list.findall("ref"):
            ref = _parse_ref(ref_elem, len(references) + 1)
            references.append(ref)
        # Nested ref-lists (annotated bibliographies)
        for sub_rl in ref_list.findall("ref-list"):
            title_elem = sub_rl.find("title")
            if title_elem is not None:
                title_text = all_text(title_elem).strip()
                if title_text:
                    # Emit the nested ref-list title as an
                    # annotation note reference so it appears in
                    # the plain-text output.
                    note_ref = Reference(
                        index=len(references) + 1,
                        comment=title_text,
                    )
                    references.append(note_ref)
            for ref_elem in sub_rl.findall("ref"):
                ref = _parse_ref(
                    ref_elem,
                    len(references) + 1,
                )
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
    citation: etree._Element,
    ref: Reference,
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
    citation: etree._Element,
    ref: Reference,
) -> None:
    """Extract editors from a citation element into *ref*."""
    editor_group = citation.find("person-group[@person-group-type='editor']")
    if editor_group is None:
        return
    for name_elem in editor_group.findall("name"):
        surname = text(name_elem.find("surname"))
        given = text(name_elem.find("given-names"))
        if surname:
            name = f"{surname} {given}" if given else surname
            ref.editors.append(name)


def _parse_ref_pages(
    citation: etree._Element,
    ref: Reference,
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
    citation: etree._Element,
    ref: Reference,
) -> None:
    """Extract identifiers and external links from a citation."""
    for pub_id_type, attr in (
        ("doi", "doi"),
        ("pmid", "pmid"),
        ("pmcid", "pmcid"),
    ):
        elem = citation.find(f"pub-id[@pub-id-type='{pub_id_type}']")
        if elem is not None:
            setattr(ref, attr, text(elem))

    for ext_link in citation.findall("ext-link"):
        href = ext_link.get("{http://www.w3.org/1999/xlink}href", "")
        if not href:
            href = ext_link.get("href", "")
        if href:
            ref.ext_links.append(href)

    # <uri> elements (URLs not wrapped in ext-link)
    for uri_elem in citation.findall("uri"):
        href = uri_elem.get("{http://www.w3.org/1999/xlink}href", "")
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
        # Fallback: some <ref> elements contain only <note> (e.g.
        # reference annotations like "•• of considerable interest").
        note = ref_elem.find("note")
        if note is not None:
            note_p = note.find("p")
            note_text = all_text(note_p) if note_p is not None else (all_text(note))
            if note_text:
                ref.comment = note_text
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
    for tag, attr in (("year", "year"), ("volume", "volume"), ("issue", "issue")):
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
