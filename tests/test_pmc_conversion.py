"""PMC content parity tests — compare JATS→Markdown against BioC plain text.

Marked with ``@pytest.mark.webtest`` and excluded from default test runs.
Run manually with::

    pytest -m webtest --count=10 -v

Requires network access to NCBI E-utilities and PMC BioC API.
"""
from __future__ import annotations

import difflib
import json
import os
import random
import re
import time
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

_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
_BIOC_URL = "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/PMC{pmcid}/unicode"

# Comparison thresholds
_TOKEN_OVERLAP_THRESHOLD = 0.7
_SEQUENCE_MATCH_THRESHOLD = 0.95
_MIN_SENTENCE_LENGTH = 20  # skip very short sentences


# ---------------------------------------------------------------------------
# NCBI API helpers
# ---------------------------------------------------------------------------


def _rate_limit(api_key: str | None) -> None:
    """Sleep to respect NCBI rate limits."""
    if api_key:
        time.sleep(0.1)   # 10/sec with key
    else:
        time.sleep(0.34)  # 3/sec without key


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
            with urlopen(req, timeout=30) as resp:
                return resp.read()
        except (HTTPError, URLError, TimeoutError):
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    return b""  # unreachable


def _fetch_random_pmcids(count: int, api_key: str | None) -> list[str]:
    """Fetch random Open Access PMCIDs using NCBI esearch."""
    # First, get total count of OA articles
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

    # Fetch random subset
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


def _fetch_nxml(pmcid: str, api_key: str | None) -> bytes:
    """Fetch nXML for a PMCID via NCBI efetch."""
    params = (
        f"?db=pmc&id={pmcid}&rettype=xml&retmode=xml"
        f"{_ncbi_params(api_key)}"
    )
    _rate_limit(api_key)
    return _fetch_url(f"{_EFETCH_URL}{params}")


def _fetch_bioc(pmcid: str) -> dict[str, Any] | None:
    """Fetch BioC JSON for a PMCID.

    The PMC BioC API returns a JSON array of collections.
    We return the first collection (which contains the documents).
    """
    url = _BIOC_URL.format(pmcid=pmcid)
    try:
        data = _fetch_url(url)
        parsed = json.loads(data)
        # API returns a list of collections; take the first
        if isinstance(parsed, list) and parsed:
            return parsed[0]
        if isinstance(parsed, dict):
            return parsed
        return None
    except (HTTPError, json.JSONDecodeError):
        return None


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
        # Take first token (PMCID), ignore inline comments
        pmcid = line.split("#")[0].split()[0]
        pmcids.append(pmcid)
    return pmcids


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------


def _ensure_cached(
    pmcid: str, api_key: str | None, refresh: bool = False,
) -> tuple[Path, Path | None]:
    """Ensure nXML and BioC data are cached for a PMCID.

    Returns (nxml_path, bioc_path_or_None).
    """
    cache = _CACHE_DIR / pmcid
    cache.mkdir(parents=True, exist_ok=True)
    nxml_path = cache / "article.nxml"
    bioc_path = cache / "bioc.json"

    if refresh or not nxml_path.exists():
        nxml_data = _fetch_nxml(pmcid, api_key)
        nxml_path.write_bytes(nxml_data)

    if refresh or not bioc_path.exists():
        bioc_data = _fetch_bioc(pmcid)
        if bioc_data:
            bioc_path.write_text(json.dumps(bioc_data), encoding="utf-8")
        else:
            bioc_path = None
    elif not bioc_path.exists():
        bioc_path = None

    return nxml_path, bioc_path


# ---------------------------------------------------------------------------
# Comparison logic
# ---------------------------------------------------------------------------


def _split_plain_text_sentences(text: str) -> list[str]:
    """Split plain text into sentences for comparison."""
    sentences: list[str] = []
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        for sent in re.split(r"(?<=[.!?])\s+", para):
            sent = sent.strip()
            if len(sent) >= _MIN_SENTENCE_LENGTH:
                sentences.append(sent)
    return sentences


def _extract_bioc_sentences(bioc_json: dict[str, Any]) -> list[str]:
    """Extract text passages from BioC JSON and split into sentences."""
    sentences: list[str] = []
    documents = bioc_json.get("documents", [])
    for doc in documents:
        for passage in doc.get("passages", []):
            text = passage.get("text", "").strip()
            if not text:
                continue
            # Split on sentence boundaries
            for sent in re.split(r"(?<=[.!?])\s+", text):
                sent = sent.strip()
                if len(sent) >= _MIN_SENTENCE_LENGTH:
                    sentences.append(sent)
    return sentences


def _normalize(s: str) -> str:
    """Normalize a sentence for comparison."""
    s = re.sub(r"\s+", " ", s).strip()
    # Remove common formatting differences
    s = re.sub(r"[^\w\s]", "", s).lower()
    return s


def _token_overlap(s1: str, s2: str) -> float:
    """Fast token overlap ratio between two normalized strings."""
    tokens1 = set(s1.split())
    tokens2 = set(s2.split())
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1 & tokens2
    return len(intersection) / max(len(tokens1), len(tokens2))


def _find_best_match(sentence: str, candidates: list[str]) -> float:
    """Find the best SequenceMatcher ratio for sentence against candidates.

    Uses token overlap as a fast pre-filter.
    """
    norm_sent = _normalize(sentence)
    if not norm_sent:
        return 1.0  # empty sentence matches everything

    best = 0.0
    for cand in candidates:
        norm_cand = _normalize(cand)
        # Fast pre-filter
        if _token_overlap(norm_sent, norm_cand) < _TOKEN_OVERLAP_THRESHOLD:
            continue
        ratio = difflib.SequenceMatcher(None, norm_sent, norm_cand).ratio()
        if ratio > best:
            best = ratio
        if best >= _SEQUENCE_MATCH_THRESHOLD:
            break
    return best


def _fulltext_similarity(our_text: str, bioc_text: str) -> float:
    """Compare full plain text using normalized SequenceMatcher."""
    norm_ours = _normalize(our_text)
    norm_bioc = _normalize(bioc_text)
    if not norm_ours or not norm_bioc:
        return 0.0
    return difflib.SequenceMatcher(None, norm_ours, norm_bioc).ratio()


def _bioc_fulltext(bioc_json: dict[str, Any]) -> str:
    """Extract full plain text from BioC JSON (all passages concatenated)."""
    parts: list[str] = []
    for doc in bioc_json.get("documents", []):
        for passage in doc.get("passages", []):
            text = passage.get("text", "").strip()
            if text:
                parts.append(text)
    return "\n\n".join(parts)


def _compare_article(
    pmcid: str, api_key: str | None, refresh: bool = False,
) -> dict[str, Any]:
    """Compare JATS→Markdown conversion against BioC for a single article.

    Performs both fulltext similarity and sentence-level matching.

    Returns a dict with keys: pmcid, verdict, fulltext_ratio,
    sentence_total, sentence_matched, sentence_dropped,
    sentence_match_ratio, dropped_sentences, error.
    """
    result: dict[str, Any] = {
        "pmcid": pmcid,
        "verdict": "SKIP",
        "fulltext_ratio": 0.0,
        "sentence_total": 0,
        "sentence_matched": 0,
        "sentence_dropped": 0,
        "sentence_match_ratio": 0.0,
        "dropped_sentences": [],
        "error": None,
    }

    try:
        nxml_path, bioc_path = _ensure_cached(pmcid, api_key, refresh)
    except Exception as exc:
        result["error"] = f"fetch error: {exc}"
        return result

    if bioc_path is None or not bioc_path.exists():
        result["error"] = "BioC data not available"
        return result

    # Full pipeline: JATS → Document → Markdown → read back → plain text
    try:
        nxml_data = nxml_path.read_bytes()
        doc = parse_jats(nxml_data)
        md = emit_markdown(doc)
        doc_rt = read_markdown(md)
        our_plain = extract_plain_text(doc_rt, include_supplements=False)
    except Exception as exc:
        result["error"] = f"parse error: {exc}"
        result["verdict"] = "ERROR"
        return result

    # Load BioC data
    bioc_data = json.loads(bioc_path.read_text(encoding="utf-8"))

    # --- Fulltext comparison ---
    bioc_plain = _bioc_fulltext(bioc_data)
    if not bioc_plain:
        result["error"] = "no BioC text extracted"
        return result

    result["fulltext_ratio"] = _fulltext_similarity(our_plain, bioc_plain)

    # --- Sentence-level comparison ---
    our_sentences = _split_plain_text_sentences(our_plain)
    bioc_sentences = _extract_bioc_sentences(bioc_data)

    if not bioc_sentences:
        result["error"] = "no BioC sentences extracted"
        return result

    matched = 0
    dropped: list[str] = []
    for sent in bioc_sentences:
        if len(sent) < _MIN_SENTENCE_LENGTH:
            continue
        best_ratio = _find_best_match(sent, our_sentences)
        if best_ratio >= _SEQUENCE_MATCH_THRESHOLD:
            matched += 1
        else:
            dropped.append(sent)

    total = matched + len(dropped)
    result["sentence_total"] = total
    result["sentence_matched"] = matched
    result["sentence_dropped"] = len(dropped)
    result["sentence_match_ratio"] = matched / total if total > 0 else 1.0
    result["dropped_sentences"] = dropped[:20]  # limit for report
    result["verdict"] = "PASS" if len(dropped) == 0 else "FAIL"

    return result


# ---------------------------------------------------------------------------
# Pytest infrastructure
# ---------------------------------------------------------------------------


def pytest_generate_tests(metafunc):
    """Parametrize webtest with fixed + random PMCIDs."""
    if "pmcid" not in metafunc.fixturenames:
        return

    # Only generate for webtest-marked tests
    markers = [m.name for m in metafunc.definition.iter_markers()]
    if "webtest" not in markers:
        return

    # Skip network fetches when webtest marker is deselected
    markexpr = metafunc.config.getoption("-m", default="")
    if "not webtest" in markexpr:
        metafunc.parametrize("pmcid", [], ids=[])
        return

    fixed = _load_fixed_articles()
    count = metafunc.config.getoption("--count", default=500)
    api_key_opt = metafunc.config.getoption("--ncbi-api-key", default=None)
    api_key = api_key_opt or os.environ.get("NCBI_API_KEY")

    random_ids: list[str] = []
    if count > 0:
        try:
            random_ids = _fetch_random_pmcids(count, api_key)
        except Exception:
            pass  # proceed with fixed articles only

    # Deduplicate, fixed first
    seen = set(fixed)
    all_ids = list(fixed)
    for pid in random_ids:
        if pid not in seen:
            seen.add(pid)
            all_ids.append(pid)

    metafunc.parametrize("pmcid", all_ids, ids=[f"PMC{p}" for p in all_ids])


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
    report = {
        "total_articles": len(results),
        "passed": sum(1 for r in results if r["verdict"] == "PASS"),
        "failed": sum(1 for r in results if r["verdict"] == "FAIL"),
        "errors": sum(1 for r in results if r["verdict"] == "ERROR"),
        "skipped": sum(1 for r in results if r["verdict"] == "SKIP"),
        "articles": results,
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


@pytest.mark.webtest
class TestPMCConversion:
    """Compare JATS→Markdown conversion against PMC BioC plain text."""

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
            dropped_preview = "; ".join(
                result["dropped_sentences"][:3]
            )
            pytest.fail(
                f"PMC{pmcid}: "
                f"fulltext={result['fulltext_ratio']:.2%}, "
                f"sentences={result['sentence_matched']}/{result['sentence_total']} "
                f"({result['sentence_match_ratio']:.2%}), "
                f"{result['sentence_dropped']} dropped. "
                f"Examples: {dropped_preview}"
            )
