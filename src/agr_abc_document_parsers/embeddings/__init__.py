"""Shared embedding-pipeline contracts and the ABC classifier chunker.

Import this subpackage explicitly (``from agr_abc_document_parsers.embeddings
import ...``); it is intentionally not re-exported from the top-level package so
that importing ``agr_abc_document_parsers`` never pulls the optional
``embeddings`` extra (tiktoken/pyarrow). Those are imported lazily only when a
chunker actually tokenizes or a parquet is written/read.

Contents:
- :class:`Chunker` / :class:`Embedder` — the abstract contracts every profile
  implements (SCRUM-6139).
- :class:`Chunk` / :class:`EmbeddingRecipe` — the canonical parquet record + the
  self-describing recipe descriptor.
- :class:`ParagraphPackChunker` — the concrete ABC document-classifier chunker
  (paragraph-level, non-overlapping, references-excluded); the worked example of
  the :class:`Chunker` contract.
- :func:`write_chunks_parquet` / :func:`read_chunks_parquet` — the canonical
  parquet I/O (requires the ``embeddings`` extra).
"""

from __future__ import annotations

from .interfaces import Chunker, Embedder  # noqa: F401
from .models import (  # noqa: F401
    Chunk,
    EmbeddingRecipe,
    chunk_uuid,
    content_preview,
)
from .paragraph_pack import (  # noqa: F401
    DEFAULT_EMBED_MODEL,
    DEFAULT_PROFILE,
    DEFAULT_TARGET_TOKENS,
    ParagraphPackChunker,
    chunk_markdown,
)
from .parquet_io import (  # noqa: F401
    canonical_columns,
    read_chunks_parquet,
    write_chunks_parquet,
)

__all__ = [
    "Chunker",
    "Embedder",
    "Chunk",
    "EmbeddingRecipe",
    "chunk_uuid",
    "content_preview",
    "ParagraphPackChunker",
    "chunk_markdown",
    "DEFAULT_EMBED_MODEL",
    "DEFAULT_PROFILE",
    "DEFAULT_TARGET_TOKENS",
    "write_chunks_parquet",
    "read_chunks_parquet",
    "canonical_columns",
]
