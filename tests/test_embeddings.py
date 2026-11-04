import sqlite3
from types import SimpleNamespace

import pytest

from echoledger.rag.embeddings import embed_texts
from echoledger.storage.db import connect


class _FakeEmbeddings:
    def __init__(self, vectors: list[list[float]], total_tokens: int) -> None:
        self._response = SimpleNamespace(
            data=[SimpleNamespace(embedding=v) for v in vectors],
            usage=SimpleNamespace(total_tokens=total_tokens),
        )

    def create(self, **kwargs: object) -> SimpleNamespace:
        return self._response


class _FakeClient:
    def __init__(self, vectors: list[list[float]], total_tokens: int = 10) -> None:
        self.embeddings = _FakeEmbeddings(vectors, total_tokens)


@pytest.fixture
def conn() -> sqlite3.Connection:
    return connect(":memory:")


def test_embed_texts_returns_vectors_and_logs_usage(conn: sqlite3.Connection) -> None:
    fake_client = _FakeClient(vectors=[[0.1, 0.2], [0.3, 0.4]], total_tokens=42)

    result = embed_texts(conn, ["a", "b"], purpose="test_purpose", client=fake_client)  # type: ignore[arg-type]

    assert result == [[0.1, 0.2], [0.3, 0.4]]
    row = conn.execute("SELECT * FROM llm_usage").fetchone()
    assert row["purpose"] == "test_purpose"
    assert row["input_tokens"] == 42
    assert row["output_tokens"] == 0


def test_embed_texts_with_no_texts_makes_no_api_call(conn: sqlite3.Connection) -> None:
    result = embed_texts(conn, [], purpose="x", client=object())  # type: ignore[arg-type]

    assert result == []
