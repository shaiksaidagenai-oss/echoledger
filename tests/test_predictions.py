import sqlite3
from datetime import date, datetime
from types import SimpleNamespace

import pytest

from echoledger.llm.predictions import generate_predictions, resolve_predictions
from echoledger.models import Prediction, TodayHeadline
from echoledger.storage.db import (
    connect,
    get_predictions_created_on,
    get_resolution,
    save_prediction,
    save_today_headline,
)


class _FakeMessages:
    def __init__(
        self, parsed_output: object, input_tokens: int = 100, output_tokens: int = 50
    ) -> None:
        self._response = SimpleNamespace(
            parsed_output=parsed_output,
            usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
        )

    def parse(self, **kwargs: object) -> SimpleNamespace:
        return self._response


class _FakeClient:
    def __init__(self, parsed_output: object) -> None:
        self.messages = _FakeMessages(parsed_output)


@pytest.fixture
def conn() -> sqlite3.Connection:
    return connect(":memory:")


def _headline(headline_id: str = "h1") -> TodayHeadline:
    return TodayHeadline(
        id=headline_id,
        date=date(2026, 10, 30),
        source_name="BBC News",
        headline="A real headline",
        snippet="A real snippet.",
        url="https://example.com",
        fetched_at=datetime(2026, 10, 30, 9, 0, 0),
    )


def test_generate_predictions_saves_valid_ones(conn: sqlite3.Connection) -> None:
    fake_output = SimpleNamespace(
        predictions=[
            SimpleNamespace(
                statement="Will X happen?", probability=0.6, resolution_date="2026-12-01"
            )
        ]
    )
    fake_client = _FakeClient(fake_output)

    saved = generate_predictions(
        conn, date(2026, 10, 30), [_headline()], model="claude-haiku-4-5", client=fake_client  # type: ignore[arg-type]
    )

    assert len(saved) == 1
    assert saved[0].statement == "Will X happen?"
    assert get_predictions_created_on(conn, date(2026, 10, 30)) == saved


def test_generate_predictions_rejects_finance_topics(conn: sqlite3.Connection) -> None:
    fake_output = SimpleNamespace(
        predictions=[
            SimpleNamespace(
                statement="Will the stock market rally by December?",
                probability=0.5,
                resolution_date="2026-12-01",
            )
        ]
    )
    fake_client = _FakeClient(fake_output)

    saved = generate_predictions(
        conn, date(2026, 10, 30), [_headline()], model="claude-haiku-4-5", client=fake_client  # type: ignore[arg-type]
    )

    assert saved == []


def test_generate_predictions_rejects_out_of_range_resolution_date(
    conn: sqlite3.Connection,
) -> None:
    fake_output = SimpleNamespace(
        predictions=[
            # Only 1 day out - below MIN_RESOLUTION_DAYS_OUT.
            SimpleNamespace(
                statement="Will X happen tomorrow?", probability=0.5, resolution_date="2026-10-31"
            )
        ]
    )
    fake_client = _FakeClient(fake_output)

    saved = generate_predictions(
        conn, date(2026, 10, 30), [_headline()], model="claude-haiku-4-5", client=fake_client  # type: ignore[arg-type]
    )

    assert saved == []


def test_generate_predictions_with_no_headlines_makes_no_api_call(conn: sqlite3.Connection) -> None:
    saved = generate_predictions(
        conn, date(2026, 10, 30), [], model="claude-haiku-4-5", client=object()  # type: ignore[arg-type]
    )

    assert saved == []


def test_resolve_predictions_with_nothing_pending_returns_empty(conn: sqlite3.Connection) -> None:
    result = resolve_predictions(
        conn, date(2026, 10, 30), model="claude-haiku-4-5", client=object()  # type: ignore[arg-type]
    )

    assert result == []


def test_resolve_predictions_with_no_news_resolves_unclear_without_api_call(
    conn: sqlite3.Connection,
) -> None:
    save_prediction(
        conn,
        Prediction(
            id="pred-1",
            created_date=date(2026, 10, 1),
            resolution_date=date(2026, 10, 30),
            statement="Will X happen?",
            probability=0.5,
            forecaster="claude-haiku-4-5",
        ),
    )
    # client=object() has no .messages - if the code tried to call the API,
    # this would raise AttributeError, proving it genuinely skipped the call.
    result = resolve_predictions(
        conn, date(2026, 10, 30), model="claude-haiku-4-5", client=object()  # type: ignore[arg-type]
    )

    assert len(result) == 1
    assert result[0].outcome == "unclear"
    assert get_resolution(conn, "pred-1") == result[0]


def test_resolve_predictions_with_news_calls_the_model(conn: sqlite3.Connection) -> None:
    save_prediction(
        conn,
        Prediction(
            id="pred-1",
            created_date=date(2026, 10, 1),
            resolution_date=date(2026, 10, 30),
            statement="Will X happen?",
            probability=0.5,
            forecaster="claude-haiku-4-5",
        ),
    )
    save_today_headline(conn, _headline())

    fake_output = SimpleNamespace(outcome="true", reasoning="The news confirms it happened.")
    fake_client = _FakeClient(fake_output)

    result = resolve_predictions(
        conn, date(2026, 10, 30), model="claude-haiku-4-5", client=fake_client  # type: ignore[arg-type]
    )

    assert len(result) == 1
    assert result[0].outcome == "true"
    assert result[0].reasoning == "The news confirms it happened."
