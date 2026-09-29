"""Shared constants between ingestion (index_builder.py) and retrieval
(retriever.py), so both sides agree on the Chroma collection name without
importing each other's "private" internals.
"""

from __future__ import annotations

COLLECTION_NAME = "alarm_copilot_chunks"
