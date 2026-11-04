"""Builds the DailyView shown for a date, by reading what's already stored.

Read-only: never fetches or calls the LLM - that's `echoledger fetch`'s job.
If a summary hasn't been generated yet for a headline, falls back to its
raw (already copyright-safe) snippet rather than showing nothing.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from echoledger.api.schemas import (
    DailyView,
    EchoView,
    NewsItemView,
    PredictionView,
    ResolvedPredictionView,
    ScorecardView,
)
from echoledger.evals.brier import brier_score
from echoledger.storage.db import (
    get_diary_entry,
    get_echo_candidates,
    get_historical_articles,
    get_news_summaries,
    get_predictions_created_on,
    get_resolved_predictions,
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
    echoes_by_id = {c.today_headline_id: c for c in get_echo_candidates(conn, on_date)}

    news = []
    for h in headlines:
        echo = echoes_by_id.get(h.id)
        news.append(
            NewsItemView(
                source_name=h.source_name,
                headline=h.headline,
                summary=(
                    summaries_by_id[h.id].summary_text if h.id in summaries_by_id else h.snippet
                ),
                url=h.url,
                echo=(
                    EchoView(
                        historical_headline=echo.historical_headline,
                        historical_date=echo.historical_date,
                        distance=echo.distance,
                    )
                    if echo
                    else None
                ),
            )
        )

    predictions = [
        PredictionView(
            statement=p.statement,
            probability=p.probability,
            resolution_date=p.resolution_date,
        )
        for p in get_predictions_created_on(conn, on_date)
    ]

    return DailyView(
        date=on_date,
        historical_date=historical_date,
        historical_newspaper=historical_newspaper,
        diary_entry=diary.entry_text if diary else None,
        news=news,
        predictions=predictions,
    )


def build_scorecard_view(conn: sqlite3.Connection) -> ScorecardView:
    resolved = get_resolved_predictions(conn)
    return ScorecardView(
        brier_score=brier_score(resolved),
        resolved=[
            ResolvedPredictionView(
                statement=prediction.statement,
                probability=prediction.probability,
                outcome=resolution.outcome,
                reasoning=resolution.reasoning,
            )
            for prediction, resolution in resolved
        ],
    )
