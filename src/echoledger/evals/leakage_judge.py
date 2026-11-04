"""Automated leakage judge: a SEPARATE Claude call that reviews a completed
ArthurDiaryEntry for anachronisms, rather than just trusting the generation
prompt (Phase 2's approach).

Important distinction from Arthur's own generation: the judge is SUPPOSED
to use its full knowledge of history - that's exactly how it recognizes a
violation. Arthur must pretend not to know the future; the judge must know
it, to check Arthur's work against it.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Literal

import anthropic
from pydantic import BaseModel

from echoledger.llm.client import get_client, record_usage
from echoledger.models import ArthurDiaryEntry, LeakageJudgment
from echoledger.storage.db import save_leakage_judgment

JUDGE_SYSTEM_PROMPT = """\
You are a strict fact-checker reviewing a diary entry supposedly written
by someone living on {historical_date}, based only on that day's real
newspaper.

Using your full knowledge of history, find any statement in the entry
that reveals knowledge of events, facts, or outcomes that happened AFTER
{historical_date} - something the real diary-writer could not yet know.

Violations include: stating the outcome of an event that was still
ongoing/uncertain on {historical_date}, referencing inventions or
technology that didn't exist yet, naming later years as if already
past, or foreshadowing a death/war/discovery that hadn't happened yet.

NOT violations: hopes, worries, or open-ended speculation about
currently-unfolding events ("I wonder if...", "time will tell",
"the prognosis sounds grim") - these are honest uncertainty, not
revealed future knowledge, even if you yourself know how it turned out.

List every real violation as a short quote plus a one-sentence
explanation. If you find none, return an empty list and verdict "pass"."""


class _Violation(BaseModel):
    quote: str
    explanation: str


class _JudgmentOutput(BaseModel):
    verdict: Literal["pass", "fail"]
    violations: list[_Violation]


def judge_diary_entry(
    conn: sqlite3.Connection,
    entry: ArthurDiaryEntry,
    model: str,
    client: anthropic.Anthropic | None = None,
) -> LeakageJudgment:
    if client is None:
        client = get_client()

    response = client.messages.parse(
        model=model,
        max_tokens=1024,
        system=JUDGE_SYSTEM_PROMPT.format(historical_date=entry.date.isoformat()),
        messages=[{"role": "user", "content": entry.entry_text}],
        output_format=_JudgmentOutput,
    )

    record_usage(
        conn,
        purpose="judge_leakage",
        model=model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )

    if response.parsed_output is None:
        raise ValueError("Claude's response didn't match the expected output schema.")

    judgment = LeakageJudgment(
        historical_date=entry.date,
        verdict=response.parsed_output.verdict,
        violations=[
            f"{v.quote} -- {v.explanation}" for v in response.parsed_output.violations
        ],
        model=model,
        judged_at=datetime.now(),
    )
    save_leakage_judgment(conn, judgment)
    return judgment
