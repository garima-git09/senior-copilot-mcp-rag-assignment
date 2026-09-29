"""Embedding backend used to turn chunk text and queries into vectors for
the Chroma vector store.

Kept as a small, swappable function type (`EmbedFn`) rather than a concrete
class baked into index_builder.py / retriever.py, for two reasons:

1. Tests can inject a fast, deterministic, dependency-free fake embedder
   (see rag/tests/fake_embedder.py) instead of downloading a real model --
   this keeps the automated test suite self-contained and network-free even
   though production embeddings are real.
2. A different embedding backend (a different sentence-transformers model,
   or an API-based embedding service) can be swapped in later by writing one
   new small function with this same signature, with no change to
   index_builder.py or retriever.py.

The real model is loaded lazily, inside `load_embedder()`, specifically so
importing this module (or anything that imports it) never requires
`sentence-transformers` to be installed or a model to be downloaded unless
embeddings are actually being generated.
"""

from __future__ import annotations

from typing import Callable

EmbedFn = Callable[[list[str]], list[list[float]]]


def load_embedder(model_name: str) -> EmbedFn:
    """Load a real sentence-transformers model and return a plain
    text-list -> vector-list function.

    Requires network access on first run (to download the model from
    Hugging Face) unless it has already been cached locally. Embeddings are
    L2-normalized so cosine similarity reduces to a plain dot product,
    matching the "cosine" space the Chroma collection is configured with.
    """
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)

    def _embed(texts: list[str]) -> list[list[float]]:
        return model.encode(list(texts), normalize_embeddings=True, show_progress_bar=False).tolist()

    return _embed
