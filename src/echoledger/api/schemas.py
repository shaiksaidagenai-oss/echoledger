"""Response shapes for the API - distinct from the storage models in
models.py, since what we show a reader isn't the same shape as what we
store (e.g. a news item here combines a TodayHeadline with its NewsSummary)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class EchoView(BaseModel):
    historical_headline: str
    historical_date: date
    distance: float


class NewsItemView(BaseModel):
    source_name: str
    headline: str
    summary: str
    url: str
    echo: EchoView | None = None


class PredictionView(BaseModel):
    statement: str
    probability: float
    resolution_date: date


class DailyView(BaseModel):
    # historical_date must come before `date` - once a field named `date` is
    # declared, it shadows the `date` *type* for every later line in this
    # class body, so a field after it typed `date` would resolve wrong.
    historical_date: date
    date: date
    historical_newspaper: str | None
    diary_entry: str | None
    diary_pending: bool  # True if a draft exists but hasn't been approved yet
    news: list[NewsItemView]
    predictions: list[PredictionView]


class ResolvedPredictionView(BaseModel):
    statement: str
    probability: float
    outcome: str
    reasoning: str


class ScorecardView(BaseModel):
    brier_score: float | None
    resolved: list[ResolvedPredictionView]
