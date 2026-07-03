"""Canonical embedding records and recipe descriptor.

A :class:`Chunk` is one row of the shared embedding parquet format: the unit of
text that gets embedded (``content``) plus its provenance and the vector. The
column set is the superset agreed for SCRUM-6139 — Chris Tabone's
``curation_assistant_v1`` profile spec (§6) plus the optional classifier
provenance fields the ABC document-classifier profile needs. Fields a given
profile does not populate are left ``None`` (curation-assistant fills
``parent_section``/``subsection``/``is_top_level`` post-import; the classifier
leaves them null), so a single parquet schema serves every profile.

Pure module — no third-party dependency. The tokenizer (tiktoken) and parquet
writer (pyarrow) live behind the optional ``embeddings`` extra and are imported
lazily where used, so importing this module never requires them.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field


def content_preview(content: str, limit: int = 1600) -> str:
    """Spec §6 rule: ``content[:limit]``; if longer, trim to the last whole word
    and append ``"..."``. Apply to every chunk — a Title-seeded RAG chunk can
    exceed ``limit`` even when the chunker targets a smaller size, so the preview
    is not always equal to ``content``."""
    if len(content) <= limit:
        return content
    head = content[:limit]
    if " " in head:
        head = head.rsplit(" ", 1)[0]
    return head + "..."


def chunk_uuid(reference_curie: str, profile_name: str, chunk_index: int,
               content: str) -> str:
    """Deterministic, tenant-independent chunk id (spec §6.1 formula).

    Keyed on ``(curie, profile_name, chunk_index, content[:100])`` so the same
    source + recipe always yields the same id, independent of any consumer's
    local namespace."""
    key = f"{reference_curie}:{profile_name}:{chunk_index}:{content[:100]}"
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return str(uuid.UUID(bytes=digest[:16]))


@dataclass
class Chunk:
    """One embedded unit of a reference = one parquet row.

    ``content`` is the exact text that is embedded (after normalization); the
    vector must be reproducible from ``content`` + the model alone (spec §0).
    """

    # --- identity / provenance ---
    reference_curie: str
    chunk_index: int
    content: str
    chunk_uuid: str = ""  # filled from the spec formula if left blank (post_init)
    content_preview: str = ""  # derived if left blank (post_init)

    # --- section provenance (raw, pre-hierarchy) ---
    section_title: str | None = None
    section_path: list[str] = field(default_factory=list)

    # --- counts / flags ---
    char_count: int = 0  # derived if 0 (post_init)
    word_count: int = 0  # derived if 0 (post_init)
    page_number: int = 1
    has_table: bool = False
    has_image: bool = False
    chunking_strategy: str = ""  # the Chunker.name that produced this chunk

    # --- element typing (RAG profiles set these; classifier leaves null) ---
    element_type: str | None = None
    content_type: str | None = None

    # --- curation-assistant hierarchy fields (filled by the consumer, not here) ---
    parent_section: str | None = None
    subsection: str | None = None
    is_top_level: str | None = None  # stored as the string "true"/"false" when set
    doc_item_provenance: str | None = None

    # --- classifier / optional provenance extras ---
    original_text: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    is_abstract: bool = False
    n_tokens: int | None = None
    is_document_level: bool = False

    # --- the vector (filled by an Embedder after chunking) ---
    embedding: list[float] | None = None

    # profile name used to derive chunk_uuid when not supplied explicitly
    profile_name: str = ""

    def __post_init__(self) -> None:
        if not self.char_count:
            self.char_count = len(self.content)
        if not self.word_count:
            self.word_count = len(self.content.split())
        if not self.content_preview:
            self.content_preview = content_preview(self.content)
        if not self.chunk_uuid:
            self.chunk_uuid = chunk_uuid(
                self.reference_curie, self.profile_name, self.chunk_index, self.content
            )


@dataclass
class EmbeddingRecipe:
    """Self-describing descriptor written into the parquet file metadata (spec
    §7.1) so a stored file can be validated/selected without a separate catalog
    lookup. Every value is stringified on write (parquet metadata is bytes→bytes)."""

    profile_name: str
    version: int
    embedding_model: str
    embedding_dim: int
    embedding_dtype: str = "float32"
    chunker_name: str = ""
    chunk_target_tokens: int | None = None
    chunk_overlap_tokens: int | None = None
    chunk_max_characters: int | None = None
    source: str = "fulltext"  # "fulltext" | "abstract"
    references_excluded: bool | None = None
    normalizer: str = "agr_abc_document_parsers.strip_markdown_formatting"
    normalizer_version: str = ""
    schema_version: str = "1.0.0"

    def as_metadata(self, *, reference_curie: str, chunk_count: int) -> dict[str, str]:
        """Flatten to a ``{str: str}`` map for parquet file-level metadata."""
        raw: dict[str, object] = {
            "profile_name": self.profile_name,
            "version": self.version,
            "embedding_model": self.embedding_model,
            "embedding_dim": self.embedding_dim,
            "embedding_dtype": self.embedding_dtype,
            "chunker_name": self.chunker_name,
            "chunk_target_tokens": self.chunk_target_tokens,
            "chunk_overlap_tokens": self.chunk_overlap_tokens,
            "chunk_max_characters": self.chunk_max_characters,
            "source": self.source,
            "references_excluded": self.references_excluded,
            "normalizer": self.normalizer,
            "normalizer_version": self.normalizer_version or _package_version(),
            "schema_version": self.schema_version,
            "reference_curie": reference_curie,
            "chunk_count": chunk_count,
        }
        out: dict[str, str] = {}
        for key, value in raw.items():
            if value is None:
                continue
            if isinstance(value, bool):
                out[key] = "true" if value else "false"
            else:
                out[key] = str(value)
        return out


def _package_version() -> str:
    """Resolve the installed ``agr_abc_document_parsers`` version (part of the
    normalization byte-identity contract). Best-effort; ``"unknown"`` if the
    package metadata is unavailable."""
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("agr-abc-document-parsers")
        except PackageNotFoundError:
            return "unknown"
    except Exception:  # pragma: no cover - importlib.metadata always present on 3.8+
        return "unknown"
