"""Generate checkable world-event predictions from today's news, and
resolve past predictions once their resolution date arrives.

Resolution works entirely from our OWN accumulated news (TodayHeadline /
NewsSummary rows saved day by day), never from Claude's own training
knowledge - these predictions concern events that may be after Claude's
training cutoff, so asking it to "just know" would mean guessing, not
judging real evidence.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from echoledger.llm.client import get_client, record_usage
from echoledger.models import Prediction, PredictionResolution, TodayHeadline
from echoledger.storage.db import (
    get_news_summaries,
    get_pending_predictions,
    get_today_headlines,
    save_prediction,
    save_resolution,
)

MAX_NEW_PREDICTIONS_PER_DAY = 3
MIN_RESOLUTION_DAYS_OUT = 3
MAX_RESOLUTION_DAYS_OUT = 180

# Defense-in-depth, not just the prompt instruction below: the non-negotiable
# rule is "no financial predictions" - a keyword filter catches anything that
# slips past prompting, same lesson as leakage prevention in Phase 2.
FINANCE_KEYWORDS = [
    "stock", "shares", "share price", "nasdaq", "dow jones", "s&p",
    "crypto", "bitcoin", "ethereum", "cryptocurrency",
    "currency", "exchange rate", "forex",
    "gold price", "commodity", "commodities",
    "interest rate", "federal reserve", "inflation rate",
    "ipo", "stock market", "investment", "investor",
]  # fmt: skip

GENERATE_SYSTEM_PROMPT = """\
Based on today's real news headlines, write 1-3 checkable predictions
about world events - things that will have a clear, verifiable yes/no
answer by a specific future date.

Rules, follow strictly:
- NEVER predict stock prices, crypto prices, currency exchange rates,
  commodity prices, interest rates, or any financial market outcome.
  World events only - politics, conflicts, elections, court rulings,
  diplomacy, science, sports, etc.
- Each prediction needs a specific resolution_date between {min_days} and
  {max_days} days from today ({today}), in YYYY-MM-DD format.
- probability is your genuine confidence the statement will be true,
  between 0.0 and 1.0 - not always 0.5, and not always extreme.
- Write statements that are unambiguous enough that a reasonable person
  reading the news on the resolution date could judge true or false."""

RESOLUTION_SYSTEM_PROMPT = """\
You are resolving a past prediction using ONLY the real news provided
below - not your own general knowledge, which may predate these events.

If the news provided clearly confirms or denies the prediction, answer
"true" or "false". If the news provided doesn't contain enough
information to tell either way, answer "unclear" - that is a valid,
honest answer, not a failure. Do not guess."""


class _PredictionItem(BaseModel):
    statement: str
    probability: float = Field(ge=0.0, le=1.0)
    resolution_date: str  # YYYY-MM-DD, validated by the caller


class _PredictionsOutput(BaseModel):
    predictions: list[_PredictionItem]


class _ResolutionOutput(BaseModel):
    outcome: Literal["true", "false", "unclear"]
    reasoning: str


def _contains_finance_topic(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in FINANCE_KEYWORDS)


def generate_predictions(
    conn: sqlite3.Connection,
    on_date: date,
    headlines: list[TodayHeadline],
    model: str,
    client: anthropic.Anthropic | None = None,
) -> list[Prediction]:
    if not headlines:
        return []
    if client is None:
        client = get_client()

    headlines_text = "\n".join(f"- {h.headline}" for h in headlines)
    system = GENERATE_SYSTEM_PROMPT.format(
        min_days=MIN_RESOLUTION_DAYS_OUT, max_days=MAX_RESOLUTION_DAYS_OUT, today=on_date
    )

    response = client.messages.parse(
        model=model,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": headlines_text}],
        output_format=_PredictionsOutput,
    )

    record_usage(
        conn,
        purpose="generate_predictions",
        model=model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )

    if response.parsed_output is None:
        raise ValueError("Claude's response didn't match the expected output schema.")

    saved: list[Prediction] = []
    for index, item in enumerate(response.parsed_output.predictions[:MAX_NEW_PREDICTIONS_PER_DAY]):
        if _contains_finance_topic(item.statement):
            print(f"  [guardrail] Rejected a finance-topic prediction: {item.statement!r}")
            continue

        try:
            resolution_date = date.fromisoformat(item.resolution_date)
        except ValueError:
            print(f"  [guardrail] Rejected a prediction with a bad date: {item.resolution_date!r}")
            continue

        days_out = (resolution_date - on_date).days
        if not (MIN_RESOLUTION_DAYS_OUT <= days_out <= MAX_RESOLUTION_DAYS_OUT):
            print(
                f"  [guardrail] Rejected a prediction with an out-of-range date: {resolution_date}"
            )
            continue

        prediction = Prediction(
            id=f"pred-{on_date.isoformat()}-{index}",
            created_date=on_date,
            resolution_date=resolution_date,
            statement=item.statement,
            probability=item.probability,
            forecaster=model,
        )
        save_prediction(conn, prediction)
        saved.append(prediction)

    return saved


def _gather_news_context(conn: sqlite3.Connection, start_date: date, end_date: date) -> str:
    """Every headline (preferring its paraphrased summary) saved between
    start_date and end_date, inclusive - the only evidence resolution
    is allowed to use."""
    lines = []
    current = start_date
    while current <= end_date:
        headlines = get_today_headlines(conn, current)
        summaries_by_id = {s.headline_id: s.summary_text for s in get_news_summaries(conn, current)}
        for h in headlines:
            text = summaries_by_id.get(h.id, h.snippet)
            lines.append(f"[{current.isoformat()}] {h.headline}: {text}")
        current += timedelta(days=1)
    return "\n".join(lines)


def resolve_predictions(
    conn: sqlite3.Connection,
    as_of_date: date,
    model: str,
    client: anthropic.Anthropic | None = None,
) -> list[PredictionResolution]:
    pending = get_pending_predictions(conn, as_of_date)
    if not pending:
        return []
    if client is None:
        client = get_client()

    resolved: list[PredictionResolution] = []
    for prediction in pending:
        news_context = _gather_news_context(conn, prediction.created_date, as_of_date)

        if not news_context:
            # No evidence at all - resolve as unclear without spending on an
            # API call we already know can't be answered.
            resolution = PredictionResolution(
                prediction_id=prediction.id,
                resolved_at=datetime.now(),
                outcome="unclear",
                reasoning="No news was saved during the prediction's window to judge it by.",
                resolver=model,
            )
            save_resolution(conn, resolution)
            resolved.append(resolution)
            continue

        response = client.messages.parse(
            model=model,
            max_tokens=512,
            system=RESOLUTION_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Prediction: {prediction.statement}\n\n"
                        f"News from {prediction.created_date} to {as_of_date}:\n{news_context}"
                    ),
                }
            ],
            output_format=_ResolutionOutput,
        )

        record_usage(
            conn,
            purpose="resolve_prediction",
            model=model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

        if response.parsed_output is None:
            raise ValueError("Claude's response didn't match the expected output schema.")

        resolution = PredictionResolution(
            prediction_id=prediction.id,
            resolved_at=datetime.now(),
            outcome=response.parsed_output.outcome,
            reasoning=response.parsed_output.reasoning,
            resolver=model,
        )
        save_resolution(conn, resolution)
        resolved.append(resolution)

    return resolved
