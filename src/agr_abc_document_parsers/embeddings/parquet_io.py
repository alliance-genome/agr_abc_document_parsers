"""Canonical embedding parquet writer/reader.

One parquet file per reference-profile: one row per :class:`~.models.Chunk`, with
the recipe descriptor (:class:`~.models.EmbeddingRecipe`) stamped into the
file-level metadata so the file is self-describing. The column order and names
are the shared contract — the ABC producer writes this and the biocurator
assistant / classifiers read it, so it must not drift.

``pyarrow`` is behind the optional ``embeddings`` extra and imported lazily; this
module imports cleanly without it (only :func:`write_chunks_parquet` /
:func:`read_chunks_parquet` require it).
"""

from __future__ import annotations

from typing import Any

from .models import Chunk, EmbeddingRecipe

# (parquet column name, pyarrow type factory name). Order is the on-disk column
# order and part of the shared contract. ``agrkb_reference_curie`` is the spec's
# column name for the reference curie (Chunk.reference_curie maps to it).
_COLUMNS = [
    ("agrkb_reference_curie", "string"),
    ("chunk_index", "int32"),
    ("chunk_uuid", "string"),
    ("content", "string"),
    ("content_preview", "string"),
    ("section_title", "string"),
    ("section_path", "list_string"),
    ("char_count", "int32"),
    ("word_count", "int32"),
    ("chunking_strategy", "string"),
    ("element_type", "string"),
    ("content_type", "string"),
    ("page_number", "int32"),
    ("has_table", "bool"),
    ("has_image", "bool"),
    ("parent_section", "string"),
    ("subsection", "string"),
    ("is_top_level", "string"),
    ("doc_item_provenance", "string"),
    ("original_text", "string"),
    ("char_start", "int32"),
    ("char_end", "int32"),
    ("is_abstract", "bool"),
    ("n_tokens", "int32"),
    ("embedding", "list_float32"),
    ("is_document_level", "bool"),
]


def _pa_schema(pa: Any) -> Any:
    factories = {
        "string": pa.string,
        "int32": pa.int32,
        "bool": pa.bool_,
        "list_string": lambda: pa.list_(pa.string()),
        "list_float32": lambda: pa.list_(pa.float32()),
    }
    return pa.schema([pa.field(name, factories[kind]()) for name, kind in _COLUMNS])


def _row(chunk: Chunk) -> dict[str, Any]:
    """Map a :class:`Chunk` to the parquet column dict (curie → spec column name)."""
    return {
        "agrkb_reference_curie": chunk.reference_curie,
        "chunk_index": chunk.chunk_index,
        "chunk_uuid": chunk.chunk_uuid,
        "content": chunk.content,
        "content_preview": chunk.content_preview,
        "section_title": chunk.section_title,
        "section_path": list(chunk.section_path),
        "char_count": chunk.char_count,
        "word_count": chunk.word_count,
        "chunking_strategy": chunk.chunking_strategy,
        "element_type": chunk.element_type,
        "content_type": chunk.content_type,
        "page_number": chunk.page_number,
        "has_table": chunk.has_table,
        "has_image": chunk.has_image,
        "parent_section": chunk.parent_section,
        "subsection": chunk.subsection,
        "is_top_level": chunk.is_top_level,
        "doc_item_provenance": chunk.doc_item_provenance,
        "original_text": chunk.original_text,
        "char_start": chunk.char_start,
        "char_end": chunk.char_end,
        "is_abstract": chunk.is_abstract,
        "n_tokens": chunk.n_tokens,
        "embedding": chunk.embedding,
        "is_document_level": chunk.is_document_level,
    }


def _require_pyarrow() -> tuple[Any, Any]:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - exercised via the extra
        raise ImportError(
            "reading/writing embedding parquet needs pyarrow; install the optional "
            "extra: pip install 'agr-abc-document-parsers[embeddings]'"
        ) from exc
    return pa, pq


def write_chunks_parquet(
    path: str,
    chunks: list[Chunk],
    recipe: EmbeddingRecipe,
    *,
    reference_curie: str | None = None,
) -> None:
    """Write ``chunks`` to ``path`` in the canonical schema, with ``recipe`` in the
    file metadata. ``reference_curie`` defaults to the first chunk's curie."""
    pa, pq = _require_pyarrow()
    if reference_curie is None:
        reference_curie = chunks[0].reference_curie if chunks else ""
    schema = _pa_schema(pa)
    metadata = recipe.as_metadata(reference_curie=reference_curie, chunk_count=len(chunks))
    schema = schema.with_metadata(metadata)
    table = pa.Table.from_pylist([_row(c) for c in chunks], schema=schema)
    pq.write_table(table, path)


def read_chunks_parquet(path: str) -> Any:
    """Read a canonical embedding parquet back as a pyarrow Table (columns per
    :data:`_COLUMNS`; file metadata carries the recipe descriptor)."""
    _, pq = _require_pyarrow()
    return pq.read_table(path)


def canonical_columns() -> list[str]:
    """The on-disk column names, in order (the shared contract)."""
    return [name for name, _ in _COLUMNS]
