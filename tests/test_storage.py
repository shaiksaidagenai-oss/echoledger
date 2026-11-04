import sqlite3
from datetime import date, datetime

import pytest

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
    get_diary_entry,
    get_historical_articles,
    get_news_summaries,
    get_pending_predictions,
    get_predictions_created_on,
    get_resolution,
    get_resolved_predictions,
    get_today_headlines,
    is_year_ingested,
    log_llm_usage,
    mark_year_ingested,
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


def test_save_and_get_historical_article(conn: sqlite3.Connection) -> None:
    article = HistoricalArticle(
        id="evestar-1926-10-29-p1-001",
        date=date(1926, 10, 29),
        newspaper="Evening Star",
        page=1,
        headline="15 YEARS FOR BANDIT WHO SHOT HUCKSTER",
        text="Maximum penalty given man who was captured in running battle.",
        source_url="https://chroniclingamerica.loc.gov/...",
    )
    save_historical_article(conn, article)

    result = get_historical_articles(conn, date(1926, 10, 29))

    assert result == [article]


def test_save_and_get_today_headline(conn: sqlite3.Connection) -> None:
    headline = TodayHeadline(
        id="bbc-2026-10-29-001",
        date=date(2026, 10, 29),
        source_name="BBC News",
        headline="Example world news headline",
        snippet="A short snippet summarizing the story in our own words.",
        url="https://www.bbc.co.uk/news/example",
        fetched_at=datetime(2026, 10, 29, 9, 0, 0),
    )
    save_today_headline(conn, headline)

    result = get_today_headlines(conn, date(2026, 10, 29))

    assert result == [headline]


def test_no_articles_for_an_unused_date_returns_empty_list(conn: sqlite3.Connection) -> None:
    assert get_historical_articles(conn, date(1926, 1, 1)) == []
    assert get_today_headlines(conn, date(2026, 1, 1)) == []


def test_saving_same_id_twice_replaces_instead_of_duplicating(conn: sqlite3.Connection) -> None:
    original = HistoricalArticle(
        id="same-id",
        date=date(1926, 10, 29),
        newspaper="Evening Star",
        page=1,
        headline="Original headline",
        text="Original text",
    )
    updated = original.model_copy(update={"headline": "Updated headline"})

    save_historical_article(conn, original)
    save_historical_article(conn, updated)

    result = get_historical_articles(conn, date(1926, 10, 29))

    assert len(result) == 1
    assert result[0].headline == "Updated headline"


def test_year_ingested_tracking(conn: sqlite3.Connection) -> None:
    assert is_year_ingested(conn, 1926, "evening_star") is False

    mark_year_ingested(conn, 1926, "evening_star")

    assert is_year_ingested(conn, 1926, "evening_star") is True
    assert is_year_ingested(conn, 1926, "some_other_paper") is False
    assert is_year_ingested(conn, 1927, "evening_star") is False


def test_save_and_get_diary_entry(conn: sqlite3.Connection) -> None:
    entry = ArthurDiaryEntry(
        date=date(1926, 10, 29),
        entry_text="Dear diary, today the papers spoke of President Coolidge...",
        source_article_ids=["evestar-1926-10-29-p1-001", "evestar-1926-10-29-p1-002"],
        model="claude-haiku-4-5",
    )

    save_diary_entry(conn, entry)

    assert get_diary_entry(conn, date(1926, 10, 29)) == entry
    assert get_diary_entry(conn, date(1926, 10, 30)) is None


def test_log_llm_usage_does_not_raise(conn: sqlite3.Connection) -> None:
    log_llm_usage(
        conn,
        purpose="arthur_diary",
        model="claude-haiku-4-5",
        input_tokens=500,
        output_tokens=200,
        estimated_cost_usd=0.0015,
    )

    row = conn.execute("SELECT * FROM llm_usage").fetchone()
    assert row["purpose"] == "arthur_diary"
    assert row["input_tokens"] == 500


def test_save_and_get_news_summary(conn: sqlite3.Connection) -> None:
    summary = NewsSummary(
        headline_id="bbc-abc123",
        date=date(2026, 10, 30),
        summary_text="A short paraphrased summary of the story.",
        model="claude-haiku-4-5",
    )

    save_news_summary(conn, summary)

    assert get_news_summaries(conn, date(2026, 10, 30)) == [summary]
    assert get_news_summaries(conn, date(2026, 10, 31)) == []


def test_save_prediction_and_get_predictions_created_on(conn: sqlite3.Connection) -> None:
    prediction = Prediction(
        id="pred-1",
        created_date=date(2026, 10, 30),
        resolution_date=date(2026, 12, 1),
        statement="Will X happen by Dec 1?",
        probability=0.4,
        forecaster="claude-haiku-4-5",
    )

    save_prediction(conn, prediction)

    assert get_predictions_created_on(conn, date(2026, 10, 30)) == [prediction]
    assert get_predictions_created_on(conn, date(2026, 10, 31)) == []


def test_save_prediction_twice_raises_instead_of_overwriting(conn: sqlite3.Connection) -> None:
    prediction = Prediction(
        id="pred-1",
        created_date=date(2026, 10, 30),
        resolution_date=date(2026, 12, 1),
        statement="Will X happen?",
        probability=0.4,
        forecaster="claude-haiku-4-5",
    )
    save_prediction(conn, prediction)

    with pytest.raises(sqlite3.IntegrityError):
        save_prediction(conn, prediction)


def test_get_pending_predictions_only_returns_due_unresolved_ones(
    conn: sqlite3.Connection,
) -> None:
    due = Prediction(
        id="due",
        created_date=date(2026, 10, 1),
        resolution_date=date(2026, 10, 30),
        statement="Due prediction",
        probability=0.5,
        forecaster="claude-haiku-4-5",
    )
    not_yet_due = Prediction(
        id="not-due",
        created_date=date(2026, 10, 1),
        resolution_date=date(2026, 12, 31),
        statement="Not due yet",
        probability=0.5,
        forecaster="claude-haiku-4-5",
    )
    already_resolved = Prediction(
        id="resolved",
        created_date=date(2026, 10, 1),
        resolution_date=date(2026, 10, 15),
        statement="Already resolved",
        probability=0.5,
        forecaster="claude-haiku-4-5",
    )
    for p in (due, not_yet_due, already_resolved):
        save_prediction(conn, p)
    save_resolution(
        conn,
        PredictionResolution(
            prediction_id="resolved",
            resolved_at=datetime(2026, 10, 16, 9, 0, 0),
            outcome="true",
            reasoning="It happened.",
            resolver="claude-haiku-4-5",
        ),
    )

    pending = get_pending_predictions(conn, as_of_date=date(2026, 10, 30))

    assert {p.id for p in pending} == {"due"}


def test_save_and_get_resolution(conn: sqlite3.Connection) -> None:
    save_prediction(
        conn,
        Prediction(
            id="pred-1",
            created_date=date(2026, 10, 1),
            resolution_date=date(2026, 10, 30),
            statement="Will X happen?",
            probability=0.6,
            forecaster="claude-haiku-4-5",
        ),
    )
    resolution = PredictionResolution(
        prediction_id="pred-1",
        resolved_at=datetime(2026, 10, 30, 9, 0, 0),
        outcome="false",
        reasoning="It did not happen based on accumulated news.",
        resolver="claude-haiku-4-5",
    )

    save_resolution(conn, resolution)

    assert get_resolution(conn, "pred-1") == resolution
    assert get_resolution(conn, "nonexistent") is None

    resolved = get_resolved_predictions(conn)
    assert len(resolved) == 1
    assert resolved[0][0].id == "pred-1"
    assert resolved[0][1].outcome == "false"
