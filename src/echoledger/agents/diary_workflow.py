"""Arthur's diary workflow, expressed as a real LangGraph graph instead of
plain sequential Python - the first use of LangGraph in this project.

Approval happens SYNCHRONOUSLY within one call to run_diary_workflow()
(the caller is already present to answer) rather than across separate
process invocations - this avoids needing a persistent checkpointer,
while still genuinely using interrupt()/Command(resume=...), LangGraph's
real mechanism for pausing a graph until a human responds.

Graph state holds only plain JSON-safe primitives (str/list/bool), never
a Pydantic object - found the hard way (a real run, see PROGRESS.md) that
LangGraph's checkpointer serializes state internally even with
InMemorySaver, and doesn't know how to deserialize arbitrary custom
types. The real ArthurDiaryEntry is only ever constructed outside the
graph, from these primitives, once the workflow finishes.

`get_approval` is injected (same dependency-injection pattern used
everywhere else in this project for the real API clients) so tests can
pass a canned function instead of a real terminal prompt.
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

from echoledger.evals.leakage_judge import judge_diary_entry
from echoledger.llm.arthur import write_diary_entry
from echoledger.models import ArthurDiaryEntry, HistoricalArticle
from echoledger.storage.db import set_diary_approved


class _DiaryWorkflowState(TypedDict):
    entry_text: str | None
    source_article_ids: list[str]
    verdict: str | None
    violations: list[str]
    approved: bool


def run_diary_workflow(
    conn: sqlite3.Connection,
    historical_date: date,
    articles: list[HistoricalArticle],
    model: str,
    get_approval: Callable[[str, str, list[str]], bool],
    client: anthropic.Anthropic | None = None,
) -> ArthurDiaryEntry:
    """Writes a diary entry, judges it, pauses for approval via
    `get_approval(entry_text, verdict, violations)`, then records the
    decision. Returns the final entry with `approved` set correctly."""

    def write_node(state: _DiaryWorkflowState) -> dict[str, object]:
        entry = write_diary_entry(conn, historical_date, articles, model, client=client)
        return {"entry_text": entry.entry_text, "source_article_ids": entry.source_article_ids}

    def judge_node(state: _DiaryWorkflowState) -> dict[str, object]:
        assert state["entry_text"] is not None
        # judge_diary_entry needs an ArthurDiaryEntry - built fresh here from
        # plain state, never stored back into the graph's own state.
        draft = ArthurDiaryEntry(
            date=historical_date,
            entry_text=state["entry_text"],
            source_article_ids=state["source_article_ids"],
            model=model,
        )
        judgment = judge_diary_entry(conn, draft, model=model, client=client)
        return {"verdict": judgment.verdict, "violations": judgment.violations}

    def approval_node(state: _DiaryWorkflowState) -> dict[str, object]:
        decision = interrupt(
            {
                "entry_text": state["entry_text"],
                "verdict": state["verdict"],
                "violations": state["violations"],
            }
        )
        return {"approved": bool(decision)}

    def finalize_node(state: _DiaryWorkflowState) -> dict[str, object]:
        set_diary_approved(conn, historical_date, state["approved"])
        return {}

    builder = StateGraph(_DiaryWorkflowState)
    builder.add_node("write", write_node)
    builder.add_node("judge", judge_node)
    builder.add_node("approval", approval_node)
    builder.add_node("finalize", finalize_node)
    builder.add_edge(START, "write")
    builder.add_edge("write", "judge")
    builder.add_edge("judge", "approval")
    builder.add_edge("approval", "finalize")
    graph = builder.compile(checkpointer=InMemorySaver())

    config = {"configurable": {"thread_id": f"diary-{historical_date.isoformat()}"}}
    initial_state: _DiaryWorkflowState = {
        "entry_text": None,
        "source_article_ids": [],
        "verdict": None,
        "violations": [],
        "approved": False,
    }
    # Verified working at runtime (2026-11-04, see test_diary_workflow.py):
    # mypy's overload resolution for a plain config dict is stricter than
    # what the real API accepts - same category of issue as Chroma's stubs.
    result = graph.invoke(initial_state, config)  # type: ignore[call-overload]

    if "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        decision = get_approval(payload["entry_text"], payload["verdict"], payload["violations"])
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
