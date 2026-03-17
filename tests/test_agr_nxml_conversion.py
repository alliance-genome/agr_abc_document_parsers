"""AGR nxml content parity tests — compare Alliance-sourced JATS against PMC reference.

Marked with ``@pytest.mark.agrtest`` and excluded from default test runs.
Run manually with::

    pytest -m agrtest --agr-count=10 -v --tb=short

Requires:
- Network access to Alliance prod RDS database (PSQL_HOST, etc.)
- AWS credentials for agr-literature S3 bucket
- Network access to PMC S3 bucket (pmc-oa-opendata.s3.amazonaws.com)
- Credentials configured in .env file at project root
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from agr_abc_document_parsers.jats_parser import parse_jats
from agr_abc_document_parsers.md_emitter import emit_markdown
from agr_abc_document_parsers.md_reader import read_markdown
from agr_abc_document_parsers.plain_text import extract_plain_text
from tests.agr_infra_helpers import download_from_agr_s3, get_db_config
from tests.pmc_parity_helpers import (
    compare_against_pmc_reference,
    fetch_bioc,
    fetch_s3_file,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CACHE_DIR = Path(__file__).parent / ".agrdata"


# ---------------------------------------------------------------------------
# Database access
# ---------------------------------------------------------------------------


def _fetch_nxml_articles(limit: int) -> list[dict[str, Any]]:
    """Fetch nxml files with PMCIDs from the Alliance prod database.

    Queries the referencefile table joined with cross_reference to find
    nxml files that have an associated PMCID.

    Returns list of dicts with keys: md5sum, reference_id, display_name,
    pmcid (numeric, without 'PMC' prefix).
    """
    try:
        import psycopg2
    except ImportError:
        pytest.skip("psycopg2 not installed")
        return []

    db_config = get_db_config()
    if not db_config["host"]:
        pytest.skip("PSQL_HOST not configured — set in .env or environment")
        return []

    query = """
        SELECT rf.md5sum, rf.reference_id, rf.display_name, cr.curie
        FROM referencefile rf
        JOIN cross_reference cr ON cr.reference_id = rf.reference_id
        WHERE rf.file_class = 'nXML'
          AND rf.file_publication_status = 'final'
          AND cr.curie_prefix = 'PMCID'
        ORDER BY random()
        LIMIT %s
    """
    try:
        conn = psycopg2.connect(
            host=db_config["host"],
            port=int(db_config["port"]),
            dbname=db_config["database"],
            user=db_config["user"],
            password=db_config["password"],
            connect_timeout=15,
        )
        with conn.cursor() as cur:
            cur.execute(query, (limit,))
            rows = cur.fetchall()
        conn.close()
    except Exception as exc:
        pytest.skip(f"Cannot connect to database: {exc}")
        return []

    results: list[dict[str, Any]] = []
    for row in rows:
        # curie is e.g. "PMCID:PMC1234567" — extract numeric part
        curie = row[3]  # type: str
        pmcid = curie.replace("PMCID:PMC", "").replace("PMCID:", "")
        results.append(
            {
                "md5sum": row[0],
                "reference_id": row[1],
                "display_name": row[2],
                "pmcid": pmcid,
            }
        )
    return results


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------


def _ensure_cached(
    pmcid: str,
    md5sum: str,
    display_name: str,
    api_key: str | None,
    refresh: bool = False,
) -> tuple[Path | None, Path | None, Path | None]:
    """Ensure nxml, PMC reference text, and BioC are cached for an article.

    Downloads:
    - article.nxml from Alliance S3 via download_from_agr_s3()
    - reference.txt from PMC S3 via fetch_s3_file()
    - bioc.json from BioC API via fetch_bioc()
    - metadata.json with md5sum, reference_id, display_name

    Returns (nxml_path_or_None, txt_path_or_None, bioc_path_or_None).
    """
    cache = _CACHE_DIR / pmcid
    cache.mkdir(parents=True, exist_ok=True)
    nxml_path = cache / "article.nxml"
    txt_path = cache / "reference.txt"
    bioc_path = cache / "bioc.json"
    meta_path = cache / "metadata.json"

    # Download nxml from Alliance S3
    if refresh or not nxml_path.exists():
        nxml_data = download_from_agr_s3(md5sum)
        if nxml_data:
            nxml_path.write_bytes(nxml_data)
        else:
            nxml_path = None

    # Download PMC reference text from PMC S3
    if refresh or not txt_path.exists():
        txt_data = fetch_s3_file(pmcid, "txt")
        if txt_data:
            txt_path.write_bytes(txt_data)
        else:
            txt_path = None

    # Download BioC from BioC API
    if refresh or not bioc_path.exists():
        bioc_data = fetch_bioc(pmcid)
        if bioc_data:
            bioc_path.write_text(
                json.dumps(bioc_data),
                encoding="utf-8",
            )
        else:
            bioc_path = None

    # Write metadata
    if not meta_path.exists() or refresh:
        meta_path.write_text(
            json.dumps(
                {
                    "md5sum": md5sum,
                    "display_name": display_name,
                    "pmcid": pmcid,
                }
            ),
            encoding="utf-8",
        )

    # Verify paths exist on disk
    if nxml_path and not nxml_path.exists():
        nxml_path = None
    if txt_path and not txt_path.exists():
        txt_path = None
    if bioc_path and not bioc_path.exists():
        bioc_path = None

    return nxml_path, txt_path, bioc_path


# ---------------------------------------------------------------------------
# Main comparison
# ---------------------------------------------------------------------------


def _compare_article(
    pmcid: str,
    md5sum: str,
    display_name: str,
    api_key: str | None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Compare Alliance-sourced JATS nxml against PMC S3 plain text + BioC.

    Pipeline: Alliance nxml → parse_jats → emit_markdown → read_markdown
              → extract_plain_text → compare_against_pmc_reference()

    Returns a dict with detailed comparison results.
    """
    result: dict[str, Any] = {
        "pmcid": pmcid,
        "md5sum": md5sum,
        "display_name": display_name,
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
        nxml_path, txt_path, bioc_path = _ensure_cached(
            pmcid,
            md5sum,
            display_name,
            api_key,
            refresh,
        )
    except Exception as exc:
        result["error"] = f"fetch error: {exc}"
        return result

    if nxml_path is None:
        result["error"] = "nxml not available from Alliance S3"
        return result
    if txt_path is None:
        result["error"] = "PMC plain text not available on S3"
        return result

    # Full pipeline: JATS → Document → Markdown → read back → plain text
    try:
        xml_data = nxml_path.read_bytes()
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
        encoding="utf-8",
        errors="replace",
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


def _load_cached_articles() -> list[dict[str, Any]]:
    """Load previously cached article metadata from .agrdata/ directory."""
    articles: list[dict[str, Any]] = []
    if not _CACHE_DIR.exists():
        return articles

    for entry in sorted(_CACHE_DIR.iterdir()):
        if not entry.is_dir():
            continue
        meta_path = entry / "metadata.json"
        if meta_path.exists():
            try:
                meta = json.loads(
                    meta_path.read_text(encoding="utf-8"),
                )
                # Require pmcid and md5sum at minimum
                if "pmcid" in meta and "md5sum" in meta:
                    articles.append(meta)
            except (json.JSONDecodeError, KeyError):
                continue
    return articles


def pytest_generate_tests(metafunc):
    """Parametrize agrtest with Alliance nxml articles."""
    if "agr_article" not in metafunc.fixturenames:
        return

    markers = [m.name for m in metafunc.definition.iter_markers()]
    if "agrtest" not in markers:
        return

    # Skip DB fetches when agrtest marker is deselected
    markexpr = metafunc.config.getoption("-m", default="")
    if "not agrtest" in markexpr:
        metafunc.parametrize("agr_article", [], ids=[])
        return

    cached_only = metafunc.config.getoption(
        "--cached-only",
        default=False,
    )
    count = metafunc.config.getoption("--agr-count", default=100)

    # Always load cached articles
    cached = _load_cached_articles()
    seen = {a["pmcid"] for a in cached}
    all_articles = list(cached)

    if not cached_only:
        # Fetch from Alliance DB
        db_articles: list[dict[str, Any]] = []
        try:
            db_articles = _fetch_nxml_articles(limit=count)
        except Exception:
            pass

        for article in db_articles:
            if article["pmcid"] not in seen:
                seen.add(article["pmcid"])
                all_articles.append(article)

    # Filter out cached articles that lack reference text (untestable).
    # New articles fetched for the first time are kept — they may
    # succeed.
    testable: list[dict[str, Any]] = []
    for article in all_articles:
        cache_dir = _CACHE_DIR / article["pmcid"]
        if cache_dir.exists():
            nxml_ok = (cache_dir / "article.nxml").exists()
            txt_ok = (cache_dir / "reference.txt").exists()
            if nxml_ok and not txt_ok:
                continue  # cached but no PMC text — skip
        testable.append(article)

    if not testable:
        pytest.skip("no AGR nxml articles to test (cache empty, DB skipped)")
        return

    metafunc.parametrize(
        "agr_article",
        testable,
        ids=[f"PMC{a['pmcid']}" for a in testable],
    )


@pytest.fixture(scope="session")
def agr_api_key(request):
    """Resolve NCBI API key from CLI, env var, or .env file."""
    key = request.config.getoption(
        "--ncbi-api-key",
        default=None,
    )
    if key:
        return key
    key = os.environ.get("NCBI_API_KEY")
    if key:
        return key
    # Fall back to .env file at project root
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        try:
            from dotenv import dotenv_values

            env = dotenv_values(env_file)
            return env.get("NCBI_API_KEY")
        except ImportError:
            # Parse manually if python-dotenv not installed
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line.startswith("NCBI_API_KEY=") and not line.startswith("#"):
                    return line.split("=", 1)[1].strip()
    return None


@pytest.fixture(scope="session")
def agr_refresh(request):
    """Whether to force re-download cached data."""
    return request.config.getoption(
        "--refresh-cache",
        default=False,
    )


@pytest.fixture(scope="session")
def agr_results():
    """Collect results for report generation."""
    results: list[dict[str, Any]] = []
    yield results
    # Write report after all tests complete
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    report_path = _CACHE_DIR / "report.json"
    testable = [r for r in results if r["verdict"] != "SKIP"]
    report = {
        "total_articles": len(testable),
        "passed": sum(1 for r in testable if r["verdict"] == "PASS"),
        "failed": sum(1 for r in testable if r["verdict"] == "FAIL"),
        "errors": sum(1 for r in testable if r["verdict"] == "ERROR"),
        "skipped": sum(1 for r in results if r["verdict"] == "SKIP"),
        "articles": results,
    }
    report_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )


@pytest.mark.agrtest
class TestAGRNxmlConversion:
    """Compare Alliance-sourced JATS nxml against PMC S3 plain text + BioC."""

    def test_conversion_parity(
        self,
        agr_article,
        agr_api_key,
        agr_refresh,
        agr_results,
    ):
        pmcid = agr_article["pmcid"]
        md5sum = agr_article["md5sum"]
        display_name = agr_article.get("display_name", md5sum)

        result = _compare_article(
            pmcid,
            md5sum,
            display_name,
            agr_api_key,
            agr_refresh,
        )
        agr_results.append(result)

        if result["error"] and result["verdict"] == "SKIP":
            pytest.skip(f"PMC{pmcid}: {result['error']}")

        if result["verdict"] == "ERROR":
            pytest.fail(f"PMC{pmcid}: {result['error']}")

        if result["verdict"] in ("FAIL", "WARN"):
            bioc_tag = " (BioC available)" if result["bioc_available"] else ""
            lines = [
                f"PMC{pmcid} [{display_name}]{bioc_tag}: "
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
            if result["missing_confirmed"] == 0 or result["verdict"] == "WARN":
                import warnings

                warnings.warn(
                    f"AGR nxml parity warning: {msg}",
                    stacklevel=2,
                )
            else:
                pytest.fail(msg)
