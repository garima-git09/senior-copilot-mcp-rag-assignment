"""Deterministic, dependency-free fake embedder used by the automated test
suite in place of a real sentence-transformers model.

Uses the classic "hashing trick" bag-of-words approach: each token is hashed
into one of a fixed number of buckets, and the resulting vector is
L2-normalized so cosine similarity behaves the same way it does for the real
embedding model (see rag/ingestion/embedder.py). This is obviously far less
semantically meaningful than a real sentence embedding, but it is fast,
requires no network access or heavy ML dependencies, and is exercised the
same way in tests (matching tokens between a query and a chunk push their
vectors closer together), so it is sufficient for exercising the retrieval
*pipeline* without asserting anything about semantic quality.
"""

from __future__ import annotations

import hashlib

import numpy as np

from rag.ingestion.index_builder import tokenize

_DIMS = 128


def fake_embed_fn(texts: list[str]) -> list[list[float]]:
    vectors = []
    for text in texts:
        vec = np.zeros(_DIMS, dtype=np.float64)
        for token in tokenize(text):
            h = int(hashlib.sha1(token.encode("utf-8")).hexdigest(), 16)
            vec[h % _DIMS] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        vectors.append(vec.tolist())
    return vectors
