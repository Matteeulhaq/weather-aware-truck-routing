"""Boundary matrices for the classification tables.

Values probe both edges of every band, including values that sit *between*
the table's integer labels (e.g. 24.9, 54.5) to lock down the conventions.
"""

import pytest

from routing.risk.classify import (
    classify_rain,
    classify_snow,
    classify_wind,
    checkpoint_risk,
    load_rule_level,
    weather_severity,
)
from routing.risk.levels import RiskLevel

L, M, H, S, NT = RiskLevel


@pytest.mark.parametrize(
    ("mph", "expected"),
    [
        (0, L), (24.9, L),
        (25, M), (34, M), (34.9, M),
        (35, H), (44, H), (44.9, H),
        (45, S), (54, S), (54.5, S),
        (55, NT), (80, NT),
    ],
)
def test_classify_wind(mph, expected):
    assert classify_wind(mph) == expected


@pytest.mark.parametrize(
    ("in_hr", "expected"),
    [
        (0.0, L), (0.09, L),
        (0.10, M), (0.25, M),
        (0.26, H), (0.50, H),
        (0.51, S), (1.00, S),
        (1.01, NT), (2.0, NT),
    ],
)
def test_classify_rain(in_hr, expected):
    assert classify_rain(in_hr) == expected


@pytest.mark.parametrize(
    ("in_hr", "expected"),
    [
        (0.0, L), (0.4, L),
        (0.5, M), (1.0, M),
        (1.1, H), (2.0, H),
        (2.1, S), (3.0, S),
        (3.1, NT), (5.0, NT),
    ],
)
def test_classify_snow(in_hr, expected):
    assert classify_snow(in_hr) == expected


def test_weather_severity_takes_the_worst_condition():
    # 60 mph wind alone is No Travel even with dry weather.
    assert weather_severity(60, 0, 0) == NT
    # Moderate rain + Low wind -> Moderate.
    assert weather_severity(10, 0.2, 0) == M
    # High snow dominates Low wind and light rain.
    assert weather_severity(10, 0.1, 1.5) == H


@pytest.mark.parametrize(
    ("wind_mph", "load_lbs", "expected"),
    [
        (55, 0, NT),                      # any wind band NT -> any load
        (55, 80_000, NT),
        (54.5, 30_001, NT),               # Severe band + just over 30k (fractional mph)
        (45, 30_000, None),               # Severe band, not over 30k
        (54, 25_000, None),               # Severe band, light load
        (44, 40_001, S),                  # High band + just over 40k
        (35, 40_000, None),               # High band, not over 40k
        (34.9, 80_000, None),             # Moderate band: no load rules
        (10, 80_000, None),
    ],
)
def test_load_rule_level(wind_mph, load_lbs, expected):
    assert load_rule_level(classify_wind(wind_mph), load_lbs) == expected


def test_checkpoint_risk_no_escalation_by_default():
    risk = checkpoint_risk(wind_mph=20, rain_in_hr=0.0, snow_in_hr=0.0, load_lbs=35_000)

    assert risk.overall == L
    assert risk.load_rule_triggered is None
    assert risk.score == 0


def test_checkpoint_risk_high_wind_heavy_load_escalates_to_severe():
    risk = checkpoint_risk(wind_mph=40, rain_in_hr=0.0, snow_in_hr=0.0, load_lbs=45_000)

    assert risk.wind == H
    assert risk.overall == S
    assert "40,000" in risk.load_rule_triggered


def test_checkpoint_risk_severe_wind_heavy_load_escalates_to_no_travel():
    risk = checkpoint_risk(wind_mph=50, rain_in_hr=0.0, snow_in_hr=0.0, load_lbs=31_000)

    assert risk.overall == NT
    assert "30,000" in risk.load_rule_triggered


def test_checkpoint_risk_escalation_never_lowers_weather_risk():
    # Heavy snow (Severe) with High wind + heavy load: load rule yields Severe,
    # weather already Severe -> overall Severe either way.
    risk = checkpoint_risk(wind_mph=40, rain_in_hr=0.0, snow_in_hr=2.5, load_lbs=45_000)

    assert risk.overall == S
