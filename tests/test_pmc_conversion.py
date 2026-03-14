"""PMC content parity tests — compare JATS→Markdown pipeline against PMC S3 plain text.

Marked with ``@pytest.mark.webtest`` and excluded from default test runs.
Run manually with::

    pytest -m webtest --count=10 -v

Requires network access to PMC S3 bucket (pmc-oa-opendata.s3.amazonaws.com).
No AWS account or API key needed — the bucket is publicly accessible.
"""
from __future__ import annotations

import difflib
import json
import os
import random
import re
import time
import unicodedata
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest

from agr_abc_document_parsers.jats_parser import parse_jats
from agr_abc_document_parsers.md_emitter import emit_markdown
from agr_abc_document_parsers.md_reader import read_markdown
from agr_abc_document_parsers.plain_text import extract_plain_text

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CACHE_DIR = Path(__file__).parent / ".pmcdata"
_FIXED_ARTICLES = Path(__file__).parent / "pmc_fixed_articles.txt"

_S3_BASE = "https://pmc-oa-opendata.s3.amazonaws.com"
_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
_BIOC_URL = (
    "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/"
    "pmcoa.cgi/BioC_json/PMC{pmcid}/unicode"
)

# PMC text header separator — match 20+ consecutive '=' chars,
# possibly surrounded by control characters like \x9f.
_HEADER_SEP_RE = re.compile(r"^[^\w]*={20,}[^\w]*$")

# Minimum paragraph length to consider for comparison (skip very short lines)
_MIN_PARA_LENGTH = 20


# ---------------------------------------------------------------------------
# Network helpers
# ---------------------------------------------------------------------------


def _rate_limit(api_key: str | None) -> None:
    """Sleep to respect NCBI rate limits."""
    if api_key:
        time.sleep(0.1)
    else:
        time.sleep(0.34)


def _ncbi_params(api_key: str | None) -> str:
    """Return ``&api_key=...`` suffix if key is available."""
    if api_key:
        return f"&api_key={api_key}"
    return ""


def _fetch_url(url: str, retries: int = 3) -> bytes:
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
            time.sleep(2 ** attempt)
    return b""  # unreachable


# ---------------------------------------------------------------------------
# PMC S3 access
# ---------------------------------------------------------------------------


def _find_latest_version(pmcid: str) -> str | None:
    """Find the latest version of a PMC article on S3.

    Tries versions 1-5 and returns the highest available.
    """
    # Most articles are version 1; try that first
    for version in range(1, 6):
        prefix = f"PMC{pmcid}.{version}"
        url = f"{_S3_BASE}/{prefix}/{prefix}.txt"
        try:
            req = Request(url, method="HEAD")
            req.add_header("User-Agent", "agr_abc_document_parsers/test")
            with urlopen(req, timeout=15):
                latest = prefix
        except (HTTPError, URLError, TimeoutError):
            break
    return latest if "latest" in dir() else None  # noqa: F841


def _fetch_s3_file(pmcid: str, ext: str, version: int = 1) -> bytes | None:
    """Fetch a file from the PMC S3 bucket.

    Args:
        pmcid: Numeric PMCID (without 'PMC' prefix).
        ext: File extension (e.g. 'txt', 'xml').
        version: Article version (default 1).

    Returns:
        File contents or None if not available.
    """
    prefix = f"PMC{pmcid}.{version}"
    url = f"{_S3_BASE}/{prefix}/{prefix}.{ext}"
    try:
        return _fetch_url(url)
    except (HTTPError, URLError):
        return None


def _fetch_bioc(pmcid: str) -> dict[str, Any] | None:
    """Fetch BioC JSON for a PMCID.

    The PMC BioC API returns a JSON array of collections.
    We return the first collection (which contains the documents).
    """
    url = _BIOC_URL.format(pmcid=pmcid)
    try:
        data = _fetch_url(url)
        parsed = json.loads(data)
        if isinstance(parsed, list) and parsed:
            return parsed[0]
        if isinstance(parsed, dict):
            return parsed
        return None
    except (HTTPError, json.JSONDecodeError):
        return None


# BioC section types excluded from comparison.
_BIOC_SKIP_SECTIONS = frozenset({"REF", "ABBR"})


def _extract_bioc_paragraphs(bioc_json: dict[str, Any]) -> list[str]:
    """Extract text passages from BioC JSON, excluding REF/ABBR sections."""
    paragraphs: list[str] = []
    for doc in bioc_json.get("documents", []):
        for passage in doc.get("passages", []):
            section = passage.get("infons", {}).get("section_type", "")
            if section in _BIOC_SKIP_SECTIONS:
                continue
            text = passage.get("text", "").strip()
            if text and len(text) >= _MIN_PARA_LENGTH:
                paragraphs.append(text)
    return paragraphs


def _fetch_random_pmcids(count: int, api_key: str | None) -> list[str]:
    """Fetch random Open Access PMCIDs using NCBI esearch."""
    params = (
        f"?db=pmc&term=open+access[filter]&rettype=count"
        f"&usehistory=n{_ncbi_params(api_key)}"
    )
    _rate_limit(api_key)
    data = _fetch_url(f"{_ESEARCH_URL}{params}")
    count_match = re.search(rb"<Count>(\d+)</Count>", data)
    if not count_match:
        return []
    total = int(count_match.group(1))

    pmcids: list[str] = []
    batch_size = min(count, 100)
    while len(pmcids) < count:
        retstart = random.randint(0, max(0, total - batch_size))
        needed = min(batch_size, count - len(pmcids))
        params = (
            f"?db=pmc&term=open+access[filter]&retmax={needed}"
            f"&retstart={retstart}&sort=pub_date"
            f"{_ncbi_params(api_key)}"
        )
        _rate_limit(api_key)
        data = _fetch_url(f"{_ESEARCH_URL}{params}")
        for m in re.finditer(rb"<Id>(\d+)</Id>", data):
            pmcid = m.group(1).decode()
            if pmcid not in pmcids:
                pmcids.append(pmcid)
                if len(pmcids) >= count:
                    break
    return pmcids


# ---------------------------------------------------------------------------
# Fixed articles
# ---------------------------------------------------------------------------


def _load_fixed_articles() -> list[str]:
    """Load PMCIDs from the fixed articles file."""
    if not _FIXED_ARTICLES.exists():
        return []
    pmcids: list[str] = []
    for line in _FIXED_ARTICLES.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pmcid = line.split("#")[0].split()[0]
        pmcids.append(pmcid)
    return pmcids


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------


def _ensure_cached(
    pmcid: str, api_key: str | None, refresh: bool = False,
) -> tuple[Path | None, Path | None, Path | None]:
    """Ensure XML, plain text, and BioC are cached for a PMCID.

    Downloads from PMC S3 bucket (no API key needed) for XML and TXT.
    Downloads from BioC API for BioC JSON.
    Falls back to NCBI efetch for XML if S3 doesn't have it.

    Returns (xml_path_or_None, txt_path_or_None, bioc_path_or_None).
    """
    cache = _CACHE_DIR / pmcid
    cache.mkdir(parents=True, exist_ok=True)
    xml_path = cache / "article.xml"
    txt_path = cache / "reference.txt"
    bioc_path = cache / "bioc.json"

    if refresh or not xml_path.exists():
        xml_data = _fetch_s3_file(pmcid, "xml")
        if xml_data:
            xml_path.write_bytes(xml_data)
        else:
            # Fallback to NCBI efetch
            efetch_url = (
                f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
                f"?db=pmc&id={pmcid}&rettype=xml&retmode=xml"
                f"{_ncbi_params(api_key)}"
            )
            _rate_limit(api_key)
            try:
                xml_data = _fetch_url(efetch_url)
                xml_path.write_bytes(xml_data)
            except (HTTPError, URLError):
                xml_path = None

    if refresh or not txt_path.exists():
        txt_data = _fetch_s3_file(pmcid, "txt")
        if txt_data:
            txt_path.write_bytes(txt_data)
        else:
            txt_path = None

    if refresh or not bioc_path.exists():
        bioc_data = _fetch_bioc(pmcid)
        if bioc_data:
            bioc_path.write_text(json.dumps(bioc_data), encoding="utf-8")
        else:
            bioc_path = None

    # Check paths exist
    if xml_path and not xml_path.exists():
        xml_path = None
    if txt_path and not txt_path.exists():
        txt_path = None
    if bioc_path and not bioc_path.exists():
        bioc_path = None

    return xml_path, txt_path, bioc_path


# ---------------------------------------------------------------------------
# PMC plain text parsing
# ---------------------------------------------------------------------------


def _parse_pmc_text(raw_text: str) -> dict[str, Any]:
    """Parse PMC S3 plain text into structured sections.

    The PMC text format has:
    1. JOURNAL INFORMATION + ====== header
    2. ARTICLE INFORMATION + ====== header
    3. Third ====== separator → body content starts
    4. Body paragraphs (abstract, sections, methods, figures, etc.)
    5. References at the end (bare citation lines)

    Returns dict with:
        - metadata_text: raw text before body
        - body_paragraphs: list of body text paragraphs
        - reference_paragraphs: list of reference lines
        - title: extracted title (first line after ARTICLE INFORMATION block)
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
        # No header structure found — treat entire text as body
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

    # Detect where references start
    # References are bare citation lines: "Author . Title. Journal Vol, Pages (Year).PMID DOI"
    # Heuristic: a sequence of 3+ consecutive paragraphs matching reference pattern
    ref_start_idx = _detect_reference_start(paragraphs)

    body_paragraphs = paragraphs[:ref_start_idx] if ref_start_idx else paragraphs
    ref_paragraphs = paragraphs[ref_start_idx:] if ref_start_idx else []

    # Extract title from ARTICLE INFORMATION block
    title = ""
    in_article_info = False
    for line in lines:
        if "ARTICLE INFORMATION" in line:
            in_article_info = True
            continue
        if in_article_info and _HEADER_SEP_RE.match(line.strip()):
            in_article_info = False
            continue
        if in_article_info:
            continue
        # After ARTICLE INFO block, first non-empty, non-metadata line before ======
        # is often the title. But it's in the section between author block and body.
        # We look for it differently...

    # Title is the first significant line in the ARTICLE INFORMATION section
    # that doesn't match metadata patterns (PMCID:, PMID:, DOI:, etc.)
    for i, line in enumerate(lines):
        if "ARTICLE INFORMATION" in line:
            for j in range(i + 1, len(lines)):
                stripped_line = lines[j].strip()
                if _HEADER_SEP_RE.match(stripped_line):
                    continue
                if not stripped_line:
                    continue
                if any(stripped_line.startswith(p) for p in [
                    "PMCID:", "PMID:", "DOI:", "Article ID:", "Article version:",
                    "Subjects:", "EISSN:", "ISSN:", "Publisher:", "Journal ID:",
                    "NLM Title",
                ]):
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


def _detect_reference_start(paragraphs: list[str]) -> int | None:
    """Detect where references begin in a list of paragraphs.

    Handles two formats:
    1. Each reference as a separate paragraph (3+ consecutive citation-like paras)
    2. All references concatenated in a single large paragraph (many PMIDs/DOIs)
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

    # Strategy 2: check if the last paragraph is a concatenated reference block
    if paragraphs:
        last = paragraphs[-1]
        pmid_count = len(_PMID_PATTERN.findall(last))
        doi_count = len(_DOI_PATTERN.findall(last))
        if pmid_count >= 3 or doi_count >= 3:
            return len(paragraphs) - 1

    return None


# ---------------------------------------------------------------------------
# Text normalization and comparison
# ---------------------------------------------------------------------------


# PLOS-style DOI prefix that PMC text prepends to figure/table captions
_DOI_PREFIX_RE = re.compile(r"^10\.\d{4,}/[^\s]+\s+")


def _normalize_text(text: str) -> str:
    """Normalize text for comparison.

    - Strip PLOS DOI prefixes from figure/table paragraphs
    - Unicode NFKC normalization
    - Collapse whitespace
    - Strip citation numbers (superscript references like "1", "23")
    - Lowercase
    """
    # Strip PLOS-style DOI prefix (e.g., "10.1371/journal.pbio.1001633.g001 Figure 1 ...")
    text = _DOI_PREFIX_RE.sub("", text)
    # Unicode normalize
    text = unicodedata.normalize("NFKC", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Remove isolated citation numbers that appear directly after words
    # e.g., "synaptic plasticity1" → "synaptic plasticity"
    # Only strip after letters (not after digits/periods to preserve "1.0", "4.53")
    text = re.sub(r"(?<=[a-zA-Z)])(\d{1,3})(?=[\s.,;:]|$)", "", text)
    # Lowercase
    text = text.lower()
    return text


def _normalize_paragraph(text: str) -> str:
    """Normalize a paragraph for matching — more aggressive than _normalize_text.

    Unlike ``_normalize_text``, this does NOT strip citation numbers so that
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


def _paragraph_similarity(para1: str, para2: str) -> float:
    """Compute normalized similarity between two paragraphs."""
    n1 = _normalize_paragraph(para1)
    n2 = _normalize_paragraph(para2)
    if not n1 or not n2:
        return 0.0
    return difflib.SequenceMatcher(None, n1, n2).ratio()


def _find_best_paragraph_match(
    pmc_para: str, our_paragraphs: list[str],
) -> tuple[float, int]:
    """Find the best matching paragraph from our output for a PMC paragraph.

    Handles paragraph boundary differences: a short PMC paragraph may be
    a substring of one of our paragraphs (e.g., figure title vs combined
    figure title + legend). Uses both SequenceMatcher ratio and substring
    containment.

    Returns (best_ratio, best_index). Index is -1 if no match.
    """
    norm_pmc = _normalize_paragraph(pmc_para)
    if not norm_pmc or len(norm_pmc) < _MIN_PARA_LENGTH:
        return (1.0, -1)  # skip short paragraphs

    pmc_tokens = set(norm_pmc.split())
    best_ratio = 0.0
    best_idx = -1

    for i, our_para in enumerate(our_paragraphs):
        norm_ours = _normalize_paragraph(our_para)
        if not norm_ours:
            continue

        # Substring containment: if PMC paragraph is fully contained
        # in one of our paragraphs (or vice versa), count as match.
        if norm_pmc in norm_ours or norm_ours in norm_pmc:
            return (1.0, i)

        # Space-stripped containment: handles table cell data where
        # token boundaries differ (e.g., "litersday 10" vs "litersday10")
        pmc_nospace = norm_pmc.replace(" ", "")
        ours_nospace = norm_ours.replace(" ", "")
        if pmc_nospace in ours_nospace or ours_nospace in pmc_nospace:
            return (1.0, i)

        # Token overlap pre-filter
        our_tokens = set(norm_ours.split())
        overlap = len(pmc_tokens & our_tokens) / max(len(pmc_tokens), len(our_tokens))
        if overlap < 0.3:
            continue

        ratio = difflib.SequenceMatcher(None, norm_pmc, norm_ours).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_idx = i
        if best_ratio >= 0.95:
            break

    return (best_ratio, best_idx)


# ---------------------------------------------------------------------------
# PMC text content categories (for classifying non-matching paragraphs)
# ---------------------------------------------------------------------------

# Patterns for content that we deliberately exclude or handle differently
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
    # Publisher neutrality statement (not behind "Publisher's note:" prefix)
    re.compile(r"^Springer Nature remains neutral", re.I),
    # Editorial markers
    re.compile(r"^Papers of special note have been highlighted", re.I),
    # Supplement descriptions in PMC text
    re.compile(r"^Multimedia Appendix \d+", re.I),
    # Publisher DOI identifiers repeated from <object-id> in <media> elements
    re.compile(r"^10\.\d{4,}/\S+(?:\s+10\.\d{4,}/\S+)+$"),
    # "Available at" URLs for peer review files (AME publisher artifact)
    re.compile(r"^Available at https?://\S+$", re.I),
    # Correction/erratum cross-references
    re.compile(r"^This is a correction to:", re.I),
    # Peer review declarations (short statements in sub-article metadata)
    re.compile(r"^Reviewer declares none\.$", re.I),
    # Peer review ORCID + reviewer info lines
    re.compile(r"^https?://orcid\.org/\S+\s", re.I),
    # Peer review recommendations (short metadata in sub-article)
    re.compile(r"^Recommendation:\s", re.I),
    # Symbol-prefixed disclaimers (publisher artifact with ☆/† label)
    re.compile(r"^[☆†‡§¶*#]+\s*Disclaimer:", re.I),
]

# Author listing patterns (individual author lines)
_AUTHOR_LINE_PATTERN = re.compile(
    r"^[A-Z][a-z]+ [A-Z][a-z-]+ (?:\w )?\d+$"
)

# Affiliation patterns
_AFFIL_PATTERN = re.compile(r"^\d+ (?:Department|School|Institute|Faculty|College)")

# Email patterns
_EMAIL_PATTERN = re.compile(r"^[a-z] [a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$")

# Author biography patterns (PMC includes <bio> content we don't parse)
_AUTHOR_BIO_PATTERN = re.compile(
    r"^[A-Z][a-z]+ [A-Z][a-z]+ is currently (?:a |an )?(?:professor|associate|assistant|lecturer)",
    re.I,
)

# Abbreviation definition lines: "ABBREV full expansion" (no punctuation at end)
# These come from abbreviation/glossary sections that BioC also excludes.
_ABBREV_DEF_PATTERN = re.compile(
    r"^[A-Za-z0-9α-ωΑ-Ω/+-]+\s+[A-Za-z]",
)

# Back-matter heading variations that map to our structured fields
_BACKMATTER_HEADING_ALIASES = {
    "conflict of interest", "conflicts of interest",
    "conflict of interests",
    "ethics/ethical approval", "ethical approval",
    "medical writing, editorial, and other assistance",
    "medical writing, editorial and other assistance",
    "notes and references",
    "declarations",
}


def _classify_pmc_paragraph(para: str) -> str:
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

    # Figure/table captions
    if re.match(r"^Figure \d+", stripped) or re.match(r"^Table \d+", stripped):
        return "figure_caption"

    # Short headings (typically section titles)
    if len(stripped) < 80 and not stripped.endswith("."):
        # Check if it's a back-matter heading variant we handle as structured fields
        if stripped.lower() in _BACKMATTER_HEADING_ALIASES:
            return "metadata"
        # Check for abbreviation definitions (short "ABBREV Expansion" lines)
        # that BioC also excludes from its ABBR section
        if _ABBREV_DEF_PATTERN.match(stripped) and len(stripped) < 150:
            return "metadata"
        return "section_heading"

    return "body"


# ---------------------------------------------------------------------------
# Main comparison
# ---------------------------------------------------------------------------


def _cross_check_bioc(
    missing_para: str, bioc_paragraphs: list[str],
) -> str:
    """Check if a paragraph missing from our output exists in BioC.

    Returns:
        'in_bioc' - BioC has this content (likely our parser is missing it)
        'not_in_bioc' - BioC also lacks this content (PMC txt may be wrong,
            or it's content neither source expected us to extract)
        'partial_bioc' - BioC has partial match
    """
    best_ratio, _ = _find_best_paragraph_match(missing_para, bioc_paragraphs)
    if best_ratio >= 0.90:
        return "in_bioc"
    if best_ratio >= 0.50:
        return "partial_bioc"
    return "not_in_bioc"


def _compare_article(
    pmcid: str, api_key: str | None, refresh: bool = False,
) -> dict[str, Any]:
    """Compare JATS→Markdown pipeline against PMC S3 plain text + BioC.

    Uses both PMC S3 plain text and BioC API as reference:
    - Primary: PMC S3 plain text (authoritative full extraction)
    - Secondary: BioC (structured passages, used to cross-check discrepancies)

    When our output doesn't match a PMC paragraph, BioC is checked:
    - If BioC also has it → confirmed missing from our parser
    - If BioC doesn't have it → PMC txt content we're not expected to extract,
      or both sources disagree

    Returns a dict with detailed comparison results.
    """
    result: dict[str, Any] = {
        "pmcid": pmcid,
        "verdict": "SKIP",
        "total_pmc_paragraphs": 0,
        "body_paragraphs": 0,
        "matched_paragraphs": 0,
        "missing_confirmed": 0,      # missing from us, confirmed by BioC
        "missing_txt_only": 0,        # in PMC txt only, not in BioC
        "missing_partial_bioc": 0,    # partial BioC match
        "total_missing": 0,
        "match_ratio": 0.0,
        "missing_details": [],
        "fulltext_similarity": 0.0,
        "bioc_available": False,
        "error": None,
    }

    try:
        xml_path, txt_path, bioc_path = _ensure_cached(pmcid, api_key, refresh)
    except Exception as exc:
        result["error"] = f"fetch error: {exc}"
        return result

    if xml_path is None:
        result["error"] = "XML not available"
        return result
    if txt_path is None:
        result["error"] = "PMC plain text not available on S3"
        return result

    # Parse PMC reference text
    pmc_raw = txt_path.read_text(encoding="utf-8", errors="replace")
    pmc = _parse_pmc_text(pmc_raw)
    pmc_body = pmc["body_paragraphs"]
    result["total_pmc_paragraphs"] = len(pmc_body)

    if not pmc_body:
        result["error"] = "no body paragraphs in PMC text"
        return result

    # Load BioC paragraphs for cross-referencing
    bioc_paragraphs: list[str] = []
    if bioc_path and bioc_path.exists():
        try:
            bioc_data = json.loads(bioc_path.read_text(encoding="utf-8"))
            bioc_paragraphs = _extract_bioc_paragraphs(bioc_data)
            result["bioc_available"] = True
        except (json.JSONDecodeError, KeyError):
            pass

    # Full pipeline: JATS → Document → Markdown → read back → plain text
    try:
        xml_data = xml_path.read_bytes()
        doc = parse_jats(xml_data)
        md = emit_markdown(doc)
        doc_rt = read_markdown(md)
        our_plain = extract_plain_text(
            doc_rt, include_supplements=False, include_sub_articles=True,
        )
    except Exception as exc:
        result["error"] = f"pipeline error: {exc}"
        result["verdict"] = "ERROR"
        return result

    if not our_plain.strip():
        result["error"] = "pipeline produced empty output"
        result["verdict"] = "ERROR"
        return result

    # Split our output into paragraphs
    our_paragraphs = [p.strip() for p in our_plain.split("\n\n") if p.strip()]

    # --- Fulltext similarity ---
    pmc_fulltext = "\n\n".join(pmc_body)
    norm_pmc = _normalize_text(pmc_fulltext)
    norm_ours = _normalize_text(our_plain)
    if norm_pmc and norm_ours:
        result["fulltext_similarity"] = difflib.SequenceMatcher(
            None, norm_ours, norm_pmc,
        ).ratio()

    # --- Paragraph-level comparison ---
    body_count = 0
    matched = 0
    missing: list[dict[str, Any]] = []
    confirmed_missing = 0
    txt_only_missing = 0
    partial_bioc = 0

    for pmc_para in pmc_body:
        category = _classify_pmc_paragraph(pmc_para)

        # Skip metadata and author info — we handle these differently
        if category in ("metadata", "author_info"):
            continue

        body_count += 1
        best_ratio, best_idx = _find_best_paragraph_match(pmc_para, our_paragraphs)

        if best_ratio >= 0.90:
            matched += 1
        else:
            # Cross-check against BioC
            bioc_status = "no_bioc"
            if bioc_paragraphs:
                bioc_status = _cross_check_bioc(pmc_para, bioc_paragraphs)

            if bioc_status == "in_bioc":
                confirmed_missing += 1
            elif bioc_status == "partial_bioc":
                partial_bioc += 1
            else:
                txt_only_missing += 1

            missing.append({
                "category": category,
                "ratio": round(best_ratio, 3),
                "bioc_status": bioc_status,
                "pmc_text": pmc_para[:200],
            })

    result["body_paragraphs"] = body_count
    result["matched_paragraphs"] = matched
    result["missing_confirmed"] = confirmed_missing
    result["missing_txt_only"] = txt_only_missing
    result["missing_partial_bioc"] = partial_bioc
    result["total_missing"] = len(missing)
    result["match_ratio"] = matched / body_count if body_count > 0 else 1.0
    result["missing_details"] = missing[:30]
    result["verdict"] = "PASS" if len(missing) == 0 else "FAIL"

    return result


# ---------------------------------------------------------------------------
# Pytest infrastructure
# ---------------------------------------------------------------------------


def pytest_generate_tests(metafunc):
    """Parametrize webtest with fixed + random PMCIDs."""
    if "pmcid" not in metafunc.fixturenames:
        return

    markers = [m.name for m in metafunc.definition.iter_markers()]
    if "webtest" not in markers:
        return

    # Skip network fetches when webtest marker is deselected
    markexpr = metafunc.config.getoption("-m", default="")
    if "not webtest" in markexpr:
        metafunc.parametrize("pmcid", [], ids=[])
        return

    fixed = _load_fixed_articles()
    cached_only = metafunc.config.getoption("--cached-only", default=False)
    count = metafunc.config.getoption("--count", default=500)
    api_key_opt = metafunc.config.getoption("--ncbi-api-key", default=None)
    api_key = api_key_opt or os.environ.get("NCBI_API_KEY")

    if cached_only:
        # Load all cached PMCIDs that have both XML and reference text
        seen = set(fixed)
        all_ids = list(fixed)
        if _CACHE_DIR.exists():
            for d in sorted(_CACHE_DIR.iterdir()):
                if d.is_dir() and d.name.isdigit() and d.name not in seen:
                    seen.add(d.name)
                    all_ids.append(d.name)
    else:
        random_ids: list[str] = []
        if count > 0:
            try:
                random_ids = _fetch_random_pmcids(count, api_key)
            except Exception:
                pass

        # Deduplicate, fixed first
        seen = set(fixed)
        all_ids = list(fixed)
        for pid in random_ids:
            if pid not in seen:
                seen.add(pid)
                all_ids.append(pid)

    # Filter out cached articles that lack reference text (untestable).
    # New articles fetched for the first time are kept — they may succeed.
    testable = []
    for pid in all_ids:
        cache_dir = _CACHE_DIR / pid
        if cache_dir.exists():
            xml_ok = (cache_dir / "article.xml").exists()
            txt_ok = (cache_dir / "reference.txt").exists()
            if xml_ok and not txt_ok:
                continue  # cached but no PMC text — skip
        testable.append(pid)

    metafunc.parametrize(
        "pmcid", testable, ids=[f"PMC{p}" for p in testable],
    )


@pytest.fixture(scope="session")
def pmc_api_key(request):
    """Resolve NCBI API key."""
    key = request.config.getoption("--ncbi-api-key", default=None)
    if key:
        return key
    return os.environ.get("NCBI_API_KEY")


@pytest.fixture(scope="session")
def pmc_refresh(request):
    """Whether to force re-download cached data."""
    return request.config.getoption("--refresh-cache", default=False)


@pytest.fixture(scope="session")
def pmc_results():
    """Collect results for report generation."""
    results: list[dict[str, Any]] = []
    yield results
    # Write report after all tests complete
    report_path = _CACHE_DIR / "report.json"
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    testable = [r for r in results if r["verdict"] != "SKIP"]
    report = {
        "total_articles": len(testable),
        "passed": sum(1 for r in testable if r["verdict"] == "PASS"),
        "failed": sum(1 for r in testable if r["verdict"] == "FAIL"),
        "errors": sum(1 for r in testable if r["verdict"] == "ERROR"),
        "skipped": sum(1 for r in results if r["verdict"] == "SKIP"),
        "articles": results,
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


@pytest.mark.webtest
class TestPMCConversion:
    """Compare JATS→Markdown conversion against PMC S3 plain text + BioC."""

    def test_conversion_parity(
        self, pmcid, pmc_api_key, pmc_refresh, pmc_results,
    ):
        result = _compare_article(pmcid, pmc_api_key, pmc_refresh)
        pmc_results.append(result)

        if result["error"] and result["verdict"] == "SKIP":
            pytest.skip(f"PMC{pmcid}: {result['error']}")

        if result["verdict"] == "ERROR":
            pytest.fail(f"PMC{pmcid}: {result['error']}")

        if result["verdict"] == "FAIL":
            bioc_tag = " (BioC available)" if result["bioc_available"] else ""
            lines = [
                f"PMC{pmcid}{bioc_tag}: "
                f"fulltext={result['fulltext_similarity']:.2%}, "
                f"paragraphs={result['matched_paragraphs']}/{result['body_paragraphs']} "
                f"({result['match_ratio']:.2%}), "
                f"{result['total_missing']} missing "
                f"[confirmed={result['missing_confirmed']}, "
                f"txt_only={result['missing_txt_only']}, "
                f"partial={result['missing_partial_bioc']}]",
            ]
            for detail in result["missing_details"][:5]:
                lines.append(
                    f"  [{detail['category']}|{detail.get('bioc_status', '?')}] "
                    f"ratio={detail['ratio']:.2f}: "
                    f"{detail['pmc_text'][:120]}..."
                )
            pytest.fail("\n".join(lines))
