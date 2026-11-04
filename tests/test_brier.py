from datetime import date, datetime

from echoledger.evals.brier import brier_score
from echoledger.models import Prediction, PredictionResolution


def _prediction(probability: float) -> Prediction:
    return Prediction(
        id="p",
        created_date=date(2026, 1, 1),
        resolution_date=date(2026, 2, 1),
        statement="x",
        probability=probability,
        forecaster="claude-haiku-4-5",
    )


def _resolution(outcome: str) -> PredictionResolution:
    return PredictionResolution(
        prediction_id="p",
        resolved_at=datetime(2026, 2, 1, 9, 0, 0),
        outcome=outcome,
        reasoning="r",
        resolver="claude-haiku-4-5",
    )


def test_brier_score_with_no_resolved_predictions_returns_none() -> None:
    assert brier_score([]) is None


def test_brier_score_excludes_unclear_outcomes() -> None:
    resolved = [(_prediction(0.9), _resolution("unclear"))]
    assert brier_score(resolved) is None


def test_brier_score_perfect_confidence_correct() -> None:
    resolved = [(_prediction(1.0), _resolution("true"))]
    assert brier_score(resolved) == 0.0


def test_brier_score_perfect_confidence_wrong() -> None:
    resolved = [(_prediction(1.0), _resolution("false"))]
    assert brier_score(resolved) == 1.0


def test_brier_score_averages_across_multiple_predictions() -> None:
    resolved = [
        (_prediction(1.0), _resolution("true")),
        (_prediction(0.0), _resolution("true")),
    ]
    assert brier_score(resolved) == 0.5
