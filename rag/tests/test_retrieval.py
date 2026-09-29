"""Tests for hybrid retrieval, filtering, citations, and low-confidence handling."""

from __future__ import annotations

from pathlib import Path

import pytest

from rag.ingestion.index_builder import build_index
from rag.retrieval.retriever import DocumentRetriever
from rag.tests.fake_embedder import fake_embed_fn

DOCS_PATH = Path(__file__).resolve().parents[1] / "documents"


@pytest.fixture(scope="module")
def retriever(tmp_path_factory) -> DocumentRetriever:
    index_dir = tmp_path_factory.mktemp("rag_index")
    build_index(str(DOCS_PATH), str(index_dir), embed_fn=fake_embed_fn)
    return DocumentRetriever(str(index_dir), embed_fn=fake_embed_fn)


def test_relevant_query_returns_ranked_results(retriever: DocumentRetriever):
    result = retriever.search("boiler feed pump high vibration bearing", top_k=3)
    assert not result.low_confidence
    assert result.chunks
    scores = [c.score for c in result.chunks]
    assert scores == sorted(scores, reverse=True)


def test_citations_include_doc_id_title_section_and_score(retriever: DocumentRetriever):
    result = retriever.search("compressor surge anti-surge valve", top_k=3)
    assert result.citations
    for c in result.citations:
        assert set(c.keys()) == {"doc_id", "title", "section", "score"}


def test_irrelevant_query_triggers_low_confidence(retriever: DocumentRetriever):
    result = retriever.search("what is the capital of France", top_k=3, min_score=0.6)
    assert result.low_confidence
    assert result.chunks == []


def test_doc_type_filter_restricts_results(retriever: DocumentRetriever):
    result = retriever.search("alarm response procedure", top_k=5, doc_type="safety_instruction")
    assert all(c.doc_type == "safety_instruction" for c in result.chunks)


def test_asset_type_filter_restricts_results(retriever: DocumentRetriever):
    result = retriever.search("recurring alarm troubleshooting", top_k=10, asset_type="compressor")
    assert all("compressor" in c.doc_id or True for c in result.chunks)  # doc_id alone isn't asset-typed; check underlying metadata instead
    # Re-check via raw chunk metadata for a stronger assertion:
    for c in result.chunks:
        matching = [row for row in retriever.chunks if row["chunk_id"] == c.chunk_id]
        assert matching and "compressor" in matching[0]["asset_types"]
