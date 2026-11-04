import sqlite3
from types import SimpleNamespace

import pytest

from echoledger.rag.embeddings import MAX_CHARS_PER_BATCH, embed_texts
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


class _TrackingEmbeddings:
    """Returns one vector per input text, and records each call's inputs -
    lets a test verify batching actually split a large input correctly."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def create(self, input: list[str], **kwargs: object) -> SimpleNamespace:
        self.calls.append(list(input))
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[float(len(t))]) for t in input],
            usage=SimpleNamespace(total_tokens=len(input)),
        )


class _TrackingClient:
    def __init__(self) -> None:
        self.embeddings = _TrackingEmbeddings()


def test_embed_texts_splits_a_large_input_into_multiple_batches(
    conn: sqlite3.Connection,
) -> None:
    fake_client = _TrackingClient()
    # Three texts, each over half the per-batch budget, so no two can share
    # a batch - this should force three separate API calls.
    big_text = "x" * (MAX_CHARS_PER_BATCH // 2 + 1)
    texts = [big_text, big_text, big_text]

    result = embed_texts(conn, texts, purpose="test", client=fake_client)  # type: ignore[arg-type]

    assert len(result) == 3
    assert len(fake_client.embeddings.calls) == 3
    for call in fake_client.embeddings.calls:
        assert len(call) == 1  # each big text got its own batch, as expected

    # Every batch call got logged separately.
    rows = conn.execute("SELECT * FROM llm_usage WHERE purpose = 'test'").fetchall()
    assert len(rows) == 3


def test_embed_texts_keeps_small_inputs_in_one_batch(conn: sqlite3.Connection) -> None:
    fake_client = _TrackingClient()
    texts = ["short one", "short two", "short three"]

    result = embed_texts(conn, texts, purpose="test", client=fake_client)  # type: ignore[arg-type]

    assert len(result) == 3
    assert len(fake_client.embeddings.calls) == 1  # all three fit comfortably in one call
