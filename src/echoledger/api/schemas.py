"""Response shapes for the API - distinct from the storage models in
models.py, since what we show a reader isn't the same shape as what we
store (e.g. a news item here combines a TodayHeadline with its NewsSummary)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class NewsItemView(BaseModel):
    source_name: str
    headline: str
    summary: str
    url: str


class DailyView(BaseModel):
    # historical_date must come before `date` - once a field named `date` is
    # declared, it shadows the `date` *type* for every later line in this
    # class body, so a field after it typed `date` would resolve wrong.
    historical_date: date
    date: date
    historical_newspaper: str | None
    diary_entry: str | None
    news: list[NewsItemView]
