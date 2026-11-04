import sqlite3
from datetime import date, datetime

import pytest

from echoledger.api.views import build_daily_view, build_scorecard_view
from echoledger.models import (
    ArthurDiaryEntry,
    HistoricalArticle,
    NewsSummary,
    Prediction,
    PredictionResolution,
    TodayHeadline,
)
from echoledger.storage.db import (
    connect,
    save_diary_entry,
    save_historical_article,
    save_news_summary,
    save_prediction,
    save_resolution,
    save_today_headline,
)


@pytest.fixture
def conn() -> sqlite3.Connection:
    return connect(":memory:")


def test_build_daily_view_with_no_data_at_all(conn: sqlite3.Connection) -> None:
    view = build_daily_view(conn, date(2026, 10, 30))

    assert view.date == date(2026, 10, 30)
    assert view.historical_date == date(1926, 10, 30)
    assert view.historical_newspaper is None
    assert view.diary_entry is None
    assert view.news == []


def test_build_daily_view_combines_everything(conn: sqlite3.Connection) -> None:
    save_historical_article(
        conn,
        HistoricalArticle(
            id="a1",
            date=date(1926, 10, 30),
            newspaper="Evening Star",
            page=1,
            headline="A headline",
            text="Article text",
        ),
    )
    save_diary_entry(
        conn,
        ArthurDiaryEntry(
            date=date(1926, 10, 30),
            entry_text="Dear diary...",
            source_article_ids=["a1"],
            model="claude-haiku-4-5",
        ),
    )
    save_today_headline(
        conn,
        TodayHeadline(
            id="h1",
            date=date(2026, 10, 30),
            source_name="BBC News",
            headline="A modern headline",
            snippet="Raw RSS snippet.",
            url="https://example.com/1",
            fetched_at=datetime(2026, 10, 30, 9, 0, 0),
        ),
    )
    save_news_summary(
        conn,
        NewsSummary(
            headline_id="h1",
            date=date(2026, 10, 30),
            summary_text="Our paraphrased summary.",
            model="claude-haiku-4-5",
        ),
    )

    view = build_daily_view(conn, date(2026, 10, 30))

    assert view.historical_newspaper == "Evening Star"
    assert view.diary_entry == "Dear diary..."
    assert len(view.news) == 1
    assert view.news[0].summary == "Our paraphrased summary."  # not the raw snippet


def test_build_daily_view_falls_back_to_snippet_without_a_summary_yet(
    conn: sqlite3.Connection,
) -> None:
    save_today_headline(
        conn,
        TodayHeadline(
            id="h1",
            date=date(2026, 10, 30),
            source_name="BBC News",
            headline="A modern headline",
            snippet="Raw RSS snippet.",
            url="https://example.com/1",
            fetched_at=datetime(2026, 10, 30, 9, 0, 0),
        ),
    )
    # No save_news_summary call - summarization hasn't run yet.

    view = build_daily_view(conn, date(2026, 10, 30))

    assert view.news[0].summary == "Raw RSS snippet."


def test_build_daily_view_includes_predictions_made_that_day(conn: sqlite3.Connection) -> None:
    save_prediction(
        conn,
        Prediction(
            id="pred-1",
            created_date=date(2026, 10, 30),
            resolution_date=date(2026, 12, 1),
            statement="Will X happen?",
            probability=0.7,
            forecaster="claude-haiku-4-5",
        ),
    )

    view = build_daily_view(conn, date(2026, 10, 30))

    assert len(view.predictions) == 1
    assert view.predictions[0].statement == "Will X happen?"
    assert view.predictions[0].probability == 0.7


def test_build_scorecard_view_with_nothing_resolved(conn: sqlite3.Connection) -> None:
    view = build_scorecard_view(conn)

    assert view.brier_score is None
    assert view.resolved == []


def test_build_scorecard_view_includes_brier_score(conn: sqlite3.Connection) -> None:
    save_prediction(
        conn,
        Prediction(
            id="pred-1",
            created_date=date(2026, 10, 1),
            resolution_date=date(2026, 10, 30),
            statement="Will X happen?",
            probability=1.0,
            forecaster="claude-haiku-4-5",
        ),
    )
    save_resolution(
        conn,
        PredictionResolution(
            prediction_id="pred-1",
            resolved_at=datetime(2026, 10, 30, 9, 0, 0),
            outcome="true",
            reasoning="It happened, confirmed by the news.",
            resolver="claude-haiku-4-5",
        ),
    )

    view = build_scorecard_view(conn)

    assert view.brier_score == 0.0  # predicted 100%, it happened - perfect
    assert len(view.resolved) == 1
    assert view.resolved[0].outcome == "true"
