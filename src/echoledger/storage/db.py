"""SQLite storage for historical articles and today's headlines.

We convert date/datetime to/from plain ISO strings ourselves rather than
relying on sqlite3's old automatic date adapters, which are deprecated.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime

from echoledger.models import ArthurDiaryEntry, HistoricalArticle, NewsSummary, TodayHeadline

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

CREATE TABLE IF NOT EXISTS arthur_diary_entries (
    date TEXT PRIMARY KEY,
    entry_text TEXT NOT NULL,
    source_article_ids TEXT NOT NULL,  -- JSON-encoded list[str]
    model TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS news_summaries (
    headline_id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    summary_text TEXT NOT NULL,
    model TEXT NOT NULL
);

-- Non-negotiable cost-control rule: log tokens + cost for every LLM call.
CREATE TABLE IF NOT EXISTS llm_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    called_at TEXT NOT NULL,
    purpose TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    estimated_cost_usd REAL NOT NULL
);
"""


def connect(db_path: str) -> sqlite3.Connection:
    """Open a connection and make sure both tables exist."""
    directory = os.path.dirname(db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def save_historical_article(conn: sqlite3.Connection, article: HistoricalArticle) -> None:
    """Does NOT commit - callers doing a single save should commit themselves;
    callers doing many saves (e.g. ingest_year) should commit once at the end.
    Committing after every row is what made a full year's ~65k-article
    ingest take many minutes instead of seconds."""
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
        "SELECT * FROM historical_articles WHERE date = ? ORDER BY page, id",
        (on_date.isoformat(),),
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


def save_diary_entry(conn: sqlite3.Connection, entry: ArthurDiaryEntry) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO arthur_diary_entries
            (date, entry_text, source_article_ids, model)
        VALUES (:date, :entry_text, :source_article_ids, :model)
        """,
        {
            "date": entry.date.isoformat(),
            "entry_text": entry.entry_text,
            "source_article_ids": json.dumps(entry.source_article_ids),
            "model": entry.model,
        },
    )
    conn.commit()


def get_diary_entry(conn: sqlite3.Connection, on_date: date) -> ArthurDiaryEntry | None:
    row = conn.execute(
        "SELECT * FROM arthur_diary_entries WHERE date = ?", (on_date.isoformat(),)
    ).fetchone()
    if row is None:
        return None
    return ArthurDiaryEntry(
        date=date.fromisoformat(row["date"]),
        entry_text=row["entry_text"],
        source_article_ids=json.loads(row["source_article_ids"]),
        model=row["model"],
    )


def save_news_summary(conn: sqlite3.Connection, summary: NewsSummary) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO news_summaries (headline_id, date, summary_text, model)
        VALUES (:headline_id, :date, :summary_text, :model)
        """,
        {
            "headline_id": summary.headline_id,
            "date": summary.date.isoformat(),
            "summary_text": summary.summary_text,
            "model": summary.model,
        },
    )
    conn.commit()


def get_news_summaries(conn: sqlite3.Connection, on_date: date) -> list[NewsSummary]:
    rows = conn.execute(
        "SELECT * FROM news_summaries WHERE date = ?", (on_date.isoformat(),)
    ).fetchall()
    return [
        NewsSummary(
            headline_id=row["headline_id"],
            date=date.fromisoformat(row["date"]),
            summary_text=row["summary_text"],
            model=row["model"],
        )
        for row in rows
    ]


def log_llm_usage(
    conn: sqlite3.Connection,
    *,
    purpose: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    estimated_cost_usd: float,
) -> None:
    conn.execute(
        """
        INSERT INTO llm_usage
            (called_at, purpose, model, input_tokens, output_tokens, estimated_cost_usd)
        VALUES (:called_at, :purpose, :model, :input_tokens, :output_tokens, :estimated_cost_usd)
        """,
        {
            "called_at": datetime.now().isoformat(),
            "purpose": purpose,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": estimated_cost_usd,
        },
    )
    conn.commit()
