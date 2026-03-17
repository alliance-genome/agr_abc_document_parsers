"""Shared Alliance infrastructure helpers — DB credentials, S3 access.

Provides environment loading, database config, S3 config, and S3
download helpers used by multiple test modules (TEI parity, future
nxml parity, etc.).
"""

from __future__ import annotations

import gzip
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ENV_FILE = Path(__file__).parent.parent / ".env"


# ---------------------------------------------------------------------------
# Environment / credential helpers
# ---------------------------------------------------------------------------


def load_env() -> dict[str, str]:
    """Load environment variables from .env file."""
    env: dict[str, str] = {}
    if ENV_FILE.exists():
        try:
            from dotenv import dotenv_values

            env = {k: v for k, v in dotenv_values(ENV_FILE).items() if v is not None}
        except ImportError:
            # Fallback: manual parsing
            for line in ENV_FILE.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, val = line.partition("=")
                    env[key.strip()] = val.strip()
    return env


def get_db_config() -> dict[str, str]:
    """Get database connection config from environment / .env file."""
    env = load_env()
    return {
        "host": os.environ.get("PSQL_HOST", env.get("PSQL_HOST", "")),
        "port": os.environ.get(
            "PSQL_PORT",
            env.get("PSQL_PORT", "5432"),
        ),
        "database": os.environ.get(
            "PSQL_DATABASE",
            env.get("PSQL_DATABASE", "literature"),
        ),
        "user": os.environ.get(
            "PSQL_USERNAME",
            env.get("PSQL_USERNAME", "postgres"),
        ),
        "password": os.environ.get(
            "PSQL_PASSWORD",
            env.get("PSQL_PASSWORD", ""),
        ),
    }


def get_s3_config() -> dict[str, str]:
    """Get S3 configuration from environment / .env file."""
    env = load_env()
    # Set AWS credentials in environment for boto3
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        if key not in os.environ and key in env:
            os.environ[key] = env[key]
    return {
        "bucket": os.environ.get(
            "S3_BUCKET",
            env.get("S3_BUCKET", "agr-literature"),
        ),
        "env_prefix": os.environ.get(
            "S3_ENV_PREFIX",
            env.get("S3_ENV_PREFIX", "prod"),
        ),
    }


# ---------------------------------------------------------------------------
# S3 access
# ---------------------------------------------------------------------------


def s3_key_from_md5sum(md5sum: str, env_prefix: str) -> str:
    """Build the S3 object key from an md5sum.

    Path pattern:
        {env}/reference/documents/{md5[0]}/{md5[1]}/{md5[2]}/{md5[3]}/{md5sum}.gz
    """
    folder = f"{env_prefix}/reference/documents/"
    folder += "/".join(md5sum[0:4])
    return f"{folder}/{md5sum}.gz"


def download_from_agr_s3(md5sum: str) -> bytes | None:
    """Download and decompress a file from the AGR S3 bucket.

    Returns the raw decompressed bytes, or None if not found.
    """
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        return None

    s3_config = get_s3_config()
    s3_key = s3_key_from_md5sum(md5sum, s3_config["env_prefix"])

    try:
        client = boto3.client("s3")
        response = client.get_object(
            Bucket=s3_config["bucket"],
            Key=s3_key,
        )
        compressed_data = response["Body"].read()
    except ClientError:
        return None

    # Decompress gzip
    try:
        return gzip.decompress(compressed_data)
    except (gzip.BadGzipFile, OSError):
        # Might not be compressed
        return compressed_data
