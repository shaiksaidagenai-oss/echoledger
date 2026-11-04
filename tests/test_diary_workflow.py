import sqlite3
from datetime import date
from types import SimpleNamespace

import pytest

from echoledger.agents.diary_workflow import run_diary_workflow
from echoledger.models import HistoricalArticle
from echoledger.storage.db import connect, get_diary_entry


class _FakeMessages:
    def __init__(self, entry_text: str, verdict: str, violations: list[str]) -> None:
        self._entry_response = SimpleNamespace(
            parsed_output=SimpleNamespace(entry_text=entry_text),
            usage=SimpleNamespace(input_tokens=100, output_tokens=50),
        )
        self._judge_response = SimpleNamespace(
            parsed_output=SimpleNamespace(verdict=verdict, violations=[]),
            usage=SimpleNamespace(input_tokens=100, output_tokens=50),
        )
        self._violations = violations

    def parse(self, **kwargs: object) -> SimpleNamespace:
        system = kwargs.get("system", "")
        assert isinstance(system, str)
        if "fact-checker" in system:
            return self._judge_response
        return self._entry_response


class _FakeClient:
    def __init__(
        self, entry_text: str, verdict: str = "pass", violations: list[str] | None = None
    ) -> None:
        self.messages = _FakeMessages(entry_text, verdict, violations or [])


@pytest.fixture
def conn() -> sqlite3.Connection:
    return connect(":memory:")


def _article() -> HistoricalArticle:
    return HistoricalArticle(
        id="a1", date=date(1926, 10, 29), newspaper="Evening Star", page=1,
        headline="A headline", text="Article text",
    )


def test_run_diary_workflow_approved(conn: sqlite3.Connection) -> None:
    fake_client = _FakeClient("A clean entry.")

    def _approve_everything(entry_text: str, verdict: str | None, violations: list[str]) -> bool:
        return True

    entry = run_diary_workflow(
        conn, date(1926, 10, 29), [_article()], model="claude-haiku-4-5",
        get_approval=_approve_everything, client=fake_client,  # type: ignore[arg-type]
    )

    assert entry.approved is True
    assert get_diary_entry(conn, date(1926, 10, 29)).approved is True  # type: ignore[union-attr]


def test_run_diary_workflow_rejected(conn: sqlite3.Connection) -> None:
    fake_client = _FakeClient("A questionable entry.")

    def _reject_everything(entry_text: str, verdict: str | None, violations: list[str]) -> bool:
        return False

    entry = run_diary_workflow(
        conn, date(1926, 10, 29), [_article()], model="claude-haiku-4-5",
        get_approval=_reject_everything, client=fake_client,  # type: ignore[arg-type]
    )

    assert entry.approved is False
    assert get_diary_entry(conn, date(1926, 10, 29)).approved is False  # type: ignore[union-attr]
