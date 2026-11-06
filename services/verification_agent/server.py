"""The Verification agent: a standalone A2A server exposing Arthur's
leakage judge as a remote skill, pulled out of the main process so the
orchestrator (agents/diary_workflow.py) calls it over the network instead
of in-process - per the roadmap's "Verification agent runs as an
independent service, reached via A2A" requirement.

Lives outside src/echoledger/ on purpose (see CLAUDE.md's planned repo
structure) - this is conceptually a separate, independently-runnable
service, even though it imports and reuses the same judge_diary_entry()
logic rather than duplicating it.

A2A's "text/plain" mode just means the message payload is a string -
nothing stops that string from being a small JSON blob we parse
ourselves, which is simpler than inventing a natural-language protocol
for passing a date + article text back and forth.

Run with: python -m services.verification_agent.server
"""

from __future__ import annotations

import json
from datetime import date

import uvicorn
from a2a.helpers import new_task_from_user_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, Part
from fastapi import FastAPI

from echoledger.config import DB_PATH, LLM_MODEL
from echoledger.evals.leakage_judge import judge_diary_entry
from echoledger.models import ArthurDiaryEntry
from echoledger.storage.db import connect

HOST = "0.0.0.0"  # deliberate - needs to be reachable from outside the container
PORT = 9998


class LeakageJudgeExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        assert context.task_id is not None
        assert context.context_id is not None
        assert context.message is not None
        # A2A requires a Task to exist in the queue before any status-update
        # event references it (found via a real run - see PROGRESS.md).
        task = new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.start_work()

        payload = json.loads(context.get_user_input())
        draft = ArthurDiaryEntry(
            date=date.fromisoformat(payload["historical_date"]),
            entry_text=payload["entry_text"],
            source_article_ids=[],
            model=LLM_MODEL,
        )

        conn = connect(DB_PATH)
        judgment = judge_diary_entry(conn, draft, model=LLM_MODEL)
        conn.close()

        response_text = json.dumps({"verdict": judgment.verdict, "violations": judgment.violations})
        # A non-streaming response comes back as a Task, and
        # get_stream_response_text() only reads a Task's artifacts (not its
        # completion message) - found via a real run, see PROGRESS.md.
        await updater.add_artifact([Part(text=response_text)])
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        pass  # A single leakage check completes immediately - nothing to cancel.


def build_app() -> FastAPI:
    skill = AgentSkill(
        id="judge_leakage",
        name="Judge Diary Leakage",
        description=(
            "Reviews a diary entry for anachronisms - knowledge of events after "
            "its stated historical date. Input: JSON {historical_date, entry_text}. "
            "Output: JSON {verdict, violations}."
        ),
        input_modes=["text/plain"],
        output_modes=["text/plain"],
        tags=["echoledger", "leakage-verification"],
    )

    agent_card = AgentCard(
        name="EchoLedger Verification Agent",
        description="Checks Arthur's diary entries for leaked future knowledge.",
        version="0.1.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=False),
        supported_interfaces=[
            AgentInterface(
                protocol_binding="JSONRPC",
                url=f"http://{HOST}:{PORT}",
                protocol_version="1.0",
            )
        ],
        skills=[skill],
    )

    request_handler = DefaultRequestHandler(
        agent_executor=LeakageJudgeExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=agent_card,
    )

    app = FastAPI(title="EchoLedger Verification Agent")
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(agent_card),
        jsonrpc_routes=create_jsonrpc_routes(request_handler, "/"),
    )
    return app


app = build_app()

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
