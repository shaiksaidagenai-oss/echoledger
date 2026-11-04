"""Embeds HistoricalArticles/TodayHeadlines into the vector store.

Idempotent: skips anything already indexed by ID, so re-running never pays
OpenAI twice for the same article. Dates are stored as an integer
(date_int, e.g. 19261029) because Chroma's $lte/$gte filters require a
number, not a string - confirmed empirically, not assumed.
"""

from __future__ import annotations

import sqlite3

from chromadb.api.models.Collection import Collection
from openai import OpenAI

from echoledger.models import HistoricalArticle, TodayHeadline
from echoledger.rag.embeddings import embed_texts
from echoledger.rag.vector_store import get_collection


def _date_to_int(on_date_iso: str) -> int:
    return int(on_date_iso.replace("-", ""))


def index_historical_articles(
    conn: sqlite3.Connection,
    articles: list[HistoricalArticle],
    client: OpenAI | None = None,
    collection: Collection | None = None,
) -> int:
    """Returns how many articles were newly embedded (0 if all were
    already indexed)."""
    if not articles:
        return 0
    if collection is None:
        collection = get_collection()
    existing_ids = set(collection.get(ids=[a.id for a in articles])["ids"])
    new_articles = [a for a in articles if a.id not in existing_ids]
    if not new_articles:
        return 0

    texts = [f"{a.headline}\n{a.text}" for a in new_articles]
    embeddings = embed_texts(conn, texts, purpose="embed_historical", client=client)

    collection.upsert(
        ids=[a.id for a in new_articles],
        embeddings=embeddings,  # type: ignore[arg-type]  # list[list[float]] is valid at runtime
        metadatas=[
            {
                "kind": "historical",
                "date": a.date.isoformat(),
                "date_int": _date_to_int(a.date.isoformat()),
                "newspaper": a.newspaper,
            }
            for a in new_articles
        ],
        documents=[a.headline for a in new_articles],
    )
    return len(new_articles)


def index_today_headlines(
    conn: sqlite3.Connection,
    headlines: list[TodayHeadline],
    client: OpenAI | None = None,
    collection: Collection | None = None,
) -> int:
    if not headlines:
        return 0
    if collection is None:
        collection = get_collection()
    existing_ids = set(collection.get(ids=[h.id for h in headlines])["ids"])
    new_headlines = [h for h in headlines if h.id not in existing_ids]
    if not new_headlines:
        return 0

    texts = [h.headline for h in new_headlines]
    embeddings = embed_texts(conn, texts, purpose="embed_today", client=client)

    collection.upsert(
        ids=[h.id for h in new_headlines],
        embeddings=embeddings,  # type: ignore[arg-type]  # list[list[float]] is valid at runtime
        metadatas=[
            {
                "kind": "today",
                "date": h.date.isoformat(),
                "date_int": _date_to_int(h.date.isoformat()),
                "source_name": h.source_name,
            }
            for h in new_headlines
        ],
        documents=[h.headline for h in new_headlines],
    )
    return len(new_headlines)
