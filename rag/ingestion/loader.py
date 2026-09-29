"""Document loading and text extraction for the RAG ingestion pipeline.

Documents are Markdown files with a small YAML-like frontmatter block
(delimited by `---`) carrying metadata (doc_id, title, doc_type,
asset_types, alarm_names, tags, version, effective_date). A tiny hand-rolled
frontmatter parser is used instead of pulling in a YAML dependency, since
the frontmatter here is a flat key: value / key: [a, b] structure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SourceDocument:
    doc_id: str
    title: str
    doc_type: str
    asset_types: list[str]
    alarm_names: list[str]
    tags: list[str]
    version: str
    effective_date: str
    source_path: str
    body: str


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def _parse_scalar_or_list(raw: str) -> str | list[str]:
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [item.strip() for item in inner.split(",")]
    return raw.strip('"')


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError("Document is missing a --- frontmatter block")
    raw_fm, body = match.group(1), match.group(2)
    metadata: dict = {}
    for line in raw_fm.splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, _, value = line.partition(":")
        metadata[key.strip()] = _parse_scalar_or_list(value)
    return metadata, body.strip()


def load_document(path: Path) -> SourceDocument:
    text = path.read_text(encoding="utf-8")
    metadata, body = _parse_frontmatter(text)
    return SourceDocument(
        doc_id=metadata.get("doc_id", path.stem),
        title=metadata.get("title", path.stem),
        doc_type=metadata.get("doc_type", "unknown"),
        asset_types=metadata.get("asset_types") or [],
        alarm_names=metadata.get("alarm_names") or [],
        tags=metadata.get("tags") or [],
        version=str(metadata.get("version", "")),
        effective_date=str(metadata.get("effective_date", "")),
        source_path=str(path),
        body=body,
    )


def load_documents(document_root: str | Path) -> list[SourceDocument]:
    root = Path(document_root)
    if not root.exists():
        raise FileNotFoundError(f"Document corpus path does not exist: {root}")
    docs = []
    for path in sorted(root.rglob("*.md")):
        docs.append(load_document(path))
    return docs
