"""Golden-set eval against the REAL Claude API - deliberately NOT part of
the normal fast test suite (no fake client here; this spends real money).

Marked `real_api` so the default `pytest` run (and the main CI workflow)
excludes it. A separate workflow (.github/workflows/eval.yml) runs
`pytest -m real_api` on a schedule + manual trigger, using a real
ANTHROPIC_API_KEY secret - the actual "eval gate in CI" from the roadmap.
"""

import sqlite3
from datetime import date

import pytest

from echoledger.evals.leakage_judge import judge_diary_entry
from echoledger.models import ArthurDiaryEntry
from echoledger.storage.db import connect

pytestmark = pytest.mark.real_api


@pytest.fixture
def conn() -> sqlite3.Connection:
    return connect(":memory:")


def test_real_judge_passes_a_clean_entry(conn: sqlite3.Connection) -> None:
    entry = ArthurDiaryEntry(
        date=date(1926, 10, 29),
        entry_text=(
            "A quiet day. The papers report Senator King's inquiry into "
            "campaign contributions continues in Arizona, though the outcome "
            "remains uncertain. I wonder how it will all settle in the end."
        ),
        source_article_ids=["a1"],
        model="claude-haiku-4-5",
    )

    judgment = judge_diary_entry(conn, entry, model="claude-haiku-4-5")

    assert judgment.verdict == "pass"


def test_real_judge_fails_a_deliberately_leaky_entry(conn: sqlite3.Connection) -> None:
    entry = ArthurDiaryEntry(
        date=date(1926, 10, 29),
        entry_text=(
            "I read today of troubles that, of course, pale next to the great "
            "stock market crash that will devastate the nation in 1929, or the "
            "second World War that will erupt in 1939."
        ),
        source_article_ids=["a1"],
        model="claude-haiku-4-5",
    )

    judgment = judge_diary_entry(conn, entry, model="claude-haiku-4-5")

    assert judgment.verdict == "fail"
    assert len(judgment.violations) > 0
