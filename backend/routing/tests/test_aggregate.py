"""Route-stat aggregation and the recommendation tie-break chain."""

from routing.risk.aggregate import CheckpointAssessment, RouteStats, recommend, route_stats
from routing.risk.classify import CheckpointRisk
from routing.risk.levels import RiskLevel

L, M, H, S, NT = RiskLevel


def cp(distance_miles, coverage, level, eta_epoch=0):
    """Build a checkpoint assessment with a fixed overall level."""
    return CheckpointAssessment(
        seq=0,
        lat=0.0,
        lng=0.0,
        distance_miles=distance_miles,
        eta_epoch=eta_epoch,
        weather={},
        risk=CheckpointRisk(wind=level, rain=level, snow=level, overall=level),
        coverage_miles=coverage,
    )


def test_route_stats_band_mileage():
    # 25 mi Low + 25 mi Moderate + 25 mi High + 15 mi Severe (partial final segment).
    checkpoints = [cp(0, 25, L), cp(25, 25, M), cp(50, 25, H), cp(75, 15, S), cp(90, 0, L)]

    stats = route_stats(checkpoints, distance_miles=90, duration_hours=2.0)

    assert stats.severe_miles == 15.0  # Severe + No Travel
    assert stats.high_miles == 25.0
    assert stats.no_travel_miles == 0.0
    assert stats.per_level_miles == {"0": 25.0, "1": 25.0, "2": 25.0, "3": 15.0, "4": 0.0}
    assert stats.eta_epoch == 0  # last checkpoint's ETA


def test_route_stats_no_travel_counts_toward_severe():
    checkpoints = [cp(0, 10, NT), cp(10, 0, L)]

    stats = route_stats(checkpoints, distance_miles=10, duration_hours=0.5)

    assert stats.severe_miles == 10.0
    assert stats.no_travel_miles == 10.0


def test_route_stats_avg_score_and_label_banding():
    # Scores 0,0,1,3 -> mean 1.0 -> Moderate (banding, not rounding).
    checkpoints = [cp(0, 10, L), cp(10, 10, L), cp(20, 10, M), cp(30, 0, S)]

    stats = route_stats(checkpoints, distance_miles=30, duration_hours=1.0)

    assert stats.avg_risk_score == 1.0
    assert stats.avg_risk_label == "Moderate"


def test_route_stats_unknown_weather_excluded():
    scored = [cp(0, 25, L), cp(25, 0, L)]
    unscored = CheckpointAssessment(
        seq=2, lat=0.0, lng=0.0, distance_miles=50, eta_epoch=0,
        weather={}, risk=None, coverage_miles=25,
    )

    stats = route_stats([*scored, unscored], distance_miles=50, duration_hours=1.0)

    assert stats.avg_risk_score == 0.0
    assert stats.per_level_miles["0"] == 25.0  # unscored coverage not attributed


def test_route_stats_all_unknown_averages_to_low():
    unscored = CheckpointAssessment(
        seq=0, lat=0.0, lng=0.0, distance_miles=10, eta_epoch=0,
        weather={}, risk=None, coverage_miles=10,
    )

    stats = route_stats([unscored], distance_miles=10, duration_hours=0.2)

    assert stats.avg_risk_score == 0.0
    assert stats.avg_risk_label == "Low"


def _stats(severe=0.0, high=0.0, avg=0.0, hours=5.0) -> RouteStats:
    return RouteStats(
        distance_miles=100, duration_hours=hours, eta_epoch=0,
        severe_miles=severe, high_miles=high, no_travel_miles=0.0,
        per_level_miles={}, avg_risk_score=avg, avg_risk_label="x",
    )


def test_recommend_prefers_fewest_severe_miles_first():
    safe_but_slow = _stats(severe=0, high=40, avg=1.5, hours=8.0)
    fast_but_severe = _stats(severe=25, high=0, avg=0.5, hours=5.0)

    index, reason = recommend([fast_but_severe, safe_but_slow])

    assert index == 1
    assert reason.startswith("Fewest severe miles")


def test_recommend_high_miles_breaks_severe_tie():
    a = _stats(severe=10, high=30, avg=2.0, hours=5.0)
    b = _stats(severe=10, high=5, avg=2.5, hours=6.0)

    index, reason = recommend([a, b])

    assert index == 1
    assert reason.startswith("Fewest high miles")


def test_recommend_avg_risk_breaks_high_tie():
    a = _stats(severe=0, high=10, avg=1.2, hours=5.0)
    b = _stats(severe=0, high=10, avg=0.4, hours=6.0)

    index, reason = recommend([a, b])

    assert index == 1
    assert reason.startswith("Lowest average risk")


def test_recommend_travel_time_is_the_final_tie_breaker():
    a = _stats(severe=0, high=10, avg=0.5, hours=6.0)
    b = _stats(severe=0, high=10, avg=0.5, hours=5.5)

    index, reason = recommend([a, b])

    assert index == 1
    assert reason.startswith("Shortest travel time")


def test_recommend_single_route():
    index, reason = recommend([_stats()])

    assert index == 0
    assert reason == "Only route available"
