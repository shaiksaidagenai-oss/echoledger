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
    """Embeds a batch of texts in one API call. Returns [] without calling
    the API at all if `texts` is empty."""
    if not texts:
        return []
    if client is None:
        client = get_client()

    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)

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

    return [item.embedding for item in response.data]
