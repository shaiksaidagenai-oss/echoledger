"""Data shapes for EchoLedger.

Two separate article types on purpose, not one shared shape: a HistoricalArticle
(1926, public domain) is allowed to hold full article text, while a
TodayHeadline (modern news, copyrighted) must never hold more than a short
snippet. Keeping them as distinct types makes it structurally impossible to
accidentally store a full modern article text.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class HistoricalArticle(BaseModel):
    """A real newspaper article from ~100 years ago. Public domain."""

    id: str
    date: date
    newspaper: str
    page: int
    headline: str
    text: str
    source_url: str | None = None


class TodayHeadline(BaseModel):
    """A pointer to a modern news article - headline + short snippet + link
    back to the original. Never the full article text (copyright)."""

    id: str
    date: date
    source_name: str
    headline: str
    snippet: str
    url: str
    fetched_at: datetime


class ArthurDiaryEntry(BaseModel):
    """Arthur's diary entry for one historical date, grounded in real
    HistoricalArticles. Leakage prevention at generation time is
    prompting only - see LeakageJudgment below for the separate,
    dedicated check."""

    date: date
    entry_text: str
    source_article_ids: list[str]
    model: str


class LeakageJudgment(BaseModel):
    """A dedicated, separate LLM call that reviews a completed
    ArthurDiaryEntry for anachronisms - not just trusting the generation
    prompt. Re-judging the same date replaces the old result (not
    immutable like Prediction - this is our own QA check, not a public
    claim)."""

    historical_date: date
    verdict: str  # "pass" | "fail"
    violations: list[str]
    model: str
    judged_at: datetime


class NewsSummary(BaseModel):
    """An LLM-written 'in our own words' paraphrase of one TodayHeadline -
    replaces display dependence on the source's own snippet wording, which
    matters for the copyright rule (summarize, don't just re-show)."""

    headline_id: str
    date: date
    summary_text: str
    model: str


class Prediction(BaseModel):
    """A forecast, logged once and NEVER modified afterward (the honesty
    rule: predictions are immutable/append-only). Resolution is a separate,
    later event recorded in PredictionResolution - not an edit to this row.
    `forecaster` is deliberately generic (not just "the LLM") so a human
    could own a prediction later without changing this model."""

    id: str
    created_date: date
    resolution_date: date  # before `date` would appear below, but there's no bare `date` field here
    statement: str
    probability: float
    forecaster: str


class PredictionResolution(BaseModel):
    """The real-world outcome for one Prediction, recorded separately so the
    original claim is never touched. `outcome` is deliberately not a plain
    bool - a genuine "we don't have enough evidence yet" is honest, not a
    failure, and forcing a fake true/false would violate the honesty rule."""

    prediction_id: str
    resolved_at: datetime
    outcome: str  # "true" | "false" | "unclear"
    reasoning: str
    resolver: str


class EchoCandidate(BaseModel):
    """The most similar 1926 article found for one TodayHeadline, by
    embedding similarity - time-filtered so it can never be dated after
    Arthur's own historical date. Persisted (not recomputed on every read)
    so `show`/the API never silently re-call the embeddings API."""

    today_headline_id: str
    historical_article_id: str
    historical_headline: str
    # historical_date must come before `date` - once a field named `date`
    # is declared, it shadows the `date` *type* for every later line in
    # this class body (same gotcha hit in api/schemas.py's DailyView).
    historical_date: date
    date: date
    distance: float
