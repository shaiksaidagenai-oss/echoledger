"""SQLite storage for historical articles and today's headlines.

We convert date/datetime to/from plain ISO strings ourselves rather than
relying on sqlite3's old automatic date adapters, which are deprecated.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime

from echoledger.models import (
    ArthurDiaryEntry,
    EchoCandidate,
    HistoricalArticle,
    NewsSummary,
    Prediction,
    PredictionResolution,
    TodayHeadline,
)

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

CREATE TABLE IF NOT EXISTS echo_candidates (
    today_headline_id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    historical_article_id TEXT NOT NULL,
    historical_headline TEXT NOT NULL,
    historical_date TEXT NOT NULL,
    distance REAL NOT NULL
);

-- Honesty rule: predictions are immutable/append-only once logged. No code
-- in this file ever UPDATEs a row here - only INSERTs. Resolution is a
-- separate table (below), never an edit to this one.
CREATE TABLE IF NOT EXISTS predictions (
    id TEXT PRIMARY KEY,
    created_date TEXT NOT NULL,
    resolution_date TEXT NOT NULL,
    statement TEXT NOT NULL,
    probability REAL NOT NULL,
    forecaster TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prediction_resolutions (
    prediction_id TEXT PRIMARY KEY,
    resolved_at TEXT NOT NULL,
    outcome TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    resolver TEXT NOT NULL
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


def save_echo_candidate(conn: sqlite3.Connection, candidate: EchoCandidate) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO echo_candidates
            (today_headline_id, date, historical_article_id, historical_headline,
             historical_date, distance)
        VALUES (:today_headline_id, :date, :historical_article_id, :historical_headline,
                :historical_date, :distance)
        """,
        {
            "today_headline_id": candidate.today_headline_id,
            "date": candidate.date.isoformat(),
            "historical_article_id": candidate.historical_article_id,
            "historical_headline": candidate.historical_headline,
            "historical_date": candidate.historical_date.isoformat(),
            "distance": candidate.distance,
        },
    )
    conn.commit()


def get_echo_candidates(conn: sqlite3.Connection, on_date: date) -> list[EchoCandidate]:
    rows = conn.execute(
        "SELECT * FROM echo_candidates WHERE date = ?", (on_date.isoformat(),)
    ).fetchall()
    return [
        EchoCandidate(
            today_headline_id=row["today_headline_id"],
            date=date.fromisoformat(row["date"]),
            historical_article_id=row["historical_article_id"],
            historical_headline=row["historical_headline"],
            historical_date=date.fromisoformat(row["historical_date"]),
            distance=row["distance"],
        )
        for row in rows
    ]


def save_prediction(conn: sqlite3.Connection, prediction: Prediction) -> None:
    """Plain INSERT, not INSERT OR REPLACE: saving the same id twice must
    fail loudly (sqlite3.IntegrityError), not silently overwrite - that's
    the honesty rule (predictions are immutable) enforced at the DB level,
    not just by convention."""
    conn.execute(
        """
        INSERT INTO predictions
            (id, created_date, resolution_date, statement, probability, forecaster)
        VALUES (:id, :created_date, :resolution_date, :statement, :probability, :forecaster)
        """,
        {
            "id": prediction.id,
            "created_date": prediction.created_date.isoformat(),
            "resolution_date": prediction.resolution_date.isoformat(),
            "statement": prediction.statement,
            "probability": prediction.probability,
            "forecaster": prediction.forecaster,
        },
    )
    conn.commit()


def _prediction_from_row(row: sqlite3.Row) -> Prediction:
    return Prediction(
        id=row["id"],
        created_date=date.fromisoformat(row["created_date"]),
        resolution_date=date.fromisoformat(row["resolution_date"]),
        statement=row["statement"],
        probability=row["probability"],
        forecaster=row["forecaster"],
    )


def get_predictions_created_on(conn: sqlite3.Connection, on_date: date) -> list[Prediction]:
    rows = conn.execute(
        "SELECT * FROM predictions WHERE created_date = ?", (on_date.isoformat(),)
    ).fetchall()
    return [_prediction_from_row(row) for row in rows]


def get_pending_predictions(conn: sqlite3.Connection, as_of_date: date) -> list[Prediction]:
    """Predictions due to be resolved (resolution_date <= as_of_date) that
    don't have a resolution row yet."""
    rows = conn.execute(
        """
        SELECT p.* FROM predictions p
        LEFT JOIN prediction_resolutions r ON p.id = r.prediction_id
        WHERE p.resolution_date <= ? AND r.prediction_id IS NULL
        """,
        (as_of_date.isoformat(),),
    ).fetchall()
    return [_prediction_from_row(row) for row in rows]


def save_resolution(conn: sqlite3.Connection, resolution: PredictionResolution) -> None:
    """Also a plain INSERT - a prediction can only ever be resolved once."""
    conn.execute(
        """
        INSERT INTO prediction_resolutions
            (prediction_id, resolved_at, outcome, reasoning, resolver)
        VALUES (:prediction_id, :resolved_at, :outcome, :reasoning, :resolver)
        """,
        {
            "prediction_id": resolution.prediction_id,
            "resolved_at": resolution.resolved_at.isoformat(),
            "outcome": resolution.outcome,
            "reasoning": resolution.reasoning,
            "resolver": resolution.resolver,
        },
    )
    conn.commit()


def get_resolution(conn: sqlite3.Connection, prediction_id: str) -> PredictionResolution | None:
    row = conn.execute(
        "SELECT * FROM prediction_resolutions WHERE prediction_id = ?", (prediction_id,)
    ).fetchone()
    if row is None:
        return None
    return PredictionResolution(
        prediction_id=row["prediction_id"],
        resolved_at=datetime.fromisoformat(row["resolved_at"]),
        outcome=row["outcome"],
        reasoning=row["reasoning"],
        resolver=row["resolver"],
    )


def get_resolved_predictions(
    conn: sqlite3.Connection,
) -> list[tuple[Prediction, PredictionResolution]]:
    """Every prediction that has a resolution, for scorecard/Brier scoring."""
    rows = conn.execute(
        """
        SELECT p.*, r.resolved_at, r.outcome, r.reasoning, r.resolver
        FROM predictions p
        JOIN prediction_resolutions r ON p.id = r.prediction_id
        """
    ).fetchall()
    results = []
    for row in rows:
        prediction = _prediction_from_row(row)
        resolution = PredictionResolution(
            prediction_id=row["id"],
            resolved_at=datetime.fromisoformat(row["resolved_at"]),
            outcome=row["outcome"],
            reasoning=row["reasoning"],
            resolver=row["resolver"],
        )
        results.append((prediction, resolution))
    return results


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
