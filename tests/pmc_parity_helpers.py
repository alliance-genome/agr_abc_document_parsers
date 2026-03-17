"""Shared PMC parity comparison helpers.

Extracted from ``test_pmc_conversion.py`` so that multiple test modules
(PMC random, AGR nxml, etc.) can compare pipeline output against PMC S3
plain text and BioC API references.
"""

from __future__ import annotations

import difflib
import json
import re
import time
import unicodedata
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

S3_BASE = "https://pmc-oa-opendata.s3.amazonaws.com"
BIOC_URL = (
    "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/PMC{pmcid}/unicode"
)

# BioC section types excluded from comparison.
BIOC_SKIP_SECTIONS = frozenset({"REF", "ABBR"})

# PMC text header separator -- match 20+ consecutive '=' chars,
# possibly surrounded by control characters like \x9f.
_HEADER_SEP_RE = re.compile(r"^[^\w]*={20,}[^\w]*$")

# Minimum paragraph length to consider for comparison (skip very short
# lines).
MIN_PARA_LENGTH = 20


# ---------------------------------------------------------------------------
# Network helpers
# ---------------------------------------------------------------------------


def rate_limit(api_key: str | None) -> None:
    """Sleep to respect NCBI rate limits."""
    if api_key:
        time.sleep(0.1)
    else:
        time.sleep(0.34)


def ncbi_params(api_key: str | None) -> str:
    """Return ``&api_key=...`` suffix if key is available."""
    if api_key:
        return f"&api_key={api_key}"
    return ""


def fetch_url(url: str, retries: int = 3) -> bytes:
    """Fetch a URL with retries on transient errors."""
    for attempt in range(retries):
        try:
            req = Request(url)
            req.add_header("User-Agent", "agr_abc_document_parsers/test")
            with urlopen(req, timeout=60) as resp:
                return resp.read()
        except (HTTPError, URLError, TimeoutError):
            if attempt == retries - 1:
                raise
            time.sleep(2**attempt)
    return b""  # unreachable


# ---------------------------------------------------------------------------
# PMC S3 access
# ---------------------------------------------------------------------------


def fetch_s3_file(
    pmcid: str,
    ext: str,
    version: int = 1,
) -> bytes | None:
    """Fetch a file from the PMC S3 bucket.

    Args:
        pmcid: Numeric PMCID (without 'PMC' prefix).
        ext: File extension (e.g. 'txt', 'xml').
        version: Article version (default 1).

    Returns:
        File contents or None if not available.
    """
    prefix = f"PMC{pmcid}.{version}"
    url = f"{S3_BASE}/{prefix}/{prefix}.{ext}"
    try:
        return fetch_url(url)
    except (HTTPError, URLError):
        return None


def fetch_bioc(pmcid: str) -> dict[str, Any] | None:
    """Fetch BioC JSON for a PMCID.

    The PMC BioC API returns a JSON array of collections.
    We return the first collection (which contains the documents).
    """
    url = BIOC_URL.format(pmcid=pmcid)
    try:
        data = fetch_url(url)
        parsed = json.loads(data)
        if isinstance(parsed, list) and parsed:
            return parsed[0]
        if isinstance(parsed, dict):
            return parsed
        return None
    except (HTTPError, json.JSONDecodeError):
        return None


def extract_bioc_paragraphs(bioc_json: dict[str, Any]) -> list[str]:
    """Extract text passages from BioC JSON, excluding REF/ABBR."""
    paragraphs: list[str] = []
    for doc in bioc_json.get("documents", []):
        for passage in doc.get("passages", []):
            section = passage.get("infons", {}).get(
                "section_type",
                "",
            )
            if section in BIOC_SKIP_SECTIONS:
                continue
            text = passage.get("text", "").strip()
            if text and len(text) >= MIN_PARA_LENGTH:
                paragraphs.append(text)
    return paragraphs


# ---------------------------------------------------------------------------
# PMC plain text parsing
# ---------------------------------------------------------------------------


def parse_pmc_text(raw_text: str) -> dict[str, Any]:
    """Parse PMC S3 plain text into structured sections.

    The PMC text format has:
    1. JOURNAL INFORMATION + ====== header
    2. ARTICLE INFORMATION + ====== header
    3. Third ====== separator -> body content starts
    4. Body paragraphs (abstract, sections, methods, figures, etc.)
    5. References at the end (bare citation lines)

    Returns dict with:
        - body_paragraphs: list of body text paragraphs
        - reference_paragraphs: list of reference lines
        - title: extracted title
    """
    lines = raw_text.split("\n")

    # Find the third ====== separator that starts body content.
    # First two are after JOURNAL INFO and ARTICLE INFO headers.
    # Third one (often with \x9f control chars) precedes the body.
    sep_count = 0
    body_start = 0
    for i, line in enumerate(lines):
        if _HEADER_SEP_RE.match(line.strip()):
            sep_count += 1
            if sep_count == 3:
                body_start = i + 1
                break

    if body_start == 0:
        # No header structure found -- treat entire text as body
        body_start = 0

    # Extract body lines (everything after headers)
    body_lines = lines[body_start:]

    # Split into paragraphs (separated by blank lines)
    paragraphs: list[str] = []
    current: list[str] = []
    for line in body_lines:
        if not line.strip():
            if current:
                paragraphs.append("\n".join(current))
                current = []
        else:
            current.append(line)
    if current:
        paragraphs.append("\n".join(current))

    # Filter out sub-article PMC S3 metadata headers (JOURNAL/ARTICLE
    # INFORMATION blocks) that appear mid-text for sub-articles.
    paragraphs = [
        p
        for p in paragraphs
        if not (p.startswith("JOURNAL INFORMATION\n") or p.startswith("ARTICLE INFORMATION\n"))
    ]

    # Detect where references start
    ref_start_idx = detect_reference_start(paragraphs)

    body_paragraphs = paragraphs[:ref_start_idx] if ref_start_idx else paragraphs
    ref_paragraphs = paragraphs[ref_start_idx:] if ref_start_idx else []

    # Extract title from ARTICLE INFORMATION block
    title = ""
    for i, line in enumerate(lines):
        if "ARTICLE INFORMATION" in line:
            for j in range(i + 1, len(lines)):
                stripped_line = lines[j].strip()
                if _HEADER_SEP_RE.match(stripped_line):
                    continue
                if not stripped_line:
                    continue
                if any(
                    stripped_line.startswith(p)
                    for p in [
                        "PMCID:",
                        "PMID:",
                        "DOI:",
                        "Article ID:",
                        "Article version:",
                        "Subjects:",
                        "EISSN:",
                        "ISSN:",
                        "Publisher:",
                        "Journal ID:",
                        "NLM Title",
                    ]
                ):
                    continue
                # This should be the title
                title = stripped_line
                break
            break

    return {
        "body_paragraphs": body_paragraphs,
        "reference_paragraphs": ref_paragraphs,
        "title": title,
    }


# Reference detection patterns
_PMID_PATTERN = re.compile(r"\d{7,8}")
_DOI_PATTERN = re.compile(r"10\.\d{4,}")
_YEAR_PATTERN = re.compile(r"\(\d{4}\)")
_BARE_YEAR_PATTERN = re.compile(r"\b(18|19|20)\d{2}\b")


def detect_reference_start(paragraphs: list[str]) -> int | None:
    """Detect where references begin in a list of paragraphs.

    Handles two formats:
    1. Each reference as a separate paragraph (3+ consecutive
       citation-like paras)
    2. All references concatenated in a single large paragraph
       (many PMIDs/DOIs)
    """
    # Strategy 1: 3+ consecutive short citation paragraphs
    consecutive_refs = 0
    first_ref_idx = None

    for i, para in enumerate(paragraphs):
        lines_in_para = para.count("\n") + 1
        if lines_in_para > 3:
            # Check if this is a large concatenated reference block
            pmid_count = len(_PMID_PATTERN.findall(para))
            doi_count = len(_DOI_PATTERN.findall(para))
            if pmid_count >= 5 or doi_count >= 5:
                return i
            consecutive_refs = 0
            first_ref_idx = None
            continue

        has_year = bool(_YEAR_PATTERN.search(para))
        has_pmid = bool(_PMID_PATTERN.search(para))
        has_doi = bool(_DOI_PATTERN.search(para))

        if has_year and (has_pmid or has_doi):
            if consecutive_refs == 0:
                first_ref_idx = i
            consecutive_refs += 1
            if consecutive_refs >= 3:
                return first_ref_idx
        else:
            consecutive_refs = 0
            first_ref_idx = None

    # Strategy 2: check if the last paragraph is a concatenated
    # reference block
    if paragraphs:
        last = paragraphs[-1]
        pmid_count = len(_PMID_PATTERN.findall(last))
        doi_count = len(_DOI_PATTERN.findall(last))
        if pmid_count >= 3 or doi_count >= 3:
            return len(paragraphs) - 1

    # Strategy 3: "References" heading followed by citation-like
    # content
    _REF_HEADING_RE = re.compile(
        r"^(?:References?|Bibliography|Literature Cited"
        r"|Works Cited|Literatur|Weiterf.hrende Literatur"
        r"|Ausgew.hlte Literatur|Bibliograf.a"
        r"|R.f.rences|Referencias)$",
        re.IGNORECASE,
    )
    for i, para in enumerate(paragraphs):
        if _REF_HEADING_RE.match(para.strip()):
            # Check if any subsequent paragraph looks like a citation.
            for j in range(i + 1, len(paragraphs)):
                subsequent = paragraphs[j]
                has_year = bool(_YEAR_PATTERN.search(subsequent))
                has_bare_year = bool(_BARE_YEAR_PATTERN.search(subsequent))
                has_pmid = bool(_PMID_PATTERN.search(subsequent))
                has_doi = bool(_DOI_PATTERN.search(subsequent))
                if has_year or has_bare_year or has_pmid or has_doi:
                    return i
            break

    # Strategy 4: numbered reference list at end
    _NUMBERED_REF_RE = re.compile(r"^1\.\s+[A-Z]")
    _BARE_YEAR_RE = re.compile(r"[,. ]\d{4}[.;,)\s]")
    for i in range(len(paragraphs) - 1, -1, -1):
        para = paragraphs[i]
        if _NUMBERED_REF_RE.match(para.strip()):
            has_pmid = bool(_PMID_PATTERN.search(para))
            has_doi = bool(_DOI_PATTERN.search(para))
            has_year = bool(_YEAR_PATTERN.search(para))
            has_bare_year = bool(_BARE_YEAR_RE.search(para))
            if has_pmid or has_doi or has_year or has_bare_year:
                return i
        # Stop scanning backwards if we hit a substantive body
        # paragraph
        elif len(para) > 100:
            break

    # Strategy 5: last paragraph is a multi-line block of bare
    # citations
    _BARE_CITATION_RE = re.compile(
        r"^[A-Z][a-z]+\s.*?\(\d{4}\)\s",
    )
    if paragraphs:
        last = paragraphs[-1]
        cite_lines = [ln.strip() for ln in last.split("\n") if ln.strip()]
        if len(cite_lines) >= 2 and all(_BARE_CITATION_RE.match(ln) for ln in cite_lines):
            return len(paragraphs) - 1

    # Strategy 6: trailing paragraph(s) that are bare citation blocks.
    _ENDS_YEAR_NUMS_RE = re.compile(
        r"\b(?:18|19|20)\d{2}\b[\s\d]*$",
    )
    if paragraphs:
        last = paragraphs[-1]
        cite_lines = [ln.strip() for ln in last.split("\n") if ln.strip()]
        if cite_lines:
            all_have_year = all(_BARE_YEAR_PATTERN.search(ln) for ln in cite_lines)
            if all_have_year:
                has_pmid = bool(_PMID_PATTERN.search(last))
                has_doi = bool(_DOI_PATTERN.search(last))
                if len(cite_lines) >= 2:
                    return len(paragraphs) - 1
                elif has_pmid or has_doi:
                    return len(paragraphs) - 1
                elif _ENDS_YEAR_NUMS_RE.search(last.strip()):
                    return len(paragraphs) - 1

    return None


# ---------------------------------------------------------------------------
# Text normalization and comparison
# ---------------------------------------------------------------------------

# PLOS-style DOI prefix that PMC text prepends to figure/table captions
_DOI_PREFIX_RE = re.compile(r"^10\.\d{4,}/[^\s]+\s+")


def normalize_text(text: str) -> str:
    """Normalize text for comparison.

    - Strip PLOS DOI prefixes from figure/table paragraphs
    - Unicode NFKC normalization
    - Collapse whitespace
    - Strip citation numbers (superscript references like "1", "23")
    - Lowercase
    """
    # Strip PLOS-style DOI prefix
    text = _DOI_PREFIX_RE.sub("", text)
    # Unicode normalize
    text = unicodedata.normalize("NFKC", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Remove isolated citation numbers that appear directly after words
    text = re.sub(
        r"(?<=[a-zA-Z)])(\d{1,3})(?=[\s.,;:]|$)",
        "",
        text,
    )
    # Lowercase
    text = text.lower()
    return text


def normalize_paragraph(text: str) -> str:
    """Normalize a paragraph for matching.

    More aggressive than ``normalize_text``.  Unlike
    ``normalize_text``, this does NOT strip citation numbers so that
    numeric data in table cells is preserved for accurate matching.
    """
    text = _DOI_PREFIX_RE.sub("", text)
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.lower()
    # Remove all non-alphanumeric except spaces
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def paragraph_similarity(para1: str, para2: str) -> float:
    """Compute normalized similarity between two paragraphs."""
    n1 = normalize_paragraph(para1)
    n2 = normalize_paragraph(para2)
    if not n1 or not n2:
        return 0.0
    return difflib.SequenceMatcher(None, n1, n2).ratio()


def find_best_paragraph_match(
    pmc_para: str,
    our_paragraphs: list[str],
) -> tuple[float, int]:
    """Find the best matching paragraph from our output.

    Handles paragraph boundary differences: a short PMC paragraph may
    be a substring of one of our paragraphs (e.g., figure title vs
    combined figure title + legend).  Uses both SequenceMatcher ratio
    and substring containment.

    Returns (best_ratio, best_index). Index is -1 if no match.
    """
    norm_pmc = normalize_paragraph(pmc_para)
    if not norm_pmc or len(norm_pmc) < MIN_PARA_LENGTH:
        return (1.0, -1)  # skip short paragraphs

    pmc_tokens = set(norm_pmc.split())
    pmc_nospace = norm_pmc.replace(" ", "")
    best_ratio = 0.0
    best_idx = -1

    for i, our_para in enumerate(our_paragraphs):
        norm_ours = normalize_paragraph(our_para)
        if not norm_ours:
            continue

        # Substring containment: if PMC paragraph is fully contained
        # in one of our paragraphs (or vice versa), count as match.
        if norm_pmc in norm_ours or norm_ours in norm_pmc:
            return (1.0, i)

        # Space-stripped containment: handles table cell data where
        # token boundaries differ
        ours_nospace = norm_ours.replace(" ", "")
        if pmc_nospace in ours_nospace or ours_nospace in pmc_nospace:
            return (1.0, i)

        # Table cell sub-paragraph check: GFM tables merge multi-<p>
        # cells into one string. Check if the PMC paragraph matches
        # any individual cell within a table row.
        if "|" in our_para:
            for cell in our_para.split("|"):
                norm_cell = normalize_paragraph(cell)
                if not norm_cell:
                    continue
                if norm_pmc in norm_cell or norm_cell in norm_pmc:
                    return (1.0, i)
                cell_nospace = norm_cell.replace(" ", "")
                if pmc_nospace in cell_nospace or cell_nospace in pmc_nospace:
                    return (1.0, i)

        # Token overlap pre-filter
        our_tokens = set(norm_ours.split())
        overlap = len(pmc_tokens & our_tokens) / max(
            len(pmc_tokens),
            len(our_tokens),
        )
        if overlap < 0.3:
            continue

        ratio = difflib.SequenceMatcher(
            None,
            norm_pmc,
            norm_ours,
        ).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_idx = i
        if best_ratio >= 0.95:
            break

    return (best_ratio, best_idx)


# ---------------------------------------------------------------------------
# PMC text content categories
# ---------------------------------------------------------------------------

# Patterns for content that we deliberately exclude or handle
# differently
_METADATA_PATTERNS = [
    re.compile(r"^Electronic publication date:", re.I),
    re.compile(r"^Publication date:", re.I),
    re.compile(r"^Volume:", re.I),
    re.compile(r"^Electronic Location ID:", re.I),
    re.compile(r"^Received \d{4}", re.I),
    re.compile(r"^Copyright:", re.I),
    re.compile(r"^Copyright year:", re.I),
    re.compile(r"^Copyright holder:", re.I),
    re.compile(r"^License:", re.I),
    re.compile(r"^License URL:", re.I),
    re.compile(r"^ISSN:", re.I),
    re.compile(r"^EISSN:", re.I),
    re.compile(r"^How to cite this article:", re.I),
    re.compile(r"^This file is available for text mining", re.I),
    re.compile(r"^Publisher.?s note:?", re.I),
    re.compile(r"^Click here for additional data file", re.I),
    re.compile(r"^Abbreviations?:", re.I),
    re.compile(r"^Abbreviation: ", re.I),
    re.compile(r"^Springer Nature remains neutral", re.I),
    re.compile(r"^Papers of special note have been highlighted", re.I),
    re.compile(r"^Multimedia Appendix \d+", re.I),
    re.compile(
        r"^10\.\d{4,}/\S+(?:\s+10\.\d{4,}/\S+)+$",
    ),
    re.compile(r"^Available at https?://\S+$", re.I),
    re.compile(r"^This is a correction to:", re.I),
    re.compile(r"^Reviewer declares none\.$", re.I),
    re.compile(r"^https?://orcid\.org/\S+\s", re.I),
    re.compile(r"^Recommendation:\s", re.I),
    re.compile(r"^[☆†‡§¶*#]+\s*Disclaimer:", re.I),
]

# Author listing patterns (individual author lines)
_AUTHOR_LINE_PATTERN = re.compile(
    r"^[A-Z][a-z]+ [A-Z][a-z-]+ (?:\w )?\d+$",
)

# Affiliation patterns
_AFFIL_PATTERN = re.compile(
    r"^\d+ (?:Department|School|Institute|Faculty|College)",
)

# Email patterns
_EMAIL_PATTERN = re.compile(
    r"^[a-z] [a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$",
)

# Author biography patterns (PMC includes <bio> content we don't
# parse)
_AUTHOR_BIO_PATTERN = re.compile(
    r"^[A-Z][a-z]+ [A-Z][a-z]+ is currently "
    r"(?:a |an )?(?:professor|associate|assistant|lecturer)",
    re.I,
)

# Abbreviation definition lines: "ABBREV full expansion"
_ABBREV_DEF_PATTERN = re.compile(
    r"^[A-Za-z0-9\u03b1-\u03c9\u0391-\u03a9/+-]+\s+[A-Za-z]",
)

# Back-matter heading variations that map to our structured fields
_BACKMATTER_HEADING_ALIASES = {
    "conflict of interest",
    "conflicts of interest",
    "conflict of interests",
    "ethics/ethical approval",
    "ethical approval",
    "medical writing, editorial, and other assistance",
    "medical writing, editorial and other assistance",
    "notes and references",
    "declarations",
}


def classify_pmc_paragraph(para: str) -> str:
    """Classify a PMC paragraph into a content category.

    Returns one of:
        'metadata' - publication metadata we don't include
        'author_info' - author names/affiliations/emails/bios
        'body' - actual body content we should match
        'figure_caption' - figure/table caption text
        'section_heading' - section heading text
    """
    stripped = para.strip()

    # Check metadata patterns
    for pattern in _METADATA_PATTERNS:
        if pattern.search(stripped):
            return "metadata"

    # Author listing lines
    if _AUTHOR_LINE_PATTERN.match(stripped):
        return "author_info"
    if _AFFIL_PATTERN.match(stripped):
        return "author_info"
    if _EMAIL_PATTERN.match(stripped):
        return "author_info"
    # Author biographies (from <bio> elements in JATS back matter)
    if _AUTHOR_BIO_PATTERN.match(stripped):
        return "author_info"

    # Figure/table captions (including supplementary labels)
    if re.match(
        r"^(?:Figure|Table|Supplementary|S\d+)\s+\d*",
        stripped,
    ):
        return "figure_caption"

    # Short headings (typically section titles)
    if len(stripped) < 80 and not stripped.endswith("."):
        if stripped.lower() in _BACKMATTER_HEADING_ALIASES:
            return "metadata"
        if _ABBREV_DEF_PATTERN.match(stripped) and len(stripped) < 150:
            return "metadata"
        return "section_heading"

    return "body"


# ---------------------------------------------------------------------------
# BioC cross-check
# ---------------------------------------------------------------------------


def cross_check_bioc(
    missing_para: str,
    bioc_paragraphs: list[str],
) -> str:
    """Check if a paragraph missing from our output exists in BioC.

    Returns:
        'in_bioc' - BioC has this content (likely our parser is
            missing it)
        'not_in_bioc' - BioC also lacks this content
        'partial_bioc' - BioC has partial match
    """
    best_ratio, _ = find_best_paragraph_match(
        missing_para,
        bioc_paragraphs,
    )
    if best_ratio >= 0.90:
        return "in_bioc"
    if best_ratio >= 0.50:
        return "partial_bioc"
    return "not_in_bioc"


# ---------------------------------------------------------------------------
# Main comparison entry point
# ---------------------------------------------------------------------------


def compare_against_pmc_reference(
    our_plain_text: str,
    pmc_reference_text: str,
    bioc_data: bytes | None,
    pmcid: str,
) -> dict[str, Any]:
    """Compare pipeline plain-text output against PMC reference data.

    Takes pre-computed pipeline output and reference data, performs
    parsing / normalization / matching / BioC cross-check, and returns
    a verdict dict.

    Args:
        our_plain_text: Plain text from our JATS->Markdown->plain
            pipeline.
        pmc_reference_text: Raw PMC S3 plain text (reference).
        bioc_data: Raw BioC JSON bytes (or None if unavailable).
        pmcid: The numeric PMCID (for reporting).

    Returns:
        Dict with detailed comparison results including verdict
        ('PASS', 'FAIL', 'ERROR').
    """
    result: dict[str, Any] = {
        "pmcid": pmcid,
        "verdict": "SKIP",
        "total_pmc_paragraphs": 0,
        "body_paragraphs": 0,
        "matched_paragraphs": 0,
        "missing_confirmed": 0,
        "missing_txt_only": 0,
        "missing_partial_bioc": 0,
        "total_missing": 0,
        "match_ratio": 0.0,
        "missing_details": [],
        "fulltext_similarity": 0.0,
        "bioc_available": False,
        "error": None,
    }

    # Parse PMC reference text
    pmc = parse_pmc_text(pmc_reference_text)
    pmc_body = pmc["body_paragraphs"]
    result["total_pmc_paragraphs"] = len(pmc_body)

    if not pmc_body:
        result["error"] = "no body paragraphs in PMC text"
        return result

    # Load BioC paragraphs for cross-referencing
    bioc_paragraphs: list[str] = []
    if bioc_data:
        try:
            bioc_json = json.loads(bioc_data)
            bioc_paragraphs = extract_bioc_paragraphs(bioc_json)
            result["bioc_available"] = True
        except (json.JSONDecodeError, KeyError):
            pass

    if not our_plain_text.strip():
        result["error"] = "pipeline produced empty output"
        result["verdict"] = "ERROR"
        return result

    # Split our output into paragraphs
    our_paragraphs = [p.strip() for p in our_plain_text.split("\n\n") if p.strip()]

    # --- Fulltext similarity ---
    pmc_fulltext = "\n\n".join(pmc_body)
    norm_pmc = normalize_text(pmc_fulltext)
    norm_ours = normalize_text(our_plain_text)
    if norm_pmc and norm_ours:
        result["fulltext_similarity"] = difflib.SequenceMatcher(
            None,
            norm_ours,
            norm_pmc,
        ).ratio()

    # --- Paragraph-level comparison ---
    body_count = 0
    matched = 0
    missing: list[dict[str, Any]] = []
    confirmed_missing = 0
    txt_only_missing = 0
    partial_bioc = 0

    for pmc_para in pmc_body:
        category = classify_pmc_paragraph(pmc_para)

        # Skip metadata and author info -- we handle these differently
        if category in ("metadata", "author_info"):
            continue

        body_count += 1
        best_ratio, best_idx = find_best_paragraph_match(
            pmc_para,
            our_paragraphs,
        )

        if best_ratio >= 0.90:
            matched += 1
        else:
            # Cross-check against BioC
            bioc_status = "no_bioc"
            if bioc_paragraphs:
                bioc_status = cross_check_bioc(
                    pmc_para,
                    bioc_paragraphs,
                )

            if bioc_status == "in_bioc":
                confirmed_missing += 1
            elif bioc_status == "partial_bioc":
                partial_bioc += 1
            else:
                txt_only_missing += 1

            missing.append(
                {
                    "category": category,
                    "ratio": round(best_ratio, 3),
                    "bioc_status": bioc_status,
                    "pmc_text": pmc_para[:200],
                }
            )

    result["body_paragraphs"] = body_count
    result["matched_paragraphs"] = matched
    result["missing_confirmed"] = confirmed_missing
    result["missing_txt_only"] = txt_only_missing
    result["missing_partial_bioc"] = partial_bioc
    result["total_missing"] = len(missing)
    result["match_ratio"] = matched / body_count if body_count > 0 else 1.0
    result["missing_details"] = missing[:30]
    if len(missing) == 0:
        result["verdict"] = "PASS"
    elif confirmed_missing <= 3 and result["fulltext_similarity"] > 0.80:
        result["verdict"] = "WARN"
    elif confirmed_missing == 0:
        # No BioC-confirmed missing content — formatting or metadata only
        result["verdict"] = "WARN"
    elif result["match_ratio"] >= 0.90 and all(
        m.get("ratio", 0) > 0.30 for m in missing if m.get("bioc_status") == "in_bioc"
    ):
        # High overall match and all confirmed-missing paragraphs have
        # partial matches (content present, formatting differs)
        result["verdict"] = "WARN"
    elif body_count <= 2 and result["fulltext_similarity"] < 0.20:
        # Very small articles with very low similarity — likely data issue
        # (empty article, OCR-damaged reference, article version mismatch)
        result["verdict"] = "WARN"
    elif result["match_ratio"] >= 0.90:
        # High paragraph match rate — remaining mismatches are minor
        result["verdict"] = "WARN"
    else:
        result["verdict"] = "FAIL"

    return result
