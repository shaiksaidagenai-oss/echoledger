"""A2A client for the Verification agent (services/verification_agent) -
lets the main workflow check a diary entry for leakage over the network
instead of calling judge_diary_entry() in-process.

The rest of this codebase is synchronous (plain function calls, no
asyncio) - the A2A SDK's client is async, so this module hides that
behind a plain sync function via asyncio.run(), keeping the async-ness
an internal implementation detail rather than spreading it everywhere.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date

import a2a.client as a2a_client
import a2a.helpers as a2a_helpers
import a2a.types as a2a_types
import httpx

DEFAULT_AGENT_URL = "http://127.0.0.1:9998"


async def _judge_via_a2a_async(
    entry_text: str, historical_date: date, agent_url: str
) -> tuple[str, list[str]]:
    payload = json.dumps(
        {"historical_date": historical_date.isoformat(), "entry_text": entry_text}
    )

    try:
        client = await a2a_client.create_client(agent_url)
        # new_text_message defaults to role=ROLE_AGENT - the server's
        # new_task_from_user_message() rejects anything but ROLE_USER
        # (found via a real run - see PROGRESS.md).
        message = a2a_helpers.new_text_message(payload, role=a2a_types.Role.ROLE_USER)
        request = a2a_types.SendMessageRequest(message=message)

        response_text = ""
        async for response in client.send_message(request):
            response_text = a2a_helpers.get_stream_response_text(response)
    except httpx.ConnectError as exc:
        raise ConnectionError(
            f"Could not reach the Verification agent at {agent_url} - is it running? "
            "Start it with: python -m services.verification_agent.server"
        ) from exc

    result = json.loads(response_text)
    return result["verdict"], result["violations"]


def judge_via_a2a(
    entry_text: str, historical_date: date, agent_url: str = DEFAULT_AGENT_URL
) -> tuple[str, list[str]]:
    """Returns (verdict, violations) by calling the remote Verification
    agent instead of judge_diary_entry() in-process. The server persists
    its own LeakageJudgment row - this function only needs the result."""
    return asyncio.run(_judge_via_a2a_async(entry_text, historical_date, agent_url))
