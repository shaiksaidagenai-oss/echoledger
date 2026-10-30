"""Builds the DailyView shown for a date, by reading what's already stored.

Read-only: never fetches or calls the LLM - that's `echoledger fetch`'s job.
If a summary hasn't been generated yet for a headline, falls back to its
raw (already copyright-safe) snippet rather than showing nothing.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from echoledger.api.schemas import DailyView, NewsItemView
from echoledger.storage.db import (
    get_diary_entry,
    get_historical_articles,
    get_news_summaries,
    get_today_headlines,
)
from echoledger.utils.dates import years_ago


def build_daily_view(conn: sqlite3.Connection, on_date: date) -> DailyView:
    historical_date = years_ago(on_date, 100)

    historical_articles = get_historical_articles(conn, historical_date)
    historical_newspaper = historical_articles[0].newspaper if historical_articles else None

    diary = get_diary_entry(conn, historical_date)

    headlines = get_today_headlines(conn, on_date)
    summaries_by_id = {s.headline_id: s for s in get_news_summaries(conn, on_date)}

    news = [
        NewsItemView(
            source_name=h.source_name,
            headline=h.headline,
            summary=(
                summaries_by_id[h.id].summary_text if h.id in summaries_by_id else h.snippet
            ),
            url=h.url,
        )
        for h in headlines
    ]

    return DailyView(
        date=on_date,
        historical_date=historical_date,
        historical_newspaper=historical_newspaper,
        diary_entry=diary.entry_text if diary else None,
        news=news,
    )
