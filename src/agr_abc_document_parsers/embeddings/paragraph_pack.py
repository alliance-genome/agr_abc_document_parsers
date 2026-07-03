"""``paragraph_pack`` — the ABC document-classifier chunker (worked example).

Paragraph-level, **non-overlapping**, references-excluded chunking, targeting a
token budget per chunk. Unlike the RAG ``by_title`` chunker (overlapping,
title-seeded), this is tuned for whole-document classification: pack consecutive
paragraphs *within one section* up to ``target_tokens`` with no overlap, so the
mean-pooled vector covers the document evenly and cheaply.

It walks the structured :class:`~agr_abc_document_parsers.models.Document` from
:func:`~agr_abc_document_parsers.read_markdown`: the abstract first, then body
sections (recursing into subsections). References live in ``doc.references`` — a
separate field — so they are excluded by construction, matching the text the
BioWordVec classifier path used. ``content`` (what gets embedded) is the text
after :func:`~agr_abc_document_parsers.strip_markdown_formatting`;
``original_text`` keeps the raw markdown for provenance.

This module is the reference implementation of the :class:`~.interfaces.Chunker`
contract — the example for other profiles (e.g. Chris's ``by_title``) to follow.
``tiktoken`` (for token counting) is behind the optional ``embeddings`` extra and
imported lazily.
"""

from __future__ import annotations

from typing import Any, Iterator

from agr_abc_document_parsers.md_reader import read_markdown
from agr_abc_document_parsers.models import Document, Section
from agr_abc_document_parsers.plain_text import strip_markdown_formatting

from .interfaces import Chunker
from .models import Chunk

DEFAULT_EMBED_MODEL = "text-embedding-3-small"
DEFAULT_TARGET_TOKENS = 512
DEFAULT_PROFILE = "classifier_fulltext_paragraph_chunk_refs_excluded_md_cleaned"


def _tiktoken_encoder(model: str) -> Any:
    """Lazily load the tiktoken encoding for ``model``. Raises a clear error if
    the optional ``embeddings`` extra is not installed."""
    try:
        import tiktoken
    except ImportError as exc:  # pragma: no cover - exercised via the extra
        raise ImportError(
            "paragraph_pack chunking needs tiktoken; install the optional extra: "
            "pip install 'agr-abc-document-parsers[embeddings]'"
        ) from exc
    return tiktoken.encoding_for_model(model)


class _Encoder:
    """Thin token-encoder wrapper exposing ``encode`` / ``decode`` / ``count``.

    Defaults to tiktoken for the given model; a caller may inject any object with
    ``encode(str) -> list[int]`` and ``decode(list[int]) -> str`` (e.g. an
    application's :class:`~.interfaces.Embedder` tokenizer) to avoid the tiktoken
    dependency."""

    def __init__(self, model: str, backend: Any = None) -> None:
        self._backend: Any = backend if backend is not None else _tiktoken_encoder(model)

    def encode(self, text: str) -> list[int]:
        return list(self._backend.encode(text or ""))

    def decode(self, tokens: list[int]) -> str:
        return str(self._backend.decode(tokens))

    def count(self, text: str) -> int:
        return len(self.encode(text))


def _iter_units(doc: Document) -> Iterator[tuple]:
    """Yield (section_path, section_title, is_abstract, raw_text) per paragraph in
    reading order: abstract first, then body sections (recursing into
    subsections). References are never walked."""
    for paragraph in doc.abstract or []:
        if paragraph.text and paragraph.text.strip():
            yield (["Abstract"], "Abstract", True, paragraph.text)

    def walk(sections: list[Section], path: list[str]) -> Iterator[tuple]:
        for section in sections:
            heading = (section.heading or "").strip()
            spath = path + ([heading] if heading else [])
            title = heading or (path[-1] if path else None)
            for paragraph in section.paragraphs:
                if paragraph.text and paragraph.text.strip():
                    yield (spath, title, False, paragraph.text)
            yield from walk(section.subsections, spath)

    yield from walk(doc.sections, [])


class ParagraphPackChunker(Chunker):
    """Pack consecutive same-section paragraphs up to ``target_tokens`` (no
    overlap), splitting any single oversized paragraph on token windows."""

    name = "paragraph_pack"

    def __init__(
        self,
        *,
        profile_name: str = DEFAULT_PROFILE,
        embed_model: str = DEFAULT_EMBED_MODEL,
        target_tokens: int = DEFAULT_TARGET_TOKENS,
        token_encoder: object | None = None,
    ) -> None:
        self.profile_name = profile_name
        self.embed_model = embed_model
        self.target_tokens = target_tokens
        self._encoder: _Encoder | None = None
        self._encoder_backend = token_encoder

    def _get_encoder(self) -> _Encoder:
        if self._encoder is None:
            self._encoder = _Encoder(self.embed_model, self._encoder_backend)
        return self._encoder

    def chunk(self, markdown: str, *, reference_curie: str) -> list[Chunk]:
        doc = read_markdown(markdown)
        return self.chunk_document(doc, reference_curie=reference_curie)

    def chunk_document(self, doc: Document, *, reference_curie: str) -> list[Chunk]:
        """Chunk an already-parsed :class:`Document` (skips re-parsing markdown)."""
        enc = self._get_encoder()
        packed = self._pack(doc, enc)
        return self._materialize(packed, reference_curie)

    def _pack(self, doc: Document, enc: _Encoder) -> list[dict]:
        """Group units into chunk dicts (section_path/title/is_abstract/content)."""
        chunks: list[dict] = []
        cur_orig: list[str] = []
        cur_clean: list[str] = []
        cur_tokens = 0
        cur_meta: tuple | None = None

        def flush() -> None:
            nonlocal cur_orig, cur_clean, cur_tokens, cur_meta
            if cur_clean and cur_meta is not None:
                chunks.append({
                    "section_path": cur_meta[0],
                    "section_title": cur_meta[1],
                    "is_abstract": cur_meta[2],
                    "original_text": "\n".join(cur_orig),
                    "content": "\n".join(cur_clean),
                })
            cur_orig, cur_clean, cur_tokens, cur_meta = [], [], 0, None

        for spath, title, is_abs, raw_text in _iter_units(doc):
            clean = strip_markdown_formatting(raw_text).strip()
            if not clean:
                continue
            meta = (spath, title, is_abs)
            tokens = enc.encode(clean)
            # A new section (or abstract/body switch) starts a fresh chunk.
            if cur_meta is not None and (cur_meta[0] != spath or cur_meta[2] != is_abs):
                flush()
            # A single paragraph larger than the target: hard-split on token windows.
            if len(tokens) > self.target_tokens:
                flush()
                for i in range(0, len(tokens), self.target_tokens):
                    piece = enc.decode(tokens[i:i + self.target_tokens])
                    chunks.append({
                        "section_path": spath, "section_title": title,
                        "is_abstract": is_abs, "original_text": raw_text,
                        "content": piece,
                    })
                continue
            if cur_tokens + len(tokens) > self.target_tokens and cur_clean:
                flush()
            if cur_meta is None:
                cur_meta = meta
            cur_orig.append(raw_text)
            cur_clean.append(clean)
            cur_tokens += len(tokens)
        flush()
        return chunks

    def _materialize(self, packed: list[dict], reference_curie: str) -> list[Chunk]:
        enc = self._get_encoder()
        chunks: list[Chunk] = []
        cursor = 0
        for idx, c in enumerate(packed):
            content = c["content"]
            char_start = cursor
            char_end = cursor + len(content)
            cursor = char_end + 2  # account for the "\n\n" join in the doc text
            chunks.append(Chunk(
                reference_curie=reference_curie,
                chunk_index=idx,
                content=content,
                profile_name=self.profile_name,
                chunking_strategy=self.name,
                section_title=c["section_title"],
                section_path=list(c["section_path"]),
                original_text=c["original_text"],
                char_start=char_start,
                char_end=char_end,
                is_abstract=c["is_abstract"],
                n_tokens=enc.count(content),
            ))
        return chunks

    def document_text(self, chunks: list[Chunk]) -> str:
        """The full references-excluded text (chunks joined by ``\\n\\n``), for an
        optional whole-document embedding."""
        return "\n\n".join(c.content for c in chunks)


# Backwards-compatible functional entry point mirroring the experiment's API.
def chunk_markdown(
    reference_curie: str,
    markdown: str,
    *,
    profile_name: str = DEFAULT_PROFILE,
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    token_encoder: object | None = None,
) -> tuple[list[Chunk], str]:
    """Return ``(chunks, document_text)`` for ``markdown`` using the
    ``paragraph_pack`` strategy."""
    chunker = ParagraphPackChunker(
        profile_name=profile_name, target_tokens=target_tokens, token_encoder=token_encoder
    )
    chunks = chunker.chunk(markdown, reference_curie=reference_curie)
    return chunks, chunker.document_text(chunks)
