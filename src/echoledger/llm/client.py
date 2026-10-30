"""Thin wrapper around the Anthropic client, plus cost tracking.

Non-negotiable project rule: log tokens + cost for every LLM call. The
pricing table below is from Anthropic's published rates (as of writing) and
needs updating by hand if prices change or new models are added.
"""

from __future__ import annotations

import sqlite3

import anthropic

from echoledger.storage.db import log_llm_usage

# (input $ per 1M tokens, output $ per 1M tokens)
PRICING_PER_MILLION_TOKENS: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


def get_client() -> anthropic.Anthropic:
    """Reads ANTHROPIC_API_KEY from the environment automatically."""
    return anthropic.Anthropic()


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    if model not in PRICING_PER_MILLION_TOKENS:
        raise ValueError(
            f"No pricing known for model {model!r} - add it to PRICING_PER_MILLION_TOKENS"
        )
    input_price, output_price = PRICING_PER_MILLION_TOKENS[model]
    return (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price


def record_usage(
    conn: sqlite3.Connection,
    *,
    purpose: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Logs this call's usage/cost to SQLite and returns the estimated cost."""
    cost = estimate_cost_usd(model, input_tokens, output_tokens)
    log_llm_usage(
        conn,
        purpose=purpose,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=cost,
    )
    return cost
