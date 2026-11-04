"""OpenAI embeddings, with the same cost logging as the Claude calls.

Embeddings have no output tokens (unlike chat), so log_llm_usage always
gets output_tokens=0 here - still one unified usage table across providers.
"""

from __future__ import annotations

import sqlite3

from openai import OpenAI

from echoledger.storage.db import log_llm_usage

EMBEDDING_MODEL = "text-embedding-3-small"
PRICE_PER_MILLION_INPUT_TOKENS = 0.02

# OpenAI rejects a single request over 300k tokens. ~4 chars/token is a safe
# rough estimate for English, and this budget leaves real headroom for that
# estimate being wrong - found the hard way when a date with 1519 historical
# articles pushed one un-batched call to ~417k tokens and the request failed.
MAX_CHARS_PER_BATCH = 800_000


def get_client() -> OpenAI:
    """Reads OPENAI_API_KEY from the environment automatically."""
    return OpenAI()


def embed_texts(
    conn: sqlite3.Connection,
    texts: list[str],
    *,
    purpose: str,
    client: OpenAI | None = None,
) -> list[list[float]]:
    """Embeds `texts`, splitting into multiple API calls if needed to stay
    under OpenAI's per-request token limit. Returns [] without calling the
    API at all if `texts` is empty."""
    if not texts:
        return []
    if client is None:
        client = get_client()

    embeddings: list[list[float]] = []
    batch: list[str] = []
    batch_chars = 0

    def flush_batch() -> None:
        nonlocal batch, batch_chars
        if not batch:
            return
        response = client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
        total_tokens = response.usage.total_tokens
        cost = (total_tokens / 1_000_000) * PRICE_PER_MILLION_INPUT_TOKENS
        log_llm_usage(
            conn,
            purpose=purpose,
            model=EMBEDDING_MODEL,
            input_tokens=total_tokens,
            output_tokens=0,
            estimated_cost_usd=cost,
        )
        embeddings.extend(item.embedding for item in response.data)
        batch = []
        batch_chars = 0

    for text in texts:
        if batch and batch_chars + len(text) > MAX_CHARS_PER_BATCH:
            flush_batch()
        batch.append(text)
        batch_chars += len(text)
    flush_batch()

    return embeddings
