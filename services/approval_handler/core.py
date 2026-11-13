"""Core logic behind the email approval links (Approve/Reject).

Framework-agnostic (plain args in, a dict describing an HTTP response
out) so it's easy to unit test and reuse regardless of what actually
serves it - originally written for a Lambda, now served via a small
FastAPI app on ECS Fargate instead (the Lambda/API Gateway path hit an
organizational restriction on publicly-invocable Lambda endpoints -
see PROGRESS.md).

Regenerate isn't handled here - re-running the LLM/judge pipeline needs
the full app environment (A2A client, Claude), not something worth
cramming into this small, EFS-mounted-but-otherwise-minimal service.
That stays a later step, likely triggering an ECS one-off task instead.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import date
from typing import Any

from echoledger.approval_email import send_approved_post_email
from echoledger.approval_tokens import verify_token
from echoledger.config import LLM_MODEL
from echoledger.llm.post_title import generate_post_title
from echoledger.storage.db import get_diary_entry, get_news_summaries, set_diary_approved
from echoledger.utils.dates import years_later

_RESPONSE_HEADERS = {"Content-Type": "text/html"}


def _html_response(status_code: int, message: str) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": _RESPONSE_HEADERS,
        "body": f"<html><body><p>{message}</p></body></html>",
    }


def process_approval(
    date_str: str | None,
    action: str | None,
    token: str | None,
    signing_key: str | None,
    conn: sqlite3.Connection,
    generate_title_fn: Callable[..., str] = generate_post_title,
    send_approved_post_fn: Callable[..., None] = send_approved_post_email,
) -> dict[str, Any]:
    if not date_str or not action or not token:
        return _html_response(400, "Missing date, action, or signature.")

    if not signing_key or not verify_token(date_str, action, token, signing_key):
        return _html_response(403, "Invalid or tampered link.")

    try:
        on_date = date.fromisoformat(date_str)
    except ValueError:
        return _html_response(400, "Invalid date.")

    set_diary_approved(conn, on_date, approved=action == "approve")

    if action == "approve":
        _notify_approved_post(conn, on_date, generate_title_fn, send_approved_post_fn)

    verb = "approved" if action == "approve" else "rejected"
    return _html_response(200, f"Arthur's diary entry for {date_str} has been {verb}.")


def _notify_approved_post(
    conn: sqlite3.Connection,
    historical_date: date,
    generate_title_fn: Callable[..., str],
    send_approved_post_fn: Callable[..., None],
) -> None:
    """Best-effort: the approve click itself already succeeded (the DB flag
    is already flipped) by the time this runs, so a hiccup here (a flaky
    SES/Claude call) must not turn that into an error response for the
    person who just clicked the link - it's logged and swallowed instead."""
    entry = get_diary_entry(conn, historical_date)
    if entry is None:
        return

    modern_date = years_later(historical_date)
    summaries = get_news_summaries(conn, modern_date)
    try:
        title = generate_title_fn(
            conn, historical_date, modern_date, entry.entry_text, summaries, LLM_MODEL
        )
        send_approved_post_fn(historical_date, modern_date, entry.entry_text, summaries, title)
    except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
        print(f"  [approved-post email] failed to send for {historical_date}: {exc}")
