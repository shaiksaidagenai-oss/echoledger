"""Lightweight prompt-injection detection for untrusted fetched text (RSS
headlines/snippets, OCR'd historical articles).

Detection only, not stripping - altering text risks corrupting legitimate
content (a real 1926 article might innocently contain the word "orders",
for instance). This surfaces a visible warning so a human can look closer,
in the spirit of "treat fetched text as untrusted input." The real defense
is the system-prompt instruction (see llm/arthur.py etc.) telling the model
to treat delimited content as data, never as commands - this is a second,
independent layer, not the only one.
"""

from __future__ import annotations

INJECTION_MARKERS = [
    "ignore previous instructions",
    "ignore the above",
    "disregard the above",
    "disregard previous instructions",
    "forget everything above",
    "new instructions:",
    "system prompt",
    "you are now",
    "act as if",
    "###instruction",
]


def detect_injection_markers(text: str) -> list[str]:
    """Returns which markers (if any) were found, lowercase-insensitive."""
    lowered = text.lower()
    return [marker for marker in INJECTION_MARKERS if marker in lowered]
