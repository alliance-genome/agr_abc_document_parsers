"""Tests for the shared embedding contracts + the paragraph_pack classifier chunker.

The chunker needs tiktoken and the parquet I/O needs pyarrow (the ``embeddings``
extra); the relevant tests skip cleanly when those are absent so the core test
run does not require the extra.
"""

from __future__ import annotations

import pytest

from agr_abc_document_parsers.embeddings import (
    Chunk,
    Chunker,
    Embedder,
    EmbeddingRecipe,
    ParagraphPackChunker,
    canonical_columns,
    chunk_uuid,
    content_preview,
)

tiktoken = pytest.importorskip("tiktoken", reason="embeddings extra not installed")

CURIE = "AGRKB:101000000000001"

# ABC merged-markdown format: H1 = title, H2 = Abstract / body sections /
# References. read_markdown routes "## References" into doc.references (excluded
# from chunks) and "## Abstract" into doc.abstract.
SAMPLE_MD = """# daf-16 regulates longevity

## Abstract

We studied daf-16 and found it extends lifespan in N2 worms.

## Introduction

The *daf-16* gene was studied. We measured expression in N2 worms.

## Methods

Worms were grown at 20C. RNA was extracted and sequenced.

## References

1. Some Author. A paper title. Journal 2020.
"""


# --- pure helpers (no extra needed) --------------------------------------


def test_content_preview_short_is_identity():
    assert content_preview("hello world") == "hello world"


def test_content_preview_truncates_on_word_boundary():
    text = "word " * 500  # 2500 chars
    preview = content_preview(text, limit=1600)
    assert preview.endswith("...")
    assert len(preview) <= 1604
    assert not preview[:-3].endswith(" ")  # trimmed at a word boundary


def test_chunk_uuid_is_deterministic_and_tenant_independent():
    a = chunk_uuid(CURIE, "p", 0, "some content")
    b = chunk_uuid(CURIE, "p", 0, "some content")
    c = chunk_uuid(CURIE, "p", 1, "some content")
    assert a == b
    assert a != c
    assert len(a) == 36  # canonical UUID string


def test_chunk_post_init_derives_fields():
    chunk = Chunk(reference_curie=CURIE, chunk_index=2, content="two words", profile_name="p")
    assert chunk.char_count == len("two words")
    assert chunk.word_count == 2
    assert chunk.content_preview == "two words"
    assert chunk.chunk_uuid == chunk_uuid(CURIE, "p", 2, "two words")


def test_recipe_metadata_stringifies_and_drops_none():
    recipe = EmbeddingRecipe(
        profile_name="prof", version=1, embedding_model="text-embedding-3-small",
        embedding_dim=1536, chunker_name="paragraph_pack", chunk_target_tokens=512,
        chunk_overlap_tokens=0, references_excluded=True, chunk_max_characters=None,
    )
    meta = recipe.as_metadata(reference_curie=CURIE, chunk_count=7)
    assert meta["profile_name"] == "prof"
    assert meta["version"] == "1"
    assert meta["embedding_dim"] == "1536"
    assert meta["references_excluded"] == "true"
    assert meta["chunk_count"] == "7"
    assert "chunk_max_characters" not in meta  # None dropped
    assert all(isinstance(v, str) for v in meta.values())


def test_interfaces_are_abstract():
    with pytest.raises(TypeError):
        Chunker()  # type: ignore[abstract]
    with pytest.raises(TypeError):
        Embedder()  # type: ignore[abstract]


# --- paragraph_pack chunker (needs tiktoken) -----------------------------


def test_paragraph_pack_excludes_references_and_orders_reading():
    chunks = ParagraphPackChunker().chunk(SAMPLE_MD, reference_curie=CURIE)
    assert chunks, "expected at least one chunk"
    joined = "\n".join(c.content for c in chunks)
    # References section content must not appear
    assert "Some Author" not in joined
    assert "Journal 2020" not in joined
    # markdown emphasis stripped by normalization
    assert "daf-16" in joined and "*daf-16*" not in joined
    # chunk_index sequential from 0
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    # each chunk carries the strategy + profile + provenance
    assert all(c.chunking_strategy == "paragraph_pack" for c in chunks)
    assert all(c.n_tokens and c.n_tokens > 0 for c in chunks)
    assert all(c.section_title for c in chunks)
    # the abstract is included (as its own chunk), flagged is_abstract
    assert any(c.is_abstract and c.section_title == "Abstract" for c in chunks)


def test_paragraph_pack_section_boundaries_start_new_chunks():
    chunks = ParagraphPackChunker().chunk(SAMPLE_MD, reference_curie=CURIE)
    titles = {c.section_title for c in chunks}
    assert "Introduction" in titles
    assert "Methods" in titles
    # abstract and body chunks are distinct (section/abstract boundary)
    assert {c.chunk_index for c in chunks if c.is_abstract}.isdisjoint(
        {c.chunk_index for c in chunks if not c.is_abstract}
    )


def test_paragraph_pack_splits_oversized_paragraph_on_token_windows():
    # H1 title + an H2 section whose single paragraph is ~2000 tokens.
    big = "# Title\n\n## Body\n\n" + ("token " * 2000)
    chunks = ParagraphPackChunker(target_tokens=512).chunk(big, reference_curie=CURIE)
    assert len(chunks) >= 4  # 2000 / 512 -> at least 4 windows
    assert all(c.n_tokens <= 512 for c in chunks)


# --- parquet round-trip (needs pyarrow) ----------------------------------


def test_parquet_round_trip(tmp_path):
    pytest.importorskip("pyarrow", reason="embeddings extra not installed")
    from agr_abc_document_parsers.embeddings import read_chunks_parquet, write_chunks_parquet

    chunker = ParagraphPackChunker()
    chunks = chunker.chunk(SAMPLE_MD, reference_curie=CURIE)
    # fill deterministic fake vectors (no live model in tests)
    for c in chunks:
        c.embedding = [0.1, 0.2, 0.3]
    recipe = EmbeddingRecipe(
        profile_name=chunker.profile_name, version=1,
        embedding_model="text-embedding-3-small", embedding_dim=1536,
        chunker_name=chunker.name, chunk_target_tokens=512, chunk_overlap_tokens=0,
        source="fulltext", references_excluded=True,
    )
    out = tmp_path / "AGRKB_101000000000001.parquet"
    write_chunks_parquet(str(out), chunks, recipe)
    assert out.exists()

    table = read_chunks_parquet(str(out))
    assert table.num_rows == len(chunks)
    assert table.schema.names == canonical_columns()
    # recipe descriptor survives in file metadata
    meta = {k.decode(): v.decode() for k, v in (table.schema.metadata or {}).items()}
    assert meta["profile_name"] == chunker.profile_name
    assert meta["references_excluded"] == "true"
    assert meta["chunk_count"] == str(len(chunks))
    # curie column uses the spec name
    assert table.column("agrkb_reference_curie").to_pylist()[0] == CURIE


# --- Embedder contract via a deterministic fake --------------------------


class _FakeEmbedder(Embedder):
    @property
    def model_name(self) -> str:
        return "fake:v1"

    @property
    def dimension(self) -> int:
        return 3

    def embed(self, texts):
        return [[float(len(t)), 0.0, 1.0] for t in texts]


def test_embedder_embed_chunks_fills_vectors():
    chunks = [
        Chunk(reference_curie=CURIE, chunk_index=0, content="abc", profile_name="p"),
        Chunk(reference_curie=CURIE, chunk_index=1, content="defgh", profile_name="p"),
    ]
    _FakeEmbedder().embed_chunks(chunks)
    assert chunks[0].embedding == [3.0, 0.0, 1.0]
    assert chunks[1].embedding == [5.0, 0.0, 1.0]


def test_embedder_rejects_wrong_dimension():
    class BadEmbedder(_FakeEmbedder):
        def embed(self, texts):
            return [[0.0, 0.0] for _ in texts]  # dim 2 != declared 3

    with pytest.raises(ValueError):
        BadEmbedder().embed_chunks(
            [Chunk(reference_curie=CURIE, chunk_index=0, content="x", profile_name="p")]
        )
