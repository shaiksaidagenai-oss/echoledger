"""SQLite storage for historical articles and today's headlines.

We convert date/datetime to/from plain ISO strings ourselves rather than
relying on sqlite3's old automatic date adapters, which are deprecated.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime

from echoledger.models import HistoricalArticle, TodayHeadline

_SCHEMA = """
CREATE TABLE IF NOT EXISTS historical_articles (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    newspaper TEXT NOT NULL,
    page INTEGER NOT NULL,
    headline TEXT NOT NULL,
    text TEXT NOT NULL,
    source_url TEXT
);

CREATE TABLE IF NOT EXISTS today_headlines (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    source_name TEXT NOT NULL,
    headline TEXT NOT NULL,
    snippet TEXT NOT NULL,
    url TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);

-- Tracks which (year, newspaper) archives we've already fully scanned, so
-- `fetch` only walks a year's ~1GB tar.gz once rather than on every call.
CREATE TABLE IF NOT EXISTS ingested_years (
    year INTEGER NOT NULL,
    newspaper TEXT NOT NULL,
    PRIMARY KEY (year, newspaper)
);
"""


def connect(db_path: str) -> sqlite3.Connection:
    """Open a connection and make sure both tables exist."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def save_historical_article(conn: sqlite3.Connection, article: HistoricalArticle) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO historical_articles
            (id, date, newspaper, page, headline, text, source_url)
        VALUES (:id, :date, :newspaper, :page, :headline, :text, :source_url)
        """,
        {
            "id": article.id,
            "date": article.date.isoformat(),
            "newspaper": article.newspaper,
            "page": article.page,
            "headline": article.headline,
            "text": article.text,
            "source_url": article.source_url,
        },
    )
    conn.commit()


def save_today_headline(conn: sqlite3.Connection, headline: TodayHeadline) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO today_headlines
            (id, date, source_name, headline, snippet, url, fetched_at)
        VALUES (:id, :date, :source_name, :headline, :snippet, :url, :fetched_at)
        """,
        {
            "id": headline.id,
            "date": headline.date.isoformat(),
            "source_name": headline.source_name,
            "headline": headline.headline,
            "snippet": headline.snippet,
            "url": headline.url,
            "fetched_at": headline.fetched_at.isoformat(),
        },
    )
    conn.commit()


def get_historical_articles(conn: sqlite3.Connection, on_date: date) -> list[HistoricalArticle]:
    rows = conn.execute(
        "SELECT * FROM historical_articles WHERE date = ?", (on_date.isoformat(),)
    ).fetchall()
    return [
        HistoricalArticle(
            id=row["id"],
            date=date.fromisoformat(row["date"]),
            newspaper=row["newspaper"],
            page=row["page"],
            headline=row["headline"],
            text=row["text"],
            source_url=row["source_url"],
        )
        for row in rows
    ]


def is_year_ingested(conn: sqlite3.Connection, year: int, newspaper: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM ingested_years WHERE year = ? AND newspaper = ?", (year, newspaper)
    ).fetchone()
    return row is not None


def mark_year_ingested(conn: sqlite3.Connection, year: int, newspaper: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO ingested_years (year, newspaper) VALUES (?, ?)",
        (year, newspaper),
    )
    conn.commit()


def get_today_headlines(conn: sqlite3.Connection, on_date: date) -> list[TodayHeadline]:
    rows = conn.execute(
        "SELECT * FROM today_headlines WHERE date = ?", (on_date.isoformat(),)
    ).fetchall()
    return [
        TodayHeadline(
            id=row["id"],
            date=date.fromisoformat(row["date"]),
            source_name=row["source_name"],
            headline=row["headline"],
            snippet=row["snippet"],
            url=row["url"],
            fetched_at=datetime.fromisoformat(row["fetched_at"]),
        )
        for row in rows
    ]
