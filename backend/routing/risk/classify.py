"""Per-checkpoint weather classification and load rules.

Pure functions — no I/O, no Django imports — implementing the assessment's
threshold tables exactly:

| Condition | Low    | Moderate   | High       | Severe     | No Travel |
|-----------|--------|------------|------------|------------|-----------|
| Wind mph  | <25    | 25–34      | 35–44      | 45–54      | >=55      |
| Rain in/hr| <0.10  | 0.10–0.25  | 0.25–0.50  | 0.50–1.00  | >1.00     |
| Snow in/hr| <0.5   | 0.5–1.0    | 1.0–2.0    | 2.0–3.0    | >3.0      |

Boundary conventions (derived from the table's own notation):
- Wind uses ">=55" for No Travel, so each band's lower edge is inclusive
  (exactly 45 mph is Severe, exactly 55 mph is No Travel).
- Rain and snow No-Travel cells are written ">1.00" / ">3.0", so the top
  Severe edge is inclusive (exactly 1.00 in/hr rain is Severe, not No Travel).

Load rules (wind speed combined with load weight, applied on top of weather):
- >=55 mph wind            -> No Travel for any load
- Severe wind (45–54 mph) + >30,000 lb -> No Travel
- High wind (35–44 mph)    + >40,000 lb -> Severe

Load rules key off the *classified wind band* rather than raw integer ranges,
so values such as 54.5 mph classify as Severe wind and are load-rule eligible.
"""

from dataclasses import dataclass

from .levels import RiskLevel


def classify_wind(mph: float) -> RiskLevel:
    if mph >= 55:
        return RiskLevel.NO_TRAVEL
    if mph >= 45:
        return RiskLevel.SEVERE
    if mph >= 35:
        return RiskLevel.HIGH
    if mph >= 25:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def classify_rain(inches_per_hour: float) -> RiskLevel:
    if inches_per_hour > 1.00:
        return RiskLevel.NO_TRAVEL
    if inches_per_hour > 0.50:
        return RiskLevel.SEVERE
    if inches_per_hour > 0.25:
        return RiskLevel.HIGH
    if inches_per_hour >= 0.10:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def classify_snow(inches_per_hour: float) -> RiskLevel:
    if inches_per_hour > 3.0:
        return RiskLevel.NO_TRAVEL
    if inches_per_hour > 2.0:
        return RiskLevel.SEVERE
    if inches_per_hour > 1.0:
        return RiskLevel.HIGH
    if inches_per_hour >= 0.5:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def weather_severity(wind_mph: float, rain_in_hr: float, snow_in_hr: float) -> RiskLevel:
    """Worst single-condition level at a checkpoint."""
    return max(
        classify_wind(wind_mph),
        classify_rain(rain_in_hr),
        classify_snow(snow_in_hr),
    )


def load_rule_level(wind_level: RiskLevel, load_lbs: float) -> RiskLevel | None:
    """Escalation from load weight + wind band, or None when no rule applies."""
    if wind_level >= RiskLevel.NO_TRAVEL:
        return RiskLevel.NO_TRAVEL  # >=55 mph: No Travel for any load
    if wind_level == RiskLevel.SEVERE and load_lbs > 30_000:
        return RiskLevel.NO_TRAVEL  # 45–54 mph + >30,000 lb
    if wind_level == RiskLevel.HIGH and load_lbs > 40_000:
        return RiskLevel.SEVERE  # 35–44 mph + >40,000 lb
    return None


_LOAD_RULE_TEXT = {
    "any_load": "Wind >=55 mph: No Travel for any load",
    "heavy_severe_wind": "Wind 45–54 mph + load >30,000 lb: No Travel",
    "heavy_high_wind": "Wind 35–44 mph + load >40,000 lb: Severe",
}


@dataclass(frozen=True)
class CheckpointRisk:
    """Risk assessment for one checkpoint at one moment in time."""

    wind: RiskLevel
    rain: RiskLevel
    snow: RiskLevel
    overall: RiskLevel
    load_rule_triggered: str | None = None

    @property
    def score(self) -> int:
        return int(self.overall)


def checkpoint_risk(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lbs: float) -> CheckpointRisk:
    """Full checkpoint risk: worst weather condition, escalated by load rules."""
    wind = classify_wind(wind_mph)
    rain = classify_rain(rain_in_hr)
    snow = classify_snow(snow_in_hr)

    weather = max(wind, rain, snow)
    escalation = load_rule_level(wind, load_lbs)

    if escalation is not None:
        if wind >= RiskLevel.NO_TRAVEL:
            rule = _LOAD_RULE_TEXT["any_load"]
        elif wind == RiskLevel.SEVERE:
            rule = _LOAD_RULE_TEXT["heavy_severe_wind"]
        else:
            rule = _LOAD_RULE_TEXT["heavy_high_wind"]
        overall = max(weather, escalation)
    else:
        rule = None
        overall = weather

    return CheckpointRisk(wind=wind, rain=rain, snow=snow, overall=overall, load_rule_triggered=rule)
