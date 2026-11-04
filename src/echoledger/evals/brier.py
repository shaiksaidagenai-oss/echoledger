"""Brier score: how well-calibrated our predictions are.

Lower is better - 0.0 is perfect, 0.25 is what pure 50/50 guessing scores
on average, 1.0 is confidently and completely wrong every time.

"unclear" resolutions are honestly excluded, not scored as a miss - we
have no evidence either way for those, so scoring them would fabricate
a result instead of reporting an honest "don't know."
"""

from __future__ import annotations

from echoledger.models import Prediction, PredictionResolution


def brier_score(resolved: list[tuple[Prediction, PredictionResolution]]) -> float | None:
    """Returns None if there are no true/false-resolved predictions yet -
    that's a real state (too early to score), not a zero."""
    outcomes = [
        (prediction.probability, 1.0 if resolution.outcome == "true" else 0.0)
        for prediction, resolution in resolved
        if resolution.outcome in ("true", "false")
    ]
    if not outcomes:
        return None
    return sum((probability - outcome) ** 2 for probability, outcome in outcomes) / len(outcomes)
