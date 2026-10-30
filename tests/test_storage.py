import sqlite3
from datetime import date, datetime

import pytest

from echoledger.models import HistoricalArticle, TodayHeadline
from echoledger.storage.db import (
    connect,
    get_historical_articles,
    get_today_headlines,
    save_historical_article,
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
