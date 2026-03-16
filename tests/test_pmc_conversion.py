"""PMC content parity tests — compare JATS→Markdown pipeline against PMC S3 plain text.

Marked with ``@pytest.mark.webtest`` and excluded from default test runs.
Run manually with::

    pytest -m webtest --count=10 -v

Requires network access to PMC S3 bucket (pmc-oa-opendata.s3.amazonaws.com).
No AWS account or API key needed — the bucket is publicly accessible.
"""
from __future__ import annotations

import json
import os
import random
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

import pytest

from agr_abc_document_parsers.jats_parser import parse_jats
from agr_abc_document_parsers.md_emitter import emit_markdown
from agr_abc_document_parsers.md_reader import read_markdown
from agr_abc_document_parsers.plain_text import extract_plain_text
from tests.pmc_parity_helpers import (
    compare_against_pmc_reference,
    fetch_bioc,
    fetch_s3_file,
    fetch_url,
    ncbi_params,
    rate_limit,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CACHE_DIR = Path(__file__).parent / ".pmcdata"
_FIXED_ARTICLES = Path(__file__).parent / "pmc_fixed_articles.txt"

_ESEARCH_URL = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
)


def _fetch_random_pmcids(
    count: int, api_key: str | None,
) -> list[str]:
    """Fetch random Open Access PMCIDs using NCBI esearch.

    Uses random year ranges (2000-current) with capped retstart to
    avoid the NCBI esearch retstart limit of 9998 for PMC.
    """
    _RETSTART_MAX = 9998
    current_year = 2026  # avoid datetime import
    years = list(range(2000, current_year + 1))

    pmcids: list[str] = []
    seen: set[str] = set()
    batch_size = min(count, 100)
    stale_rounds = 0
    max_stale = 10

    while len(pmcids) < count and stale_rounds < max_stale:
        year = random.choice(years)
        # First get the count for this year to cap retstart
        params = (
            f"?db=pmc&term=open+access[filter]+AND+{year}[pdat]"
            f"&rettype=count&usehistory=n{ncbi_params(api_key)}"
        )
        rate_limit(api_key)
        data = fetch_url(f"{_ESEARCH_URL}{params}")
        count_match = re.search(rb"<Count>(\d+)</Count>", data)
        if not count_match:
            continue
        year_total = int(count_match.group(1))
        if year_total == 0:
            continue

        needed = min(batch_size, count - len(pmcids))
        max_start = min(_RETSTART_MAX, max(0, year_total - needed))
        retstart = random.randint(0, max_start)
        params = (
            f"?db=pmc&term=open+access[filter]+AND+{year}[pdat]"
            f"&retmax={needed}&retstart={retstart}&sort=pub_date"
            f"{ncbi_params(api_key)}"
        )
        rate_limit(api_key)
        data = fetch_url(f"{_ESEARCH_URL}{params}")
        added = 0
        for m in re.finditer(rb"<Id>(\d+)</Id>", data):
            pmcid = m.group(1).decode()
            if pmcid not in seen:
                seen.add(pmcid)
                pmcids.append(pmcid)
                added += 1
                if len(pmcids) >= count:
                    break
        stale_rounds = 0 if added > 0 else stale_rounds + 1

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
        xml_data = fetch_s3_file(pmcid, "xml")
        if xml_data:
            xml_path.write_bytes(xml_data)
        else:
            # Fallback to NCBI efetch
            efetch_url = (
                f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
                f"efetch.fcgi?db=pmc&id={pmcid}&rettype=xml"
                f"&retmode=xml{ncbi_params(api_key)}"
            )
            rate_limit(api_key)
            try:
                xml_data = fetch_url(efetch_url)
                xml_path.write_bytes(xml_data)
            except (HTTPError, URLError):
                xml_path = None

    if refresh or not txt_path.exists():
        txt_data = fetch_s3_file(pmcid, "txt")
        if txt_data:
            txt_path.write_bytes(txt_data)
        else:
            txt_path = None

    if refresh or not bioc_path.exists():
        bioc_data = fetch_bioc(pmcid)
        if bioc_data:
            bioc_path.write_text(
                json.dumps(bioc_data), encoding="utf-8",
            )
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
# Main comparison
# ---------------------------------------------------------------------------


def _compare_article(
    pmcid: str, api_key: str | None, refresh: bool = False,
) -> dict[str, Any]:
    """Compare JATS→Markdown pipeline against PMC S3 plain text + BioC.

    Uses both PMC S3 plain text and BioC API as reference:
    - Primary: PMC S3 plain text (authoritative full extraction)
    - Secondary: BioC (structured passages, used to cross-check
      discrepancies)

    Returns a dict with detailed comparison results.
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

    try:
        xml_path, txt_path, bioc_path = _ensure_cached(
            pmcid, api_key, refresh,
        )
    except Exception as exc:
        result["error"] = f"fetch error: {exc}"
        return result

    if xml_path is None:
        result["error"] = "XML not available"
        return result
    if txt_path is None:
        result["error"] = "PMC plain text not available on S3"
        return result

    # Full pipeline: JATS → Document → Markdown → read back → plain
    # text
    try:
        xml_data = xml_path.read_bytes()
        doc = parse_jats(xml_data)
        md = emit_markdown(doc)
        doc_rt = read_markdown(md)
        our_plain = extract_plain_text(
            doc_rt,
            include_supplements=False,
            include_sub_articles=True,
        )
    except Exception as exc:
        result["error"] = f"pipeline error: {exc}"
        result["verdict"] = "ERROR"
        return result

    # Read reference data
    pmc_reference_text = txt_path.read_text(
        encoding="utf-8", errors="replace",
    )
    bioc_data = None
    if bioc_path and bioc_path.exists():
        bioc_data = bioc_path.read_bytes()

    return compare_against_pmc_reference(
        our_plain_text=our_plain,
        pmc_reference_text=pmc_reference_text,
        bioc_data=bioc_data,
        pmcid=pmcid,
    )


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
    cached_only = metafunc.config.getoption(
        "--cached-only", default=False,
    )
    count = metafunc.config.getoption("--count", default=500)
    api_key_opt = metafunc.config.getoption(
        "--ncbi-api-key", default=None,
    )
    api_key = api_key_opt or os.environ.get("NCBI_API_KEY")

    if cached_only:
        # Load all cached PMCIDs that have both XML and reference text
        seen = set(fixed)
        all_ids = list(fixed)
        if _CACHE_DIR.exists():
            for d in sorted(_CACHE_DIR.iterdir()):
                if (
                    d.is_dir()
                    and d.name.isdigit()
                    and d.name not in seen
                ):
                    seen.add(d.name)
                    all_ids.append(d.name)
    else:
        random_ids: list[str] = []
        if count > 0:
            try:
                random_ids = _fetch_random_pmcids(count, api_key)
            except Exception:
                pass

        # Start with fixed, then add all cached, then random
        # (deduplicated)
        seen = set(fixed)
        all_ids = list(fixed)
        # Include all cached articles for regression coverage
        if _CACHE_DIR.exists():
            for d in sorted(_CACHE_DIR.iterdir()):
                if (
                    d.is_dir()
                    and d.name.isdigit()
                    and d.name not in seen
                ):
                    seen.add(d.name)
                    all_ids.append(d.name)
        for pid in random_ids:
            if pid not in seen:
                seen.add(pid)
                all_ids.append(pid)

    # Filter out cached articles that lack reference text
    # (untestable). New articles fetched for the first time are kept
    # -- they may succeed.
    testable = []
    for pid in all_ids:
        cache_dir = _CACHE_DIR / pid
        if cache_dir.exists():
            xml_ok = (cache_dir / "article.xml").exists()
            txt_ok = (cache_dir / "reference.txt").exists()
            if xml_ok and not txt_ok:
                continue  # cached but no PMC text -- skip
        testable.append(pid)

    metafunc.parametrize(
        "pmcid", testable, ids=[f"PMC{p}" for p in testable],
    )


@pytest.fixture(scope="session")
def pmc_api_key(request):
    """Resolve NCBI API key from CLI, env var, or .env file."""
    key = request.config.getoption(
        "--ncbi-api-key", default=None,
    )
    if key:
        return key
    key = os.environ.get("NCBI_API_KEY")
    if key:
        return key
    # Fall back to .env file at project root.
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        try:
            from dotenv import dotenv_values
            env = dotenv_values(env_file)
            return env.get("NCBI_API_KEY")
        except ImportError:
            # Parse manually if python-dotenv not installed.
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line.startswith("NCBI_API_KEY=") and not line.startswith("#"):
                    return line.split("=", 1)[1].strip()
    return None


@pytest.fixture(scope="session")
def pmc_refresh(request):
    """Whether to force re-download cached data."""
    return request.config.getoption(
        "--refresh-cache", default=False,
    )


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
        "passed": sum(
            1 for r in testable if r["verdict"] == "PASS"
        ),
        "failed": sum(
            1 for r in testable if r["verdict"] == "FAIL"
        ),
        "errors": sum(
            1 for r in testable if r["verdict"] == "ERROR"
        ),
        "skipped": sum(
            1 for r in results if r["verdict"] == "SKIP"
        ),
        "articles": results,
    }
    report_path.write_text(
        json.dumps(report, indent=2), encoding="utf-8",
    )


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

        if result["verdict"] in ("FAIL", "WARN"):
            bioc_tag = (
                " (BioC available)"
                if result["bioc_available"]
                else ""
            )
            lines = [
                f"PMC{pmcid}{bioc_tag}: "
                f"fulltext={result['fulltext_similarity']:.2%}, "
                f"paragraphs="
                f"{result['matched_paragraphs']}/"
                f"{result['body_paragraphs']} "
                f"({result['match_ratio']:.2%}), "
                f"{result['total_missing']} missing "
                f"[confirmed={result['missing_confirmed']}, "
                f"txt_only={result['missing_txt_only']}, "
                f"partial={result['missing_partial_bioc']}]",
            ]
            for detail in result["missing_details"][:5]:
                lines.append(
                    f"  [{detail['category']}"
                    f"|{detail.get('bioc_status', '?')}] "
                    f"ratio={detail['ratio']:.2f}: "
                    f"{detail['pmc_text'][:120]}..."
                )
            msg = "\n".join(lines)
            # Downgrade to warning when no BioC-confirmed content
            # is missing (txt_only / partial differences only),
            # or when the verdict is WARN (few confirmed missing
            # with high fulltext similarity).
            if (
                result["missing_confirmed"] == 0
                or result["verdict"] == "WARN"
            ):
                import warnings
                warnings.warn(
                    f"PMC parity warning: {msg}",
                    stacklevel=2,
                )
            else:
                pytest.fail(msg)
