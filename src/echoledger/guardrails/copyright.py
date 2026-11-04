"""Defense-in-depth for the copyright rule: checks whether a generated
summary actually paraphrased its source, rather than just echoing it back -
the same "don't trust prompting alone" lesson as the finance-topic filter.
"""

from __future__ import annotations

MIN_MATCHING_WORDS = 8


def is_too_similar_to_source(
    summary_text: str, source_text: str, min_matching_words: int = MIN_MATCHING_WORDS
) -> bool:
    """True if `summary_text` contains a run of `min_matching_words`
    consecutive words copied verbatim from `source_text` - a sign the
    model echoed rather than paraphrased."""
    source_words = source_text.lower().split()
    if len(source_words) < min_matching_words:
        return False  # too short to meaningfully judge either way

    source_joined = " ".join(source_words)
    summary_words = summary_text.lower().split()
    for i in range(len(summary_words) - min_matching_words + 1):
        window = " ".join(summary_words[i : i + min_matching_words])
        if window in source_joined:
            return True
    return False
