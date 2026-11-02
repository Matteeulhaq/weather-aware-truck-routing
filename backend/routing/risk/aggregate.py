"""Per-route risk aggregation and the recommendation cascade.

Recommendation priority (from the assessment, applied strictly in order):
1. Fewest Severe miles
2. Fewest High miles
3. Lowest average risk
4. Shortest travel time

Miles attribution: checkpoint *i* covers the road from its own position to
checkpoint *i+1* (the final checkpoint covers nothing). With a uniform
sampling interval this equals "count x interval" for interior bands and
handles the final partial segment correctly.

Average risk labels use monotonic banding on the mean score rather than
rounding (round-half-even made 2.5 -> "High" but 3.5 -> "No Travel"):
<0.5 Low | <1.5 Moderate | <2.5 High | <3.5 Severe | otherwise No Travel.
"""

import statistics
from dataclasses import dataclass, field

from .classify import CheckpointRisk
from .levels import RiskLevel


@dataclass(frozen=True)
class CheckpointAssessment:
    """A checkpoint with its position, ETA, weather, and risk."""

    seq: int
    lat: float
    lng: float
    distance_miles: float
    eta_epoch: int
    weather: dict
    risk: CheckpointRisk
    coverage_miles: float = 0.0  # miles from this checkpoint to the next one


@dataclass(frozen=True)
class RouteStats:
    distance_miles: float
    duration_hours: float
    eta_epoch: int
    severe_miles: float
    high_miles: float
    no_travel_miles: float
    per_level_miles: dict = field(default_factory=dict)
    avg_risk_score: float = 0.0
    avg_risk_label: str = "Low"

    @property
    def sort_key(self) -> tuple:
        """Lexicographic recommendation key; lower wins."""
        return (self.severe_miles, self.high_miles, self.avg_risk_score, self.duration_hours)


def _avg_risk_label(mean_score: float) -> str:
    if mean_score < 0.5:
        return RiskLevel.LOW.label
    if mean_score < 1.5:
        return RiskLevel.MODERATE.label
    if mean_score < 2.5:
        return RiskLevel.HIGH.label
    if mean_score < 3.5:
        return RiskLevel.SEVERE.label
    return RiskLevel.NO_TRAVEL.label


def route_stats(
    checkpoints: list[CheckpointAssessment],
    distance_miles: float,
    duration_hours: float,
) -> RouteStats:
    """Aggregate checkpoint risks into route-level statistics.

    Checkpoints with unknown weather (risk score None) are excluded from the
    average and from band mileage — they contribute neither safe nor unsafe
    miles, and the caller surfaces them as warnings instead.
    """
    per_level = {int(level): 0.0 for level in RiskLevel}
    scored = [cp for cp in checkpoints if cp.risk is not None]

    for cp in scored:
        per_level[int(cp.risk.overall)] += cp.coverage_miles

    severe_miles = per_level[int(RiskLevel.SEVERE)] + per_level[int(RiskLevel.NO_TRAVEL)]
    high_miles = per_level[int(RiskLevel.HIGH)]
    no_travel_miles = per_level[int(RiskLevel.NO_TRAVEL)]

    scores = [int(cp.risk.overall) for cp in scored]
    avg = round(statistics.mean(scores), 2) if scores else 0.0

    eta_epoch = checkpoints[-1].eta_epoch if checkpoints else 0

    return RouteStats(
        distance_miles=distance_miles,
        duration_hours=duration_hours,
        eta_epoch=eta_epoch,
        severe_miles=round(severe_miles, 1),
        high_miles=round(high_miles, 1),
        no_travel_miles=round(no_travel_miles, 1),
        per_level_miles={str(k): round(v, 1) for k, v in per_level.items()},
        avg_risk_score=avg,
        avg_risk_label=_avg_risk_label(avg),
    )


def _fmt(value: float, unit: str) -> str:
    return f"{value:g} {unit}"


def recommend(stats: list[RouteStats]) -> tuple[int, str]:
    """Pick the winning route index and a human-readable reason for the win.

    The reason names the first criterion on which the winner strictly beats
    every other route — i.e. the criterion that actually decided.
    """
    best_index = min(range(len(stats)), key=lambda i: stats[i].sort_key)
    best = stats[best_index]

    others = [s for i, s in enumerate(stats) if i != best_index]
    if not others:
        return best_index, "Only route available"
    criteria = [
        ("severe miles", best.severe_miles, min(s.severe_miles for s in others), "mi", "Fewest severe miles"),
        ("high miles", best.high_miles, min(s.high_miles for s in others), "mi", "Fewest high miles"),
        ("average risk", best.avg_risk_score, min(s.avg_risk_score for s in others), "", "Lowest average risk"),
        ("travel time", best.duration_hours, min(s.duration_hours for s in others), "h", "Shortest travel time"),
    ]

    reason = "Best overall profile"
    for _name, best_value, others_best, unit, phrase in criteria:
        if best_value < others_best:
            reason = f"{phrase} ({_fmt(best_value, unit)} vs {_fmt(others_best, unit)})"
            break

    return best_index, reason
