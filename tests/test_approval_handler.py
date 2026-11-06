import sqlite3
from datetime import date

import pytest
from services.approval_handler.core import process_approval

from echoledger.approval_tokens import make_token
from echoledger.models import ArthurDiaryEntry
from echoledger.storage.db import connect, get_diary_entry, save_diary_entry

SIGNING_KEY = "test-signing-key"


@pytest.fixture
def conn() -> sqlite3.Connection:
    return connect(":memory:")


def _seed_entry(conn: sqlite3.Connection, on_date: date) -> None:
    save_diary_entry(
        conn,
        ArthurDiaryEntry(
            date=on_date,
            entry_text="A draft entry.",
            source_article_ids=[],
            model="claude-haiku-4-5",
            approved=False,
        ),
    )


def test_a_valid_approve_link_approves_the_entry(conn: sqlite3.Connection) -> None:
    on_date = date(1926, 11, 7)
    _seed_entry(conn, on_date)
    token = make_token("1926-11-07", "approve", SIGNING_KEY)

    result = process_approval("1926-11-07", "approve", token, SIGNING_KEY, conn)

    assert result["statusCode"] == 200
    entry = get_diary_entry(conn, on_date)
    assert entry is not None and entry.approved is True


def test_a_valid_reject_link_rejects_the_entry(conn: sqlite3.Connection) -> None:
    on_date = date(1926, 11, 7)
    _seed_entry(conn, on_date)
    token = make_token("1926-11-07", "reject", SIGNING_KEY)

    result = process_approval("1926-11-07", "reject", token, SIGNING_KEY, conn)

    assert result["statusCode"] == 200
    entry = get_diary_entry(conn, on_date)
    assert entry is not None and entry.approved is False


def test_a_tampered_signature_is_rejected_and_changes_nothing(conn: sqlite3.Connection) -> None:
    on_date = date(1926, 11, 7)
    _seed_entry(conn, on_date)

    result = process_approval("1926-11-07", "approve", "not-a-real-token", SIGNING_KEY, conn)

    assert result["statusCode"] == 403
    entry = get_diary_entry(conn, on_date)
    assert entry is not None and entry.approved is False


def test_missing_params_are_rejected(conn: sqlite3.Connection) -> None:
    result = process_approval(None, "approve", "sometoken", SIGNING_KEY, conn)

    assert result["statusCode"] == 400


def test_missing_signing_key_is_rejected(conn: sqlite3.Connection) -> None:
    token = make_token("1926-11-07", "approve", SIGNING_KEY)

    result = process_approval("1926-11-07", "approve", token, None, conn)

    assert result["statusCode"] == 403
