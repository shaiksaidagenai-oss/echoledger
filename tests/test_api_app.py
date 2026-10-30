import sqlite3
from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient

from echoledger.api.app import app, get_db
from echoledger.models import HistoricalArticle
from echoledger.storage.db import connect, save_historical_article


def _override_get_db() -> Iterator[sqlite3.Connection]:
    conn = connect(":memory:")
    save_historical_article(
        conn,
        HistoricalArticle(
            id="a1",
            date=date(1926, 10, 30),
            newspaper="Evening Star",
            page=1,
            headline="A headline",
            text="Article text",
        ),
    )
    yield conn
    conn.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_get_archive_returns_a_daily_view(client: TestClient) -> None:
    response = client.get("/archive/2026-10-30")

    assert response.status_code == 200
    body = response.json()
    assert body["date"] == "2026-10-30"
    assert body["historical_date"] == "1926-10-30"
    assert body["historical_newspaper"] == "Evening Star"


def test_get_archive_rejects_a_malformed_date(client: TestClient) -> None:
    response = client.get("/archive/not-a-date")

    assert response.status_code == 422


def test_get_today_returns_200(client: TestClient) -> None:
    response = client.get("/today")

    assert response.status_code == 200
    assert "date" in response.json()
