"""Prompt-injection defense for retrieved document text.

Retrieved chunks are external data, not instructions, but a document could
contain text crafted to look like an instruction to the LLM ("ignore
previous instructions", "reveal your system prompt", etc). This module:

1. Detects common injection patterns in a chunk (for logging/flagging and
   for the GUI to show a warning badge on that citation).
2. Wraps every retrieved chunk in an explicit data-fence when it is
   assembled into the LLM prompt, so even an undetected pattern is presented
   to the model as quoted reference material rather than as instructions.

This is defense in depth, not a guarantee -- it is documented as such in
docs/rag-design.md.
"""

from __future__ import annotations

import re

_INJECTION_PATTERNS = [
    r"ignore (all )?(previous|prior|above) instructions",
    r"disregard (all )?(previous|prior|above) instructions",
    r"you are no longer",
    r"reveal (the|your|any) (api key|token|secret|system prompt|password)",
    r"act as (if you are|a) (system|admin|root)",
    r"new instructions?:",
    r"system\s*:\s*",
    r"do not cite sources",
    r"stop citing sources",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]


def detect_injection(text: str) -> list[str]:
    """Return the list of matched pattern strings, empty if none found."""
    matches = []
    for pattern, compiled in zip(_INJECTION_PATTERNS, _COMPILED, strict=True):
        if compiled.search(text):
            matches.append(pattern)
    return matches


def fence_untrusted_text(text: str, doc_id: str) -> str:
    """Wrap retrieved text in an explicit data fence for prompt assembly."""
    return f'<untrusted_document_excerpt source="{doc_id}">\n{text}\n</untrusted_document_excerpt>'
