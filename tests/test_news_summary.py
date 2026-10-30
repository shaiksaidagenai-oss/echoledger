import sqlite3
from datetime import date, datetime
from types import SimpleNamespace

import pytest

from echoledger.llm.news_summary import summarize_headlines
from echoledger.models import TodayHeadline
from echoledger.storage.db import connect, get_news_summaries


class _FakeMessages:
    def __init__(self, items: list[dict[str, str]], input_tokens: int, output_tokens: int) -> None:
        self._response = SimpleNamespace(
            parsed_output=SimpleNamespace(
                summaries=[SimpleNamespace(**item) for item in items]
            ),
            usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
        )

    def parse(self, **kwargs: object) -> SimpleNamespace:
        return self._response


class _FakeClient:
    def __init__(
        self, items: list[dict[str, str]], input_tokens: int = 300, output_tokens: int = 100
    ) -> None:
        self.messages = _FakeMessages(items, input_tokens, output_tokens)


@pytest.fixture
def conn() -> sqlite3.Connection:
    return connect(":memory:")


def _headline(headline_id: str, text: str) -> TodayHeadline:
    return TodayHeadline(
        id=headline_id,
        date=date(2026, 10, 30),
        source_name="BBC News",
        headline=text,
        snippet="Some RSS snippet text.",
        url=f"https://example.com/{headline_id}",
        fetched_at=datetime(2026, 10, 30, 9, 0, 0),
    )


def test_summarize_headlines_saves_and_returns_summaries(conn: sqlite3.Connection) -> None:
    headlines = [_headline("h1", "First story"), _headline("h2", "Second story")]
    fake_client = _FakeClient(
        items=[
            {"headline_id": "h1", "summary_text": "Paraphrase of the first story."},
            {"headline_id": "h2", "summary_text": "Paraphrase of the second story."},
        ]
    )

    summaries = summarize_headlines(
        conn, date(2026, 10, 30), headlines, model="claude-haiku-4-5", client=fake_client  # type: ignore[arg-type]
    )

    assert len(summaries) == 2
    assert summaries[0].headline_id == "h1"
    assert get_news_summaries(conn, date(2026, 10, 30)) == summaries


def test_summarize_headlines_logs_usage(conn: sqlite3.Connection) -> None:
    fake_client = _FakeClient(
        items=[{"headline_id": "h1", "summary_text": "..."}],
        input_tokens=321,
        output_tokens=98,
    )

    summarize_headlines(
        conn,
        date(2026, 10, 30),
        [_headline("h1", "A story")],
        model="claude-haiku-4-5",
        client=fake_client,  # type: ignore[arg-type]
    )

    row = conn.execute("SELECT * FROM llm_usage").fetchone()
    assert row["purpose"] == "news_summary"
    assert row["input_tokens"] == 321
    assert row["output_tokens"] == 98


def test_summarize_headlines_with_no_headlines_makes_no_api_call(conn: sqlite3.Connection) -> None:
    result = summarize_headlines(
        conn, date(2026, 10, 30), [], model="claude-haiku-4-5", client=object()  # type: ignore[arg-type]
    )

    assert result == []
