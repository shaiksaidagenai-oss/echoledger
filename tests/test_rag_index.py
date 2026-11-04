import sqlite3
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from chromadb.api.models.Collection import Collection

from echoledger.models import HistoricalArticle, TodayHeadline
from echoledger.rag.index import index_historical_articles, index_today_headlines
from echoledger.rag.vector_store import get_collection
from echoledger.storage.db import connect


class _FakeEmbeddings:
    def create(self, input: list[str], **kwargs: object) -> SimpleNamespace:
        vectors = [[float(i), 0.0] for i in range(len(input))]
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=v) for v in vectors],
            usage=SimpleNamespace(total_tokens=10),
        )


class _FakeClient:
    def __init__(self) -> None:
        self.embeddings = _FakeEmbeddings()


@pytest.fixture
def conn() -> sqlite3.Connection:
    return connect(":memory:")


@pytest.fixture
def collection(tmp_path: Path) -> Collection:
    return get_collection(path=str(tmp_path / "chroma"))


def _article(article_id: str, headline: str = "A headline") -> HistoricalArticle:
    return HistoricalArticle(
        id=article_id,
        date=date(1926, 10, 29),
        newspaper="Evening Star",
        page=1,
        headline=headline,
        text="text",
    )


def test_index_historical_articles_embeds_and_stores(
    conn: sqlite3.Connection, collection: Collection
) -> None:
    articles = [_article("a1"), _article("a2")]

    count = index_historical_articles(
        conn, articles, client=_FakeClient(), collection=collection  # type: ignore[arg-type]
    )

    assert count == 2
    stored = collection.get(ids=["a1", "a2"])
    assert set(stored["ids"]) == {"a1", "a2"}


def test_index_historical_articles_skips_already_indexed(
    conn: sqlite3.Connection, collection: Collection
) -> None:
    articles = [_article("a1"), _article("a2")]
    index_historical_articles(
        conn, articles, client=_FakeClient(), collection=collection  # type: ignore[arg-type]
    )

    second_count = index_historical_articles(
        conn, articles, client=_FakeClient(), collection=collection  # type: ignore[arg-type]
    )

    assert second_count == 0


def test_index_today_headlines_embeds_and_stores(
    conn: sqlite3.Connection, collection: Collection
) -> None:
    headline = TodayHeadline(
        id="h1",
        date=date(2026, 10, 30),
        source_name="BBC News",
        headline="A headline",
        snippet="snip",
        url="https://example.com",
        fetched_at=datetime(2026, 10, 30, 9, 0, 0),
    )

    count = index_today_headlines(
        conn, [headline], client=_FakeClient(), collection=collection  # type: ignore[arg-type]
    )

    assert count == 1
