"""Shared pytest fixtures for agr_abc_document_parsers tests."""

import os


def pytest_addoption(parser):
    parser.addoption(
        "--count",
        type=int,
        default=500,
        help="Number of random PMC articles to test (webtest only)",
    )
    parser.addoption(
        "--ncbi-api-key",
        default=None,
        help="NCBI API key (or set NCBI_API_KEY env var)",
    )
    parser.addoption(
        "--refresh-cache",
        action="store_true",
        default=False,
        help="Force re-download of cached PMC data",
    )
    parser.addoption(
        "--cached-only",
        action="store_true",
        default=False,
        help="Test only cached PMC articles (no network fetch for new IDs)",
    )
    parser.addoption(
        "--tei-count",
        type=int,
        default=20,
        help="Number of TEI files to test from prod DB (teitest only)",
    )
    parser.addoption(
        "--agr-count",
        type=int,
        default=100,
        help="Number of Alliance nxml articles to test (agrtest only)",
    )


def get_ncbi_api_key(request):
    """Resolve NCBI API key from CLI option or environment variable."""
    key = request.config.getoption("--ncbi-api-key")
    if key:
        return key
    return os.environ.get("NCBI_API_KEY")
