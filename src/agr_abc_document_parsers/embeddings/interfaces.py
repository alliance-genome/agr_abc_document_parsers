"""Abstract Chunker / Embedder contracts for the shared embedding pipeline.

The split (SCRUM-6139): embeddings are *not* reusable across applications (each
app chunks differently) but *are* reusable within an app for a given recipe. So
the **contracts** live here, in the shared package, and each application (the
biocurator assistant, the document classifiers, the ABC producer) implements
concrete :class:`Chunker` / :class:`Embedder` subclasses. Only these interfaces,
the :class:`~.models.Chunk` record, and the parquet format are shared — that is
what lets the producer run any app's recipe and any app read the result.

A concrete chunker (the ABC classifier ``paragraph_pack`` profile) ships in
:mod:`.paragraph_pack` as the worked example; Chris's ``by_title`` RAG chunker is
another implementation of the same :class:`Chunker` contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from .models import Chunk


class Chunker(ABC):
    """Turn a reference's ABC Markdown into embeddable :class:`Chunk` records.

    Implementations own their own splitting strategy and section handling but
    must agree on the input (the ``converted_merged_main`` Markdown string) and
    the output (a list of :class:`Chunk`, ``chunk_index`` sequential from 0, with
    ``content`` the exact text to embed). ``embedding`` is left ``None`` here and
    filled by an :class:`Embedder`.
    """

    #: short, stable strategy id recorded in the recipe descriptor (e.g.
    #: ``"paragraph_pack"``, ``"by_title"``).
    name: str = ""
    #: the profile this chunker produces (e.g.
    #: ``"classifier_fulltext_paragraph_chunk_refs_excluded_md_cleaned"``).
    profile_name: str = ""

    @abstractmethod
    def chunk(self, markdown: str, *, reference_curie: str) -> list[Chunk]:
        """Parse ``markdown`` and return its ordered chunks for ``reference_curie``."""
        raise NotImplementedError


class Embedder(ABC):
    """Turn chunk ``content`` strings into vectors.

    Kept minimal and model-agnostic so an OpenAI, SPECTER2, or local embedder can
    be swapped in without touching chunking or the parquet format. Concrete
    embedders live in the applications (e.g. the ABC OpenAI embedder), not in
    this shared library, to keep it free of model-client dependencies.
    """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Versioned model identifier recorded in the recipe descriptor."""
        raise NotImplementedError

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector length every returned embedding must have."""
        raise NotImplementedError

    @abstractmethod
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one vector per input text, order preserved."""
        raise NotImplementedError

    def embed_chunks(self, chunks: Sequence[Chunk]) -> None:
        """Fill each chunk's ``embedding`` in place from its ``content``."""
        vectors = self.embed([c.content for c in chunks])
        if len(vectors) != len(chunks):
            raise ValueError(
                f"embedder returned {len(vectors)} vectors for {len(chunks)} chunks"
            )
        for chunk, vector in zip(chunks, vectors):
            if len(vector) != self.dimension:
                raise ValueError(
                    f"vector dim {len(vector)} != declared dimension {self.dimension}"
                )
            chunk.embedding = [float(x) for x in vector]
