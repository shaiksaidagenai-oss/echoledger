import sqlite3
from datetime import date
from types import SimpleNamespace

import pytest

from echoledger.llm.post_title import generate_post_title
from echoledger.models import NewsSummary
from echoledger.storage.db import connect


class _FakeMessages:
    def __init__(self, title: str, input_tokens: int, output_tokens: int) -> None:
        self._response = SimpleNamespace(
            parsed_output=SimpleNamespace(title=title),
            usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
        )

    def parse(self, **kwargs: object) -> SimpleNamespace:
        return self._response


class _FakeClient:
    def __init__(self, title: str, input_tokens: int = 200, output_tokens: int = 20) -> None:
        self.messages = _FakeMessages(title, input_tokens, output_tokens)


@pytest.fixture
def conn() -> sqlite3.Connection:
    return connect(":memory:")


def _summary(headline_id: str = "h1", text: str = "Something happened today.") -> NewsSummary:
    return NewsSummary(
        headline_id=headline_id,
        date=date(2026, 11, 12),
        summary_text=text,
        model="claude-haiku-4-5",
    )


def test_generate_post_title_returns_the_parsed_title(conn: sqlite3.Connection) -> None:
    fake_client = _FakeClient(title="Then & Now: A Catchy Title")

    title = generate_post_title(
        conn,
        date(1926, 11, 12),
        date(2026, 11, 12),
        "A diary entry.",
        [_summary()],
        model="claude-haiku-4-5",
        client=fake_client,  # type: ignore[arg-type]
    )

    assert title == "Then & Now: A Catchy Title"


def test_generate_post_title_logs_usage(conn: sqlite3.Connection) -> None:
    fake_client = _FakeClient(title="A Title", input_tokens=345, output_tokens=12)

    generate_post_title(
        conn,
        date(1926, 11, 12),
        date(2026, 11, 12),
        "A diary entry.",
        [],
        model="claude-haiku-4-5",
        client=fake_client,  # type: ignore[arg-type]
    )

    row = conn.execute("SELECT * FROM llm_usage").fetchone()
    assert row["purpose"] == "post_title"
    assert row["input_tokens"] == 345
    assert row["output_tokens"] == 12


def test_generate_post_title_raises_if_output_unparsed(conn: sqlite3.Connection) -> None:
    class _EmptyMessages:
        def parse(self, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(
                parsed_output=None, usage=SimpleNamespace(input_tokens=1, output_tokens=1)
            )

    fake_client = SimpleNamespace(messages=_EmptyMessages())

    with pytest.raises(ValueError):
        generate_post_title(
            conn,
            date(1926, 11, 12),
            date(2026, 11, 12),
            "A diary entry.",
            [],
            model="claude-haiku-4-5",
            client=fake_client,  # type: ignore[arg-type]
        )
