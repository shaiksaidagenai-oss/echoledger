import sqlite3
from datetime import date
from types import SimpleNamespace

import pytest

from echoledger.evals.leakage_judge import judge_diary_entry
from echoledger.models import ArthurDiaryEntry
from echoledger.storage.db import connect, get_leakage_judgment


class _FakeMessages:
    def __init__(
        self, parsed_output: object, input_tokens: int = 100, output_tokens: int = 50
    ) -> None:
        self._response = SimpleNamespace(
            parsed_output=parsed_output,
            usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
        )

    def parse(self, **kwargs: object) -> SimpleNamespace:
        return self._response


class _FakeClient:
    def __init__(self, parsed_output: object) -> None:
        self.messages = _FakeMessages(parsed_output)


@pytest.fixture
def conn() -> sqlite3.Connection:
    return connect(":memory:")


def _entry(text: str) -> ArthurDiaryEntry:
    return ArthurDiaryEntry(
        date=date(1926, 10, 29),
        entry_text=text,
        source_article_ids=["a1"],
        model="claude-haiku-4-5",
    )


def test_judge_diary_entry_pass_case(conn: sqlite3.Connection) -> None:
    fake_output = SimpleNamespace(verdict="pass", violations=[])
    fake_client = _FakeClient(fake_output)

    judgment = judge_diary_entry(
        conn,
        _entry("A perfectly period-appropriate entry."),
        model="claude-haiku-4-5",
        client=fake_client,  # type: ignore[arg-type]
    )

    assert judgment.verdict == "pass"
    assert judgment.violations == []
    assert get_leakage_judgment(conn, date(1926, 10, 29)) == judgment


def test_judge_diary_entry_fail_case_with_violations(conn: sqlite3.Connection) -> None:
    fake_output = SimpleNamespace(
        verdict="fail",
        violations=[
            SimpleNamespace(
                quote="television would soon change everything",
                explanation="Television wasn't invented/known in 1926.",
            )
        ],
    )
    fake_client = _FakeClient(fake_output)

    judgment = judge_diary_entry(
        conn, _entry("I mused that television would soon change everything."),
        model="claude-haiku-4-5", client=fake_client,  # type: ignore[arg-type]
    )

    assert judgment.verdict == "fail"
    assert len(judgment.violations) == 1
    assert "television" in judgment.violations[0]
    assert get_leakage_judgment(conn, date(1926, 10, 29)) == judgment


def test_judge_diary_entry_logs_usage(conn: sqlite3.Connection) -> None:
    fake_output = SimpleNamespace(verdict="pass", violations=[])
    fake_client = _FakeClient(fake_output)

    judge_diary_entry(
        conn, _entry("Entry text."), model="claude-haiku-4-5", client=fake_client  # type: ignore[arg-type]
    )

    row = conn.execute("SELECT * FROM llm_usage WHERE purpose = 'judge_leakage'").fetchone()
    assert row is not None
