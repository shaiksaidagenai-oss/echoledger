"""Arthur's diary: a fictional 1926 resident reacting to his real daily paper.

Leakage prevention here is entirely prompt-based (the CRITICAL RULE below).
An automated leakage *judge* that scores how well this actually held up is
Phase 4 scope (shared/model-migration... no - see CLAUDE.md roadmap), not
something this file attempts.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import anthropic
from pydantic import BaseModel

from echoledger.llm.client import get_client, record_usage
from echoledger.models import ArthurDiaryEntry, HistoricalArticle
from echoledger.storage.db import save_diary_entry

MAX_SOURCE_ARTICLES = 6

ARTHUR_SYSTEM_PROMPT = """\
You are Arthur, an ordinary resident of Washington, D.C., in the year 1926.

Today's date, for you, is {date}. You have just finished reading that day's
edition of the {newspaper}.

Write a short, personal diary entry (150-250 words) reacting to what you
read, in first person, in a voice natural to an educated American of 1926 -
thoughtful, a little formal, genuinely curious or concerned about the news
of your actual day.

CRITICAL RULE - follow this absolutely: you have no knowledge whatsoever of
anything that happens after {date}. You do not know what will happen
tomorrow, next year, or in any future decade - no later inventions, wars,
deaths, elections, or discoveries. Write only from what a real person on
{date} could possibly know or guess. If you are unsure whether something
has happened yet, assume it has not.

Base your entry only on the real newspaper articles provided below - do not
invent news that isn't there."""


class _ArthurOutput(BaseModel):
    """What we ask the LLM to produce. Deliberately minimal - the date and
    source_article_ids are things we already know, not things to ask the
    model to repeat back."""

    entry_text: str


def write_diary_entry(
    conn: sqlite3.Connection,
    historical_date: date,
    articles: list[HistoricalArticle],
    model: str,
    client: anthropic.Anthropic | None = None,
) -> ArthurDiaryEntry:
    """Writes and saves Arthur's diary entry for one date, grounded in the
    given articles. Pass in a handful of real front-page articles, not all
    of them - there can be hundreds of legible articles for a single date."""
    if client is None:
        client = get_client()

    chosen = articles[:MAX_SOURCE_ARTICLES]
    newspaper = chosen[0].newspaper if chosen else "the newspaper"
    articles_text = "\n\n".join(f"[{a.id}] {a.headline}\n{a.text}" for a in chosen)

    response = client.messages.parse(
        model=model,
        max_tokens=1024,
        system=ARTHUR_SYSTEM_PROMPT.format(
            date=historical_date.isoformat(), newspaper=newspaper
        ),
        messages=[{"role": "user", "content": articles_text}],
        output_format=_ArthurOutput,
    )

    record_usage(
        conn,
        purpose="arthur_diary",
        model=model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )

    if response.parsed_output is None:
        raise ValueError(
            "Claude's response didn't match the expected output schema - "
            "no diary entry was produced."
        )

    entry = ArthurDiaryEntry(
        date=historical_date,
        entry_text=response.parsed_output.entry_text,
        source_article_ids=[a.id for a in chosen],
        model=model,
    )
    save_diary_entry(conn, entry)
    return entry
