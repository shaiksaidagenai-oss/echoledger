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
from echoledger.models import NewsSummary, Prediction


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


def send_approved_post_email(
    historical_date: date,
    modern_date: date,
    entry_text: str,
    summaries: list[NewsSummary],
    title: str,
    echo_then: str | None,
    echo_now: str | None,
    predictions: list[Prediction],
    client: Any = None,
) -> None:
    """Sent once an entry is approved - a ready-to-copy LinkedIn post
    combining all of 'Then & Now' (Arthur's entry, today's real news, the
    best History Echo match if one exists, and today's predictions) for
    manual posting. Goes to a different recipient than the approval email
    itself (ECHOLEDGER_APPROVED_NOTIFY_EMAIL, not ECHOLEDGER_NOTIFY_EMAIL).

    Echo and predictions are each included only when real data exists for
    that date - never invented, matching every other section here."""
    sender = os.environ["ECHOLEDGER_NOTIFY_EMAIL"]
    recipient = os.environ["ECHOLEDGER_APPROVED_NOTIFY_EMAIL"]

    news_block = "\n".join(f"{i}. {s.summary_text}" for i, s in enumerate(summaries, 1)) or (
        "(no news summaries saved for this date)"
    )

    body_lines = [
        f"Article Title: {title}",
        "",
        f"\U0001f4f0 Then & Now | {modern_date.strftime('%d %B')} "
        f"— {historical_date.year} vs {modern_date.year}",
        "",
        "\U0001f4dc 100 YEARS AGO TODAY",
        f'Arthur, our AI citizen of {historical_date.year}, writes in his diary:',
        f'"{entry_text}"',
        "",
        "\U0001f30d TODAY'S NEWS",
        news_block,
    ]

    if echo_then and echo_now:
        body_lines += [
            "",
            "\U0001f517 ECHO OF THE DAY",
            f"{historical_date.year}: {echo_then}",
            f"{modern_date.year}: {echo_now}",
            "(found by embedding similarity, not written by hand)",
        ]

    if predictions:
        body_lines += ["", "\U0001f52e TODAY'S PREDICTION(S)"]
        for p in predictions:
            body_lines.append(
                f"{p.statement} by {p.resolution_date.isoformat()} — {p.probability:.0%} likely."
            )
        body_lines.append("Logged and locked. We'll report the result either way.")

    if client is None:
        client = get_client()

    client.send_email(
        Source=sender,
        Destination={"ToAddresses": [recipient]},
        Message={
            "Subject": {
                "Data": (
                    f"{modern_date.isoformat()} EchoLedger: Arthur's diary for "
                    f"{historical_date.isoformat()} approved for LinkedIn post"
                )
            },
            "Body": {"Text": {"Data": "\n".join(body_lines)}},
        },
    )
