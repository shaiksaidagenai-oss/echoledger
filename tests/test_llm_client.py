import sqlite3

import pytest

from echoledger.llm.client import estimate_cost_usd, record_usage
from echoledger.storage.db import connect


def test_estimate_cost_usd_known_model() -> None:
    cost = estimate_cost_usd("claude-haiku-4-5", input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == pytest.approx(1.00 + 5.00)


def test_estimate_cost_usd_unknown_model_raises() -> None:
    with pytest.raises(ValueError):
        estimate_cost_usd("not-a-real-model", input_tokens=100, output_tokens=100)


@pytest.fixture
def conn() -> sqlite3.Connection:
    return connect(":memory:")


def test_record_usage_logs_and_returns_cost(conn: sqlite3.Connection) -> None:
    cost = record_usage(
        conn,
        purpose="arthur_diary",
        model="claude-haiku-4-5",
        input_tokens=500,
        output_tokens=200,
    )

    assert cost > 0
    row = conn.execute("SELECT * FROM llm_usage").fetchone()
    assert row["estimated_cost_usd"] == pytest.approx(cost)
