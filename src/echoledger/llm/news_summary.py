"""Summarize today's RSS headlines in our own words.

One batched API call handles the whole day's headlines (not one call per
headline) - cheaper, and we only ever pass in a single day's headlines,
never an archive of past days.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import anthropic
from pydantic import BaseModel

from echoledger.llm.client import get_client, record_usage
from echoledger.models import NewsSummary, TodayHeadline
from echoledger.storage.db import save_news_summary

SUMMARY_SYSTEM_PROMPT = """\
You summarize today's news headlines in your own words - clear, neutral,
1-2 sentences each. Paraphrase; do not copy phrases directly from the
provided snippet. Do not add opinion or speculation beyond what the
headline and snippet state."""


class _SummaryItem(BaseModel):
    headline_id: str
    summary_text: str


class _SummariesOutput(BaseModel):
    summaries: list[_SummaryItem]


def summarize_headlines(
    conn: sqlite3.Connection,
    on_date: date,
    headlines: list[TodayHeadline],
    model: str,
    client: anthropic.Anthropic | None = None,
) -> list[NewsSummary]:
    if not headlines:
        return []
    if client is None:
        client = get_client()

    headlines_text = "\n\n".join(
        f"[{h.id}] ({h.source_name}) {h.headline}\n{h.snippet}" for h in headlines
    )

    response = client.messages.parse(
        model=model,
        max_tokens=2048,
        system=SUMMARY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": headlines_text}],
        output_format=_SummariesOutput,
    )

    record_usage(
        conn,
        purpose="news_summary",
        model=model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )

    if response.parsed_output is None:
        raise ValueError(
            "Claude's response didn't match the expected output schema - "
            "no summaries were produced."
        )

    summaries = [
        NewsSummary(
            headline_id=item.headline_id,
            date=on_date,
            summary_text=item.summary_text,
            model=model,
        )
        for item in response.parsed_output.summaries
    ]
    for summary in summaries:
        save_news_summary(conn, summary)
    return summaries
