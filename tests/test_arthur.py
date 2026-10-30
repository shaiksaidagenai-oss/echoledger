import sqlite3
from datetime import date
from types import SimpleNamespace

import pytest

from echoledger.llm.arthur import write_diary_entry
from echoledger.models import HistoricalArticle
from echoledger.storage.db import connect, get_diary_entry


class _FakeMessages:
    def __init__(self, entry_text: str, input_tokens: int, output_tokens: int) -> None:
        self._response = SimpleNamespace(
            parsed_output=SimpleNamespace(entry_text=entry_text),
            usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
        )

    def parse(self, **kwargs: object) -> SimpleNamespace:
        return self._response


class _FakeClient:
    def __init__(self, entry_text: str, input_tokens: int = 500, output_tokens: int = 200) -> None:
        self.messages = _FakeMessages(entry_text, input_tokens, output_tokens)


@pytest.fixture
def conn() -> sqlite3.Connection:
    return connect(":memory:")


def _article(article_id: str, headline: str) -> HistoricalArticle:
    return HistoricalArticle(
        id=article_id,
        date=date(1926, 10, 29),
        newspaper="Evening Star",
        page=1,
        headline=headline,
        text="Some real article text.",
    )


def test_write_diary_entry_saves_and_returns_entry(conn: sqlite3.Connection) -> None:
    articles = [_article("a1", "First headline"), _article("a2", "Second headline")]
    fake_client = _FakeClient(entry_text="Dear diary, today was a remarkable day...")

    entry = write_diary_entry(
        conn,
        historical_date=date(1926, 10, 29),
        articles=articles,
        model="claude-haiku-4-5",
        client=fake_client,  # type: ignore[arg-type]
    )

    assert entry.entry_text == "Dear diary, today was a remarkable day..."
    assert entry.source_article_ids == ["a1", "a2"]
    assert entry.model == "claude-haiku-4-5"
    assert get_diary_entry(conn, date(1926, 10, 29)) == entry


def test_write_diary_entry_logs_token_usage(conn: sqlite3.Connection) -> None:
    fake_client = _FakeClient(entry_text="...", input_tokens=1234, output_tokens=567)

    write_diary_entry(
        conn,
        historical_date=date(1926, 10, 29),
        articles=[_article("a1", "A headline")],
        model="claude-haiku-4-5",
        client=fake_client,  # type: ignore[arg-type]
    )

    row = conn.execute("SELECT * FROM llm_usage").fetchone()
    assert row["input_tokens"] == 1234
    assert row["output_tokens"] == 567
    assert row["purpose"] == "arthur_diary"


def test_write_diary_entry_caps_source_articles_at_max(conn: sqlite3.Connection) -> None:
    many_articles = [_article(f"a{i}", f"Headline {i}") for i in range(20)]
    fake_client = _FakeClient(entry_text="...")

    entry = write_diary_entry(
        conn,
        historical_date=date(1926, 10, 29),
        articles=many_articles,
        model="claude-haiku-4-5",
        client=fake_client,  # type: ignore[arg-type]
    )

    assert len(entry.source_article_ids) == 6  # MAX_SOURCE_ARTICLES
