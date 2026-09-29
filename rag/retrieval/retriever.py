"""Hybrid (real embeddings via ChromaDB + BM25) retrieval over the ingested
document index.

Query flow:
    1. Embed the query with the same embedding function used at ingestion
       time, and query the persistent Chroma collection for cosine
       similarity against every chunk's stored vector (dense/semantic
       signal).
    2. Compute a BM25 score for every chunk (sparse/keyword signal).
    3. Bound the BM25 score to [0, 1) with a saturating transform (dense
       scores from Chroma are already bounded in [0, 1] since they come
       from a cosine space), then combine with a configurable weight
       (default 0.5/0.5) into one fused score.
    4. Apply retrieval filters (doc_type, asset_type) before ranking.
    5. Drop chunks below `min_score` (low-confidence handling) -- if nothing
       clears the bar, the caller gets an explicit "no result" signal rather
       than a low-quality forced answer.
    6. Flag any injection patterns found in the returned chunks.

(Earlier revisions of this project used a TF-IDF vector space instead of
real embeddings -- see docs/rag-design.md for that history. This revision
queries a real vector database (Chroma) populated by
rag/ingestion/index_builder.py.)
"""

from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from pathlib import Path

import chromadb
import numpy as np

from rag.constants import COLLECTION_NAME
from rag.ingestion.embedder import EmbedFn, load_embedder
from rag.ingestion.index_builder import tokenize
from rag.retrieval.injection_guard import detect_injection


@dataclass
class RetrievedChunk:
    chunk_id: str
    doc_id: str
    title: str
    doc_type: str
    section_heading: str
    text: str
    score: float
    source_path: str
    injection_flags: list[str]


@dataclass
class RetrievalResult:
    query: str
    chunks: list[RetrievedChunk]
    low_confidence: bool
    citations: list[dict]


class DocumentRetriever:
    def __init__(
        self,
        index_path: str,
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        embed_fn: EmbedFn | None = None,
    ):
        """`embed_fn`, if given, overrides the real embedding model with any
        text-list -> vector-list callable -- used by the test suite to
        inject a fast, deterministic, network-free fake embedder (see
        rag/tests/fake_embedder.py) instead of downloading a real model.
        It MUST be the same function (or at least produce vectors in the
        same space) as whatever built the index, or similarity scores will
        be meaningless.
        """
        self.index_path = Path(index_path)
        self._embed = embed_fn or load_embedder(embedding_model)
        self._load()

    def _load(self) -> None:
        if not (self.index_path / "index_manifest.json").exists():
            raise FileNotFoundError(
                f"No RAG index found at {self.index_path}. Run `python -m rag.ingestion.index_builder --documents <docs> --index <path>` first."
            )
        chroma_client = chromadb.PersistentClient(path=str(self.index_path / "chroma"))
        self.collection = chroma_client.get_collection(COLLECTION_NAME)
        with open(self.index_path / "bm25.pkl", "rb") as f:
            self.bm25 = pickle.load(f)
        self.chunks: list[dict] = []
        with open(self.index_path / "chunks.jsonl", encoding="utf-8") as f:
            for line in f:
                self.chunks.append(json.loads(line))
        self._chunk_index_by_id = {c["chunk_id"]: i for i, c in enumerate(self.chunks)}

    @staticmethod
    def _saturate(scores: np.ndarray, k: float) -> np.ndarray:
        """Bound an unbounded, non-negative score to [0, 1) using a
        saturating transform (score / (score + k)) instead of min-max
        normalization. Min-max normalization is relative to whatever
        candidates happen to be in this query's result set, so it always
        maps the best-of-a-bad-bunch match to ~1.0 -- which defeats
        low-confidence detection for genuinely irrelevant queries. This
        transform instead reflects the *absolute* match strength.
        """
        scores = np.clip(scores, a_min=0, a_max=None)
        return scores / (scores + k)

    def _dense_scores(self, query: str) -> np.ndarray:
        n = len(self.chunks)
        dense_scores = np.zeros(n, dtype=np.float64)
        if n == 0:
            return dense_scores
        query_embedding = self._embed([query])[0]
        chroma_result = self.collection.query(query_embeddings=[query_embedding], n_results=n)
        ids = chroma_result["ids"][0]
        distances = chroma_result["distances"][0]
        for chunk_id, distance in zip(ids, distances, strict=True):
            idx = self._chunk_index_by_id.get(chunk_id)
            if idx is None:
                continue
            # Chroma's "cosine" space reports distance = 1 - cosine_similarity,
            # so similarity = 1 - distance. Clamp for floating-point noise.
            dense_scores[idx] = max(0.0, 1.0 - distance)
        return dense_scores

    def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.25,
        doc_type: str | None = None,
        asset_type: str | None = None,
        dense_weight: float = 0.5,
    ) -> RetrievalResult:
        dense_scores = self._dense_scores(query)
        sparse_scores = np.array(self.bm25.get_scores(tokenize(query)))
        sparse_norm = self._saturate(sparse_scores, k=5.0)
        fused = dense_weight * dense_scores + (1 - dense_weight) * sparse_norm

        candidate_indices = list(range(len(self.chunks)))
        if doc_type:
            candidate_indices = [i for i in candidate_indices if self.chunks[i]["doc_type"] == doc_type]
        if asset_type:
            candidate_indices = [i for i in candidate_indices if asset_type in (self.chunks[i]["asset_types"] or [])]

        ranked = sorted(candidate_indices, key=lambda i: fused[i], reverse=True)[:top_k]

        results: list[RetrievedChunk] = []
        for i in ranked:
            score = float(fused[i])
            if score < min_score:
                continue
            c = self.chunks[i]
            results.append(
                RetrievedChunk(
                    chunk_id=c["chunk_id"],
                    doc_id=c["doc_id"],
                    title=c["title"],
                    doc_type=c["doc_type"],
                    section_heading=c["section_heading"],
                    text=c["text"],
                    score=round(score, 4),
                    source_path=c["source_path"],
                    injection_flags=detect_injection(c["text"]),
                )
            )

        low_confidence = len(results) == 0
        citations = [
            {
                "doc_id": r.doc_id,
                "title": r.title,
                "section": r.section_heading,
                "score": r.score,
            }
            for r in results
        ]
        return RetrievalResult(query=query, chunks=results, low_confidence=low_confidence, citations=citations)
