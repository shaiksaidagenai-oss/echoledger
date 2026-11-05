import sqlite3
from datetime import date
from types import SimpleNamespace

import pytest

from echoledger.agents.diary_workflow import run_diary_workflow
from echoledger.models import HistoricalArticle
from echoledger.storage.db import connect, get_diary_entry


class _FakeMessages:
    """Returns the next entry text in sequence each time `write` is
    called, like a real model would produce a different draft each
    regeneration. The judge step no longer goes through this client at
    all - it's a separate network call to the Verification agent, faked
    via `judge_fn` instead (see `_fake_judge` below)."""

    def __init__(self, entry_texts: list[str]) -> None:
        self._entry_texts = iter(entry_texts)

    def parse(self, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            parsed_output=SimpleNamespace(entry_text=next(self._entry_texts)),
            usage=SimpleNamespace(input_tokens=100, output_tokens=50),
        )


class _FakeClient:
    def __init__(self, entry_texts: list[str]) -> None:
        self.messages = _FakeMessages(entry_texts)


def _fake_judge(entry_text: str, historical_date: date) -> tuple[str, list[str]]:
    """Stands in for judge_via_a2a - the tests only care about the
    get_approval callback's decisions, not the judge's verdict, so this
    always reports a clean pass."""
    return "pass", []


@pytest.fixture
def conn() -> sqlite3.Connection:
    return connect(":memory:")


def _article() -> HistoricalArticle:
    return HistoricalArticle(
        id="a1",
        date=date(1926, 10, 29),
        newspaper="Evening Star",
        page=1,
        headline="A headline",
        text="Article text",
    )


def test_run_diary_workflow_approved_first_attempt(conn: sqlite3.Connection) -> None:
    fake_client = _FakeClient(["A clean entry."])

    def _approve(
        entry_text: str, verdict: str | None, violations: list[str], attempt: int, max_attempts: int
    ) -> str:
        return "approve"

    entry = run_diary_workflow(
        conn,
        date(1926, 10, 29),
        [_article()],
        model="claude-haiku-4-5",
        get_approval=_approve,
        client=fake_client,  # type: ignore[arg-type]
        judge_fn=_fake_judge,
    )

    assert entry.approved is True
    assert entry.entry_text == "A clean entry."
    assert get_diary_entry(conn, date(1926, 10, 29)).approved is True  # type: ignore[union-attr]


def test_run_diary_workflow_rejected_without_regenerating(conn: sqlite3.Connection) -> None:
    fake_client = _FakeClient(["A questionable entry."])

    def _reject(
        entry_text: str, verdict: str | None, violations: list[str], attempt: int, max_attempts: int
    ) -> str:
        return "reject"

    entry = run_diary_workflow(
        conn,
        date(1926, 10, 29),
        [_article()],
        model="claude-haiku-4-5",
        get_approval=_reject,
        client=fake_client,  # type: ignore[arg-type]
        judge_fn=_fake_judge,
    )

    assert entry.approved is False
    assert get_diary_entry(conn, date(1926, 10, 29)).approved is False  # type: ignore[union-attr]


def test_run_diary_workflow_regenerates_then_approves(conn: sqlite3.Connection) -> None:
    fake_client = _FakeClient(["First flawed draft.", "Second, better draft."])
    calls: list[int] = []

    def _regenerate_once_then_approve(
        entry_text: str, verdict: str | None, violations: list[str], attempt: int, max_attempts: int
    ) -> str:
        calls.append(attempt)
        return "regenerate" if attempt == 1 else "approve"

    entry = run_diary_workflow(
        conn,
        date(1926, 10, 29),
        [_article()],
        model="claude-haiku-4-5",
        get_approval=_regenerate_once_then_approve,
        client=fake_client,  # type: ignore[arg-type]
        judge_fn=_fake_judge,
    )

    assert calls == [1, 2]  # the approval callback was genuinely invoked twice
    assert entry.approved is True
    assert entry.entry_text == "Second, better draft."  # the final, regenerated text


def test_run_diary_workflow_stops_regenerating_at_max_attempts(conn: sqlite3.Connection) -> None:
    fake_client = _FakeClient(["Draft one.", "Draft two."])
    calls: list[int] = []

    def _always_try_to_regenerate(
        entry_text: str, verdict: str | None, violations: list[str], attempt: int, max_attempts: int
    ) -> str:
        calls.append(attempt)
        return "regenerate"

    entry = run_diary_workflow(
        conn,
        date(1926, 10, 29),
        [_article()],
        model="claude-haiku-4-5",
        get_approval=_always_try_to_regenerate,
        client=fake_client,  # type: ignore[arg-type]
        max_attempts=2,
        judge_fn=_fake_judge,
    )

    assert calls == [1, 2]  # stopped asking once max_attempts was reached
    assert entry.approved is False  # "regenerate" past the limit finalizes as rejected
