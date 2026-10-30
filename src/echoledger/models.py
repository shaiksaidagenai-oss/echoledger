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
