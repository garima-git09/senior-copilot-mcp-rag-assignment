"""Tests for document ingestion: loading, frontmatter parsing, and chunking."""

from __future__ import annotations

from pathlib import Path

from rag.ingestion.chunker import chunk_document
from rag.ingestion.loader import load_documents

DOCS_PATH = Path(__file__).resolve().parents[1] / "documents"


def test_load_documents_discovers_all_markdown_files():
    docs = load_documents(DOCS_PATH)
    assert len(docs) >= 8
    doc_ids = {d.doc_id for d in docs}
    assert "OP-101" in doc_ids
    assert "SI-401" in doc_ids


def test_document_metadata_is_captured():
    docs = load_documents(DOCS_PATH)
    op101 = next(d for d in docs if d.doc_id == "OP-101")
    assert op101.doc_type == "operating_procedure"
    assert "pump" in op101.asset_types
    assert "High Vibration" in op101.alarm_names


def test_chunking_preserves_metadata_and_section_headings():
    docs = load_documents(DOCS_PATH)
    op101 = next(d for d in docs if d.doc_id == "OP-101")
    chunks = chunk_document(op101)
    assert len(chunks) > 1
    for c in chunks:
        assert c.doc_id == "OP-101"
        assert c.section_heading
        assert c.chunk_id.startswith("OP-101::chunk-")


def test_long_section_is_split_into_overlapping_windows():
    docs = load_documents(DOCS_PATH)
    doc = docs[0]
    chunks = chunk_document(doc, max_chars=50, overlap=10)
    assert all(len(c.text) <= 50 + len(c.section_heading) + 2 for c in chunks)
