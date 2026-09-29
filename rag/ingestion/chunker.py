"""Heading-aware chunking with metadata capture.

Documents are split at Markdown headings first (so each chunk stays inside
one logical section), then any section still longer than `max_chars` is
further split into overlapping windows. Every chunk carries the full
document metadata plus its own section heading and position, which is what
powers citations later ("OP-101, section 'Response to High Vibration
Alarm'").
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rag.ingestion.loader import SourceDocument

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    title: str
    doc_type: str
    asset_types: list[str]
    alarm_names: list[str]
    tags: list[str]
    section_heading: str
    chunk_index: int
    text: str
    source_path: str


def _split_sections(body: str) -> list[tuple[str, str]]:
    """Return (heading, section_text) pairs, using 'Document' as the heading
    for any leading text before the first heading.
    """
    matches = list(_HEADING_RE.finditer(body))
    if not matches:
        return [("Document", body.strip())]

    sections: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        sections.append(("Document", body[: matches[0].start()].strip()))

    for i, m in enumerate(matches):
        heading = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        section_text = body[start:end].strip()
        if section_text:
            sections.append((heading, section_text))
    return [(h, t) for h, t in sections if t]


def _split_long_section(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    windows = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        windows.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return windows


def chunk_document(doc: SourceDocument, max_chars: int = 900, overlap: int = 150) -> list[Chunk]:
    chunks: list[Chunk] = []
    index = 0
    for heading, section_text in _split_sections(doc.body):
        for window in _split_long_section(section_text, max_chars, overlap):
            chunks.append(
                Chunk(
                    chunk_id=f"{doc.doc_id}::chunk-{index}",
                    doc_id=doc.doc_id,
                    title=doc.title,
                    doc_type=doc.doc_type,
                    asset_types=doc.asset_types,
                    alarm_names=doc.alarm_names,
                    tags=doc.tags,
                    section_heading=heading,
                    chunk_index=index,
                    text=f"{heading}\n{window}".strip(),
                    source_path=doc.source_path,
                )
            )
            index += 1
    return chunks


def chunk_documents(docs: list[SourceDocument], max_chars: int = 900, overlap: int = 150) -> list[Chunk]:
    all_chunks: list[Chunk] = []
    for doc in docs:
        all_chunks.extend(chunk_document(doc, max_chars, overlap))
    return all_chunks
