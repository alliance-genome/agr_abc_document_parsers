"""TEI→Markdown content parity tests — verify no content is lost in TEI→MD round-trip.

Marked with ``@pytest.mark.teitest`` and excluded from default test runs.
Run manually with::

    pytest -m teitest --tei-count=10 -v

Requires:
- Network access to Alliance prod RDS database
- AWS credentials for agr-literature S3 bucket
- Credentials configured in .env file at project root
"""
from __future__ import annotations

import difflib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import pytest

from agr_abc_document_parsers.md_emitter import emit_markdown
from agr_abc_document_parsers.plain_text import extract_plain_text
from agr_abc_document_parsers.tei_parser import parse_tei
from tests.agr_infra_helpers import download_from_agr_s3, get_db_config

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CACHE_DIR = Path(__file__).parent / ".teidata"

# Minimum paragraph length for comparison (skip very short text)
_MIN_PARA_LENGTH = 20


# ---------------------------------------------------------------------------
# Database access
# ---------------------------------------------------------------------------


def _fetch_tei_md5sums(limit: int = 50) -> list[dict[str, Any]]:
    """Fetch TEI file md5sums and reference info from the prod database.

    Returns list of dicts with keys: md5sum, reference_id, display_name.
    """
    try:
        import psycopg2
    except ImportError:
        pytest.skip("psycopg2 not installed")
        return []

    db_config = get_db_config()
    if not db_config["host"]:
        pytest.skip(
            "PSQL_HOST not configured — set in .env or environment"
        )
        return []

    query = """
        SELECT rf.md5sum, rf.reference_id, rf.display_name
        FROM referencefile rf
        WHERE rf.file_class = 'tei'
          AND rf.file_extension = 'tei'
          AND rf.file_publication_status = 'final'
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

    return [
        {"md5sum": row[0], "reference_id": row[1],
         "display_name": row[2]}
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------


def _ensure_cached(md5sum: str, display_name: str) -> Path | None:
    """Ensure TEI file is cached locally. Downloads from S3 if needed.

    Returns path to the cached TEI file, or None if unavailable.
    """
    cache = _CACHE_DIR / md5sum
    cache.mkdir(parents=True, exist_ok=True)
    tei_path = cache / f"{display_name}.tei"
    meta_path = cache / "meta.json"

    if tei_path.exists():
        return tei_path

    # Download from S3
    tei_data = download_from_agr_s3(md5sum)
    if tei_data is None:
        return None

    tei_path.write_bytes(tei_data)
    meta_path.write_text(
        json.dumps({"md5sum": md5sum, "display_name": display_name}),
        encoding="utf-8",
    )
    return tei_path


# ---------------------------------------------------------------------------
# Text normalization and comparison
# ---------------------------------------------------------------------------


def _normalize_text(text: str) -> str:
    """Normalize text for comparison.

    - Unicode NFKC normalization
    - Collapse whitespace
    - Lowercase
    """
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.lower()
    return text


def _normalize_paragraph(text: str) -> str:
    """Normalize a paragraph for matching — strip non-alphanumeric."""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.lower()
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


def _find_best_match(
    needle: str, haystack: list[str],
) -> tuple[float, int]:
    """Find the best matching string from haystack for needle.

    Returns (best_ratio, best_index). Index is -1 if no match.
    """
    norm_needle = _normalize_paragraph(needle)
    if not norm_needle or len(norm_needle) < _MIN_PARA_LENGTH:
        return (1.0, -1)  # skip very short text

    needle_tokens = set(norm_needle.split())
    best_ratio = 0.0
    best_idx = -1

    for i, candidate in enumerate(haystack):
        norm_cand = _normalize_paragraph(candidate)
        if not norm_cand:
            continue

        # Substring containment
        if norm_needle in norm_cand or norm_cand in norm_needle:
            return (1.0, i)

        # Token overlap pre-filter
        cand_tokens = set(norm_cand.split())
        overlap = len(needle_tokens & cand_tokens) / max(
            len(needle_tokens), len(cand_tokens), 1
        )
        if overlap < 0.3:
            continue

        ratio = difflib.SequenceMatcher(None, norm_needle, norm_cand).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_idx = i
        if best_ratio >= 0.95:
            break

    return (best_ratio, best_idx)


# ---------------------------------------------------------------------------
# Main comparison logic
# ---------------------------------------------------------------------------


def _strip_md_formatting(text: str) -> str:
    """Strip Markdown formatting to get plain text for comparison.

    Removes headings markers, bold/italic markers, HTML sup/sub tags,
    table separators, link syntax, and Markdown list markers.
    """
    lines: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        # Skip GFM table separator rows (|---|---|)
        if re.match(r"^\|[-:| ]+\|$", stripped):
            continue
        # Skip horizontal rules
        if re.match(r"^---\s*$", stripped):
            continue
        # Strip heading markers
        stripped = re.sub(r"^#{1,6}\s+", "", stripped)
        # Strip bold/italic
        stripped = re.sub(r"\*\*(.+?)\*\*", r"\1", stripped)
        stripped = re.sub(r"\*(.+?)\*", r"\1", stripped)
        # Strip sup/sub HTML
        stripped = re.sub(r"</?su[bp]>", "", stripped)
        # Strip link syntax [text](url) → text
        stripped = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", stripped)
        # Strip table cell pipes
        stripped = stripped.strip("|").strip()
        # Strip list markers
        stripped = re.sub(r"^[-*]\s+", "", stripped)
        stripped = re.sub(r"^\d+\.\s+", "", stripped)
        if stripped:
            lines.append(stripped)
    return "\n\n".join(lines)


def _compare_tei_roundtrip(
    tei_data: bytes, md5sum: str, display_name: str,
) -> dict[str, Any]:
    """Compare TEI→MD to verify content preservation.

    Pipeline: TEI XML → Document → plain text (original)
              TEI XML → Document → Markdown → stripped text (output)
    Compare plain text from Document against the Markdown output directly.

    Returns a dict with detailed comparison results.
    """
    result: dict[str, Any] = {
        "md5sum": md5sum,
        "display_name": display_name,
        "verdict": "SKIP",
        "error": None,
        "original_plain_text_len": 0,
        "markdown_text_len": 0,
        "fulltext_similarity": 0.0,
        "total_original_paragraphs": 0,
        "matched_paragraphs": 0,
        "missing_paragraphs": 0,
        "match_ratio": 0.0,
        "missing_details": [],
        # Structural counts
        "orig_sections": 0,
        "orig_figures": 0,
        "orig_tables": 0,
        "orig_refs": 0,
    }

    # --- Step 1: Parse TEI → original Document ---
    try:
        orig_doc = parse_tei(tei_data)
    except Exception as exc:
        result["error"] = f"TEI parse error: {exc}"
        result["verdict"] = "ERROR"
        return result

    # --- Step 2: Emit Markdown ---
    try:
        md_text = emit_markdown(orig_doc)
    except Exception as exc:
        result["error"] = f"Markdown emit error: {exc}"
        result["verdict"] = "ERROR"
        return result

    if not md_text.strip():
        result["error"] = "Markdown output is empty"
        result["verdict"] = "ERROR"
        return result

    # --- Step 3: Extract plain text from original Document ---
    orig_plain = extract_plain_text(orig_doc, include_supplements=False)

    result["original_plain_text_len"] = len(orig_plain)
    result["markdown_text_len"] = len(md_text)

    if not orig_plain.strip():
        result["error"] = "Original TEI produced no plain text"
        result["verdict"] = "SKIP"
        return result

    # --- Step 4: Strip formatting from Markdown ---
    md_stripped = _strip_md_formatting(md_text)

    # --- Step 5: Structural counts ---
    result["orig_sections"] = _count_sections(orig_doc.sections)
    all_sections = _flatten_sections(orig_doc.sections)
    result["orig_figures"] = len(orig_doc.figures) + sum(
        len(s.figures) for s in all_sections
    )
    result["orig_tables"] = len(orig_doc.tables) + sum(
        len(s.tables) for s in all_sections
    )
    result["orig_refs"] = len(orig_doc.references)

    # --- Step 6: Fulltext similarity ---
    norm_orig = _normalize_text(orig_plain)
    norm_md = _normalize_text(md_stripped)
    if norm_orig and norm_md:
        result["fulltext_similarity"] = difflib.SequenceMatcher(
            None, norm_orig, norm_md,
        ).ratio()

    # --- Step 7: Paragraph-level comparison ---
    # Check each paragraph from the Document plain text appears in the MD
    orig_paragraphs = [p.strip() for p in orig_plain.split("\n\n") if p.strip()]
    md_paragraphs = [p.strip() for p in md_stripped.split("\n\n") if p.strip()]

    result["total_original_paragraphs"] = len(orig_paragraphs)
    matched = 0
    missing: list[dict[str, Any]] = []

    for orig_para in orig_paragraphs:
        best_ratio, best_idx = _find_best_match(orig_para, md_paragraphs)

        if best_ratio >= 0.85:
            matched += 1
        else:
            missing.append({
                "ratio": round(best_ratio, 3),
                "original_text": orig_para[:200],
                "best_match_text": (
                    md_paragraphs[best_idx][:200] if best_idx >= 0 else ""
                ),
            })

    result["matched_paragraphs"] = matched
    result["missing_paragraphs"] = len(missing)
    result["match_ratio"] = (
        matched / len(orig_paragraphs) if orig_paragraphs else 1.0
    )
    result["missing_details"] = missing[:20]
    result["verdict"] = "PASS" if len(missing) == 0 else "FAIL"

    return result


def _count_sections(sections: list) -> int:
    """Recursively count sections including subsections."""
    count = len(sections)
    for s in sections:
        count += _count_sections(s.subsections)
    return count


def _flatten_sections(sections: list) -> list:
    """Flatten a section tree into a list."""
    flat = []
    for s in sections:
        flat.append(s)
        flat.extend(_flatten_sections(s.subsections))
    return flat


# ---------------------------------------------------------------------------
# Pytest infrastructure
# ---------------------------------------------------------------------------


def pytest_generate_tests(metafunc):
    """Parametrize teitest with TEI files from the prod database."""
    if "tei_file_info" not in metafunc.fixturenames:
        return

    markers = [m.name for m in metafunc.definition.iter_markers()]
    if "teitest" not in markers:
        return

    # Skip DB fetches when teitest marker is deselected
    markexpr = metafunc.config.getoption("-m", default="")
    if "not teitest" in markexpr:
        metafunc.parametrize("tei_file_info", [], ids=[])
        return

    count = metafunc.config.getoption("--tei-count", default=20)

    # Try loading from cache first, then fall back to DB
    cached_files = _load_cached_tei_files()
    db_files: list[dict[str, Any]] = []

    if len(cached_files) < count:
        try:
            db_files = _fetch_tei_md5sums(limit=count)
        except Exception:
            pass

    # Merge: cached first, then DB results (deduplicated)
    seen = {f["md5sum"] for f in cached_files}
    all_files = list(cached_files)
    for f in db_files:
        if f["md5sum"] not in seen:
            seen.add(f["md5sum"])
            all_files.append(f)

    # Limit to requested count
    all_files = all_files[:count]

    metafunc.parametrize(
        "tei_file_info",
        all_files,
        ids=[f"{f['display_name']}" for f in all_files],
    )


def _load_cached_tei_files() -> list[dict[str, Any]]:
    """Load previously cached TEI file metadata."""
    files: list[dict[str, Any]] = []
    if not _CACHE_DIR.exists():
        return files

    for entry in _CACHE_DIR.iterdir():
        if not entry.is_dir():
            continue
        meta_path = entry / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                files.append(meta)
            except (json.JSONDecodeError, KeyError):
                continue
    return files


@pytest.fixture(scope="session")
def tei_results():
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
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


@pytest.mark.teitest
class TestTEIConversion:
    """Compare TEI→Markdown round-trip to verify content preservation."""

    def test_tei_content_parity(
        self, tei_file_info, tei_results,
    ):
        md5sum = tei_file_info["md5sum"]
        display_name = tei_file_info.get("display_name", md5sum)

        # Ensure TEI file is cached
        tei_path = _ensure_cached(md5sum, display_name)
        if tei_path is None:
            pytest.skip(f"{display_name}: could not download TEI from S3")

        tei_data = tei_path.read_bytes()
        result = _compare_tei_roundtrip(tei_data, md5sum, display_name)
        tei_results.append(result)

        if result["error"] and result["verdict"] == "SKIP":
            pytest.skip(f"{display_name}: {result['error']}")

        if result["verdict"] == "ERROR":
            pytest.fail(f"{display_name}: {result['error']}")

        if result["verdict"] == "FAIL":
            lines = [
                f"{display_name} (md5={md5sum[:12]}...): "
                f"fulltext={result['fulltext_similarity']:.2%}, "
                f"paragraphs={result['matched_paragraphs']}"
                f"/{result['total_original_paragraphs']} "
                f"({result['match_ratio']:.2%}), "
                f"{result['missing_paragraphs']} missing",
            ]
            # Structural counts
            lines.append(
                f"  sections: {result['orig_sections']}, "
                f"figures: {result['orig_figures']}, "
                f"tables: {result['orig_tables']}, "
                f"refs: {result['orig_refs']}"
            )
            for detail in result["missing_details"][:5]:
                lines.append(
                    f"  ratio={detail['ratio']:.2f}: "
                    f"{detail['original_text'][:120]}..."
                )
            pytest.fail("\n".join(lines))
