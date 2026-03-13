"""Shared pytest fixtures for agr_abc_document_parsers tests."""
import os


def pytest_addoption(parser):
    parser.addoption(
        "--count", type=int, default=500,
        help="Number of random PMC articles to test (webtest only)",
    )
    parser.addoption(
        "--ncbi-api-key", default=None,
        help="NCBI API key (or set NCBI_API_KEY env var)",
    )
    parser.addoption(
        "--refresh-cache", action="store_true", default=False,
        help="Force re-download of cached PMC data",
    )
    parser.addoption(
        "--tei-count", type=int, default=20,
        help="Number of TEI files to test from prod DB (teitest only)",
    )


def get_ncbi_api_key(request):
    """Resolve NCBI API key from CLI option or environment variable."""
    key = request.config.getoption("--ncbi-api-key")
    if key:
        return key
    return os.environ.get("NCBI_API_KEY")
