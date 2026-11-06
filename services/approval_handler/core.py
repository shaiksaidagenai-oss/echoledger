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
from datetime import date
from typing import Any

from echoledger.approval_tokens import verify_token
from echoledger.storage.db import set_diary_approved

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

    verb = "approved" if action == "approve" else "rejected"
    return _html_response(200, f"Arthur's diary entry for {date_str} has been {verb}.")
