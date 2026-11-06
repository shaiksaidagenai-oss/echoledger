"""Small FastAPI service behind the email approval links (Approve/Reject).

Runs on ECS Fargate with a public IP, same pattern as the main app and
the Verification agent - not Lambda, after Lambda/API Gateway's public
invocation turned out to be blocked by an organizational restriction
(see core.py's docstring and PROGRESS.md for the full story).
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Response

from echoledger.config import DB_PATH
from echoledger.storage.db import connect
from services.approval_handler.core import process_approval

app = FastAPI(title="EchoLedger Approval Handler")


@app.get("/")
def approve_or_reject(date: str, action: str, sig: str) -> Response:
    conn = connect(DB_PATH)
    try:
        result = process_approval(date, action, sig, os.environ.get("APPROVAL_SIGNING_KEY"), conn)
    finally:
        conn.close()
    return Response(
        content=result["body"], status_code=result["statusCode"], media_type="text/html"
    )
