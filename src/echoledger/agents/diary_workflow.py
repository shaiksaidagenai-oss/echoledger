"""Arthur's diary workflow, expressed as a real LangGraph graph instead of
plain sequential Python - the first use of LangGraph in this project.

Approval happens SYNCHRONOUSLY within one call to run_diary_workflow()
(the caller is already present to answer) rather than across separate
process invocations - this avoids needing a persistent checkpointer,
while still genuinely using interrupt()/Command(resume=...), LangGraph's
real mechanism for pausing a graph until a human responds.

A rejection doesn't have to be final: the reviewer can ask for a fresh
draft instead (up to `max_attempts`), using add_conditional_edges() to
loop back to "write" - this matters because the diary entry is the
highest-leakage-risk content in the project, so "reject or accept a
flawed entry" was too narrow a choice.

Graph state holds only plain JSON-safe primitives (str/list/bool/int),
never a Pydantic object - found the hard way (a real run, see
PROGRESS.md) that LangGraph's checkpointer serializes state internally
even with InMemorySaver, and doesn't know how to deserialize arbitrary
custom types. The real ArthurDiaryEntry is only ever constructed outside
the graph, from these primitives, once the workflow finishes.

`get_approval` and `judge_fn` are both injected (same dependency-injection
pattern used everywhere else in this project for the real API clients) so
tests can pass canned functions instead of a real terminal prompt or a
real network call to the Verification agent.

The judge step now calls the Verification agent OVER THE NETWORK
(judge_via_a2a) instead of judge_diary_entry() in-process - pulling it
out into services/verification_agent as its own independent service,
reached via A2A, per the roadmap. That server process persists its own
LeakageJudgment row; this module no longer needs a DB connection or an
Anthropic client for the judge step at all.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import date
from typing import TypedDict

import anthropic
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, StateGraph
from langgraph.types import Command, interrupt

from echoledger.agents.verification_client import judge_via_a2a
from echoledger.llm.arthur import write_diary_entry
from echoledger.models import ArthurDiaryEntry, HistoricalArticle
from echoledger.storage.db import set_diary_approved

DEFAULT_MAX_ATTEMPTS = 3


class _DiaryWorkflowState(TypedDict):
    entry_text: str | None
    source_article_ids: list[str]
    verdict: str | None
    violations: list[str]
    decision: str | None  # "approve" | "reject" | "regenerate"
    approved: bool
    attempts: int


def run_diary_workflow(
    conn: sqlite3.Connection,
    historical_date: date,
    articles: list[HistoricalArticle],
    model: str,
    get_approval: Callable[[str, str, list[str], int, int], str],
    client: anthropic.Anthropic | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    judge_fn: Callable[[str, date], tuple[str, list[str]]] = judge_via_a2a,
) -> ArthurDiaryEntry:
    """Writes a diary entry, judges it (via the remote Verification
    agent), pauses for approval via
    `get_approval(entry_text, verdict, violations, attempt, max_attempts)`
    (must return "approve"/"reject"/"regenerate"). A "regenerate" decision
    loops back to a fresh draft, up to `max_attempts` total attempts.
    Returns the final entry with `approved` set correctly."""

    def write_node(state: _DiaryWorkflowState) -> dict[str, object]:
        entry = write_diary_entry(conn, historical_date, articles, model, client=client)
        return {
            "entry_text": entry.entry_text,
            "source_article_ids": entry.source_article_ids,
            "attempts": state["attempts"] + 1,
        }

    def judge_node(state: _DiaryWorkflowState) -> dict[str, object]:
        assert state["entry_text"] is not None
        verdict, violations = judge_fn(state["entry_text"], historical_date)
        return {"verdict": verdict, "violations": violations}

    def approval_node(state: _DiaryWorkflowState) -> dict[str, object]:
        decision = interrupt(
            {
                "entry_text": state["entry_text"],
                "verdict": state["verdict"],
                "violations": state["violations"],
                "attempt": state["attempts"],
                "max_attempts": max_attempts,
            }
        )
        return {"decision": decision}

    def route_after_approval(state: _DiaryWorkflowState) -> str:
        if state["decision"] == "regenerate" and state["attempts"] < max_attempts:
            return "write"
        return "finalize"

    def finalize_node(state: _DiaryWorkflowState) -> dict[str, object]:
        approved = state["decision"] == "approve"
        set_diary_approved(conn, historical_date, approved)
        return {"approved": approved}

    builder = StateGraph(_DiaryWorkflowState)
    builder.add_node("write", write_node)
    builder.add_node("judge", judge_node)
    builder.add_node("approval", approval_node)
    builder.add_node("finalize", finalize_node)
    builder.add_edge(START, "write")
    builder.add_edge("write", "judge")
    builder.add_edge("judge", "approval")
    builder.add_conditional_edges(
        "approval", route_after_approval, {"write": "write", "finalize": "finalize"}
    )
    graph = builder.compile(checkpointer=InMemorySaver())

    config = {"configurable": {"thread_id": f"diary-{historical_date.isoformat()}"}}
    initial_state: _DiaryWorkflowState = {
        "entry_text": None,
        "source_article_ids": [],
        "verdict": None,
        "violations": [],
        "decision": None,
        "approved": False,
        "attempts": 0,
    }
    # Verified working at runtime (2026-11-04, see test_diary_workflow.py):
    # mypy's overload resolution for a plain config dict is stricter than
    # what the real API accepts - same category of issue as Chroma's stubs.
    result = graph.invoke(initial_state, config)  # type: ignore[call-overload]

    # A "regenerate" decision loops back and hits another interrupt, so this
    # has to keep resuming until the graph genuinely finishes, not just once.
    while "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        decision = get_approval(
            payload["entry_text"],
            payload["verdict"],
            payload["violations"],
            payload["attempt"],
            payload["max_attempts"],
        )
        result = graph.invoke(Command(resume=decision), config)  # type: ignore[call-overload]

    entry_text = result["entry_text"]
    assert isinstance(entry_text, str)
    return ArthurDiaryEntry(
        date=historical_date,
        entry_text=entry_text,
        source_article_ids=result["source_article_ids"],
        model=model,
        approved=result["approved"],
    )
