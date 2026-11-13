import sqlite3
from datetime import date

import pytest
from services.approval_handler.core import process_approval

from echoledger.approval_tokens import make_token
from echoledger.models import (
    ArthurDiaryEntry,
    EchoCandidate,
    NewsSummary,
    Prediction,
    TodayHeadline,
)
from echoledger.storage.db import (
    connect,
    get_diary_entry,
    save_diary_entry,
    save_echo_candidate,
    save_news_summary,
    save_prediction,
    save_today_headline,
)

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


def _noop_title_fn(*args: object, **kwargs: object) -> str:
    return "A Title"


def _noop_send_fn(*args: object, **kwargs: object) -> None:
    pass


def test_a_valid_approve_link_approves_the_entry(conn: sqlite3.Connection) -> None:
    on_date = date(1926, 11, 7)
    _seed_entry(conn, on_date)
    token = make_token("1926-11-07", "approve", SIGNING_KEY)

    result = process_approval(
        "1926-11-07",
        "approve",
        token,
        SIGNING_KEY,
        conn,
        generate_title_fn=_noop_title_fn,
        send_approved_post_fn=_noop_send_fn,
    )

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


def test_approving_sends_an_approved_post_notification(conn: sqlite3.Connection) -> None:
    on_date = date(1926, 11, 12)
    _seed_entry(conn, on_date)
    save_news_summary(
        conn,
        NewsSummary(
            headline_id="h1",
            date=date(2026, 11, 12),
            summary_text="Today's news.",
            model="claude-haiku-4-5",
        ),
    )
    token = make_token("1926-11-12", "approve", SIGNING_KEY)
    calls: list[dict[str, object]] = []

    def _title_fn(conn, historical_date, modern_date, entry_text, summaries, model):  # type: ignore[no-untyped-def]
        calls.append(
            {
                "historical_date": historical_date,
                "modern_date": modern_date,
                "entry_text": entry_text,
                "summaries": summaries,
            }
        )
        return "A Title"

    def _send_fn(  # type: ignore[no-untyped-def]
        historical_date, modern_date, entry_text, summaries, title, echo_then, echo_now, predictions
    ):
        calls.append({"title": title, "echo_then": echo_then, "predictions": predictions})

    result = process_approval(
        "1926-11-12",
        "approve",
        token,
        SIGNING_KEY,
        conn,
        generate_title_fn=_title_fn,
        send_approved_post_fn=_send_fn,
    )

    assert result["statusCode"] == 200
    assert len(calls) == 2
    assert calls[0]["historical_date"] == on_date
    assert calls[0]["modern_date"] == date(2026, 11, 12)
    assert calls[0]["entry_text"] == "A draft entry."
    assert len(calls[0]["summaries"]) == 1  # type: ignore[arg-type]
    assert calls[1]["title"] == "A Title"


def test_approving_includes_the_real_echo_match_and_predictions(conn: sqlite3.Connection) -> None:
    from datetime import datetime

    on_date = date(1926, 11, 12)
    _seed_entry(conn, on_date)
    save_today_headline(
        conn,
        TodayHeadline(
            id="h1",
            date=date(2026, 11, 12),
            source_name="NPR",
            headline="Real modern headline.",
            snippet="A snippet.",
            url="https://example.com/h1",
            fetched_at=datetime(2026, 11, 12, 9, 0, 0),
        ),
    )
    save_echo_candidate(
        conn,
        EchoCandidate(
            today_headline_id="h1",
            date=date(2026, 11, 12),
            historical_article_id="a1",
            historical_headline="Real historical headline.",
            historical_date=on_date,
            distance=1.1,
        ),
    )
    save_prediction(
        conn,
        Prediction(
            id="pred-1",
            created_date=date(2026, 11, 12),
            resolution_date=date(2027, 3, 31),
            statement="A ceasefire will be signed",
            probability=0.25,
            forecaster="claude-haiku-4-5",
        ),
    )
    token = make_token("1926-11-12", "approve", SIGNING_KEY)
    captured: dict[str, object] = {}

    def _send_fn(  # type: ignore[no-untyped-def]
        historical_date, modern_date, entry_text, summaries, title, echo_then, echo_now, predictions
    ):
        captured["echo_then"] = echo_then
        captured["echo_now"] = echo_now
        captured["predictions"] = predictions

    process_approval(
        "1926-11-12",
        "approve",
        token,
        SIGNING_KEY,
        conn,
        generate_title_fn=_noop_title_fn,
        send_approved_post_fn=_send_fn,
    )

    assert captured["echo_then"] == "Real historical headline."
    assert captured["echo_now"] == "Real modern headline."
    predictions = captured["predictions"]
    assert len(predictions) == 1  # type: ignore[arg-type]
    assert predictions[0].statement == "A ceasefire will be signed"  # type: ignore[index]


def test_rejecting_does_not_send_an_approved_post_notification(conn: sqlite3.Connection) -> None:
    on_date = date(1926, 11, 7)
    _seed_entry(conn, on_date)
    token = make_token("1926-11-07", "reject", SIGNING_KEY)
    calls: list[object] = []

    result = process_approval(
        "1926-11-07",
        "reject",
        token,
        SIGNING_KEY,
        conn,
        generate_title_fn=lambda *a, **k: calls.append("title") or "x",  # type: ignore[func-returns-value]
        send_approved_post_fn=lambda *a, **k: calls.append("send"),
    )

    assert result["statusCode"] == 200
    assert calls == []


def test_a_notification_failure_does_not_break_the_approve_response(
    conn: sqlite3.Connection,
) -> None:
    on_date = date(1926, 11, 7)
    _seed_entry(conn, on_date)
    token = make_token("1926-11-07", "approve", SIGNING_KEY)

    def _raising_title_fn(*args: object, **kwargs: object) -> str:
        raise RuntimeError("SES is down")

    result = process_approval(
        "1926-11-07",
        "approve",
        token,
        SIGNING_KEY,
        conn,
        generate_title_fn=_raising_title_fn,
        send_approved_post_fn=_noop_send_fn,
    )

    assert result["statusCode"] == 200
    entry = get_diary_entry(conn, on_date)
    assert entry is not None and entry.approved is True
