"""Signed tokens for the email-approval action links (Approve/Reject).

Tamper-proof without needing a database lookup, so the Lambda handler
can verify a click is genuine before touching anything - pure HMAC over
the date and action, no new dependency needed.
"""

from __future__ import annotations

import base64
import hashlib
import hmac

VALID_ACTIONS = ("approve", "reject")


def make_token(date_str: str, action: str, signing_key: str) -> str:
    message = f"{date_str}|{action}".encode()
    signature = hmac.new(signing_key.encode(), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(signature).decode().rstrip("=")


def verify_token(date_str: str, action: str, token: str, signing_key: str) -> bool:
    if action not in VALID_ACTIONS:
        return False
    expected = make_token(date_str, action, signing_key)
    return hmac.compare_digest(expected, token)
