"""Read-only HTTP API: GET /today and GET /archive/{date}.

`get_db` is a FastAPI dependency so tests can swap in a test database via
`app.dependency_overrides[get_db]` instead of hitting the real DB_PATH file.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import date

from fastapi import Depends, FastAPI

from echoledger.api.schemas import DailyView
from echoledger.api.views import build_daily_view
from echoledger.config import DB_PATH
from echoledger.storage.db import connect
from echoledger.utils.dates import today as today_fn

app = FastAPI(
    title="EchoLedger",
    description="Then & Now - today's news beside the news from 100 years ago.",
)


def get_db() -> Iterator[sqlite3.Connection]:
    conn = connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


@app.get("/today", response_model=DailyView)
def get_today(conn: sqlite3.Connection = Depends(get_db)) -> DailyView:
    return build_daily_view(conn, today_fn())


@app.get("/archive/{on_date}", response_model=DailyView)
def get_archive(on_date: date, conn: sqlite3.Connection = Depends(get_db)) -> DailyView:
    return build_daily_view(conn, on_date)
