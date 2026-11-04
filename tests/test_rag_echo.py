import sqlite3
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from chromadb.api.models.Collection import Collection

from echoledger.models import HistoricalArticle, TodayHeadline
from echoledger.rag.echo import find_echo_candidates
from echoledger.rag.index import index_historical_articles
from echoledger.rag.vector_store import get_collection
from echoledger.storage.db import connect


class _FakeEmbeddings:
    """Every text gets the same vector - these tests check the date filter,
    not embedding semantics, so similarity should be a tie except for date."""

    def create(self, input: list[str], **kwargs: object) -> SimpleNamespace:
        vectors = [[1.0, 0.0] for _ in input]
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


def _historical(article_id: str, on_date: date, headline: str) -> HistoricalArticle:
    return HistoricalArticle(
        id=article_id, date=on_date, newspaper="Evening Star", page=1, headline=headline, text="t"
    )


def test_find_echo_candidates_excludes_articles_after_the_max_date(
    conn: sqlite3.Connection, collection: Collection
) -> None:
    old_article = _historical("old", date(1926, 10, 28), "Old headline")
    future_article = _historical("future", date(1926, 10, 31), "Future headline")
    fake_client = _FakeClient()

    index_historical_articles(
        conn, [old_article, future_article], client=fake_client, collection=collection  # type: ignore[arg-type]
    )

    headline = TodayHeadline(
        id="h1",
        date=date(2026, 10, 30),
        source_name="BBC News",
        headline="Today's headline",
        snippet="snip",
        url="https://example.com",
        fetched_at=datetime(2026, 10, 30, 9, 0, 0),
    )

    candidates = find_echo_candidates(
        conn,
        [headline],
        max_historical_date=date(1926, 10, 30),
        client=fake_client,  # type: ignore[arg-type]
        collection=collection,
    )

    assert len(candidates) == 1
    assert candidates[0].historical_article_id == "old"  # future_article filtered out


def test_find_echo_candidates_with_no_headlines_returns_empty(
    conn: sqlite3.Connection, collection: Collection
) -> None:
    result = find_echo_candidates(
        conn, [], max_historical_date=date(1926, 10, 30), client=object(), collection=collection  # type: ignore[arg-type]
    )

    assert result == []
