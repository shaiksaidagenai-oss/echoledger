"""Sends the email containing Arthur's draft diary entry plus signed
Approve/Reject action links, via AWS SES.

Links point at the approval-handler service (services/approval_handler/)
over plain HTTP - no HTTPS needed, since the signed token secures the
action itself, not the transport (that requirement went away once the
approval channel became email instead of WhatsApp).
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any

import boto3

from echoledger.approval_tokens import make_token


def get_client() -> Any:
    """Reads AWS_REGION from the environment automatically (ECS injects it;
    config.py's Secrets Manager client relies on the same resolution)."""
    return boto3.client("ses")


def send_approval_email(
    historical_date: date,
    entry_text: str,
    verdict: str | None,
    violations: list[str],
    client: Any = None,
) -> None:
    base_url = os.environ["ECHOLEDGER_APPROVAL_BASE_URL"]
    signing_key = os.environ["APPROVAL_SIGNING_KEY"]
    recipient = os.environ["ECHOLEDGER_NOTIFY_EMAIL"]

    date_str = historical_date.isoformat()
    approve_url = (
        f"{base_url}/?date={date_str}&action=approve"
        f"&sig={make_token(date_str, 'approve', signing_key)}"
    )
    reject_url = (
        f"{base_url}/?date={date_str}&action=reject"
        f"&sig={make_token(date_str, 'reject', signing_key)}"
    )

    body_lines = [
        f"Arthur's diary entry for {date_str} is ready for review.",
        "",
        entry_text,
        "",
        f"Leakage judge verdict: {verdict}",
    ]
    if violations:
        body_lines.append("Violations flagged:")
        body_lines.extend(f"  - {v}" for v in violations)
    body_lines += ["", f"Approve: {approve_url}", "", f"Reject: {reject_url}"]

    if client is None:
        client = get_client()

    client.send_email(
        Source=recipient,
        Destination={"ToAddresses": [recipient]},
        Message={
            "Subject": {"Data": f"EchoLedger: Arthur's diary for {date_str} - approval needed"},
            "Body": {"Text": {"Data": "\n".join(body_lines)}},
        },
    )
