"""Builds the hybrid retrieval index: real sentence-transformer embeddings
stored in a persistent Chroma vector store, plus a BM25 keyword index,
fused at query time in rag/retrieval/retriever.py.

(Earlier revisions of this project used a TF-IDF vector space instead of
real embeddings, specifically to avoid needing network access to a model
hub during ingestion -- see docs/rag-design.md for that history. This
revision switches to real embeddings + a real vector database now that the
deployment environment has network access, per an explicit decision to
prioritize retrieval quality over offline-build guarantees.)
"""

from __future__ import annotations

import json
import pickle
import re
from dataclasses import asdict
from pathlib import Path

import chromadb
from rank_bm25 import BM25Okapi

from rag.constants import COLLECTION_NAME
from rag.ingestion.chunker import chunk_documents
from rag.ingestion.embedder import EmbedFn, load_embedder
from rag.ingestion.loader import load_documents

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def build_index(
    document_path: str,
    index_path: str,
    max_chars: int = 900,
    overlap: int = 150,
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    embed_fn: EmbedFn | None = None,
) -> dict:
    """Ingest every Markdown document under `document_path`, chunk it, embed
    every chunk, and persist a hybrid vector (Chroma) + BM25 index to
    `index_path`. Returns a small summary dict (documents/chunks counts)
    useful for CLI output and tests.

    `embed_fn`, if given, overrides the real embedding model with any
    text-list -> vector-list callable -- used by the test suite to inject a
    fast, deterministic, network-free fake embedder (see
    rag/tests/fake_embedder.py) instead of downloading a real model.
    """
    docs = load_documents(document_path)
    if not docs:
        raise ValueError(f"No documents found under {document_path}")

    chunks = chunk_documents(docs, max_chars=max_chars, overlap=overlap)
    corpus_texts = [c.text for c in chunks]
    chunk_ids = [c.chunk_id for c in chunks]

    embed = embed_fn or load_embedder(embedding_model)
    embeddings = embed(corpus_texts)

    tokenized_corpus = [tokenize(t) for t in corpus_texts]
    bm25 = BM25Okapi(tokenized_corpus)

    out_dir = Path(index_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Dense vectors: a persistent Chroma collection on disk under
    # <index_path>/chroma. Rebuilt fresh every time so a re-ingest never
    # leaves stale vectors mixed in with the new ones.
    chroma_client = chromadb.PersistentClient(path=str(out_dir / "chroma"))
    existing_collections = {c.name for c in chroma_client.list_collections()}
    if COLLECTION_NAME in existing_collections:
        chroma_client.delete_collection(COLLECTION_NAME)
    collection = chroma_client.create_collection(name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
    collection.add(
        ids=chunk_ids,
        embeddings=embeddings,
        documents=corpus_texts,
        metadatas=[
            {
                "doc_id": c.doc_id,
                "title": c.title,
                "doc_type": c.doc_type,
                "section_heading": c.section_heading,
                "source_path": c.source_path,
                # Chroma metadata values must be scalars, not lists -- the
                # real list values are still available from chunks.jsonl,
                # which is what doc_type/asset_type filtering actually reads
                # (see retriever.py). These comma-joined copies are kept
                # only for anyone inspecting the Chroma collection directly.
                "asset_types": ",".join(c.asset_types),
                "alarm_names": ",".join(c.alarm_names),
            }
            for c in chunks
        ],
    )

    # Sparse (BM25) index -- unchanged: a plain local pickle.
    with open(out_dir / "bm25.pkl", "wb") as f:
        pickle.dump(bm25, f)
    with open(out_dir / "chunks.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(asdict(c)) + "\n" for c in chunks)

    summary = {
        "documents_ingested": len(docs),
        "chunks_indexed": len(chunks),
        "index_path": str(out_dir),
        "embedding_model": embedding_model,
        "vector_store": "chromadb",
        "doc_ids": sorted({d.doc_id for d in docs}),
    }
    with open(out_dir / "index_manifest.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build the RAG retrieval index")
    parser.add_argument("--documents", default="./rag/documents")
    parser.add_argument("--index", default="./rag/index/local")
    parser.add_argument("--embedding-model", default="sentence-transformers/all-MiniLM-L6-v2")
    args = parser.parse_args()

    result = build_index(args.documents, args.index, embedding_model=args.embedding_model)
    print(json.dumps(result, indent=2))
