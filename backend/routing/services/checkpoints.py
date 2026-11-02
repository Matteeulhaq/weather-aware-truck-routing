"""Checkpoint interpolation along an OpenRouteService route geometry.

Given a route's polyline, per-step durations, and a sampling interval, this
module places checkpoints every N miles and estimates the truck's arrival
time (ETA epoch) at each one.

Distance: haversine over consecutive vertices, then uniformly rescaled so the
total matches ORS's road distance (haversine underestimates road geometry by
roughly 1%; the rescale keeps checkpoint distances honest against the summary).

Duration at an arbitrary vertex: ORS reports durations per *step*
(`segments[].steps[].duration`) plus the step's vertex range
(`way_points = [startIdx, endIdx]`). That gives cumulative duration at step
boundaries; interior vertices are filled by piecewise-linear interpolation
(duration proportional to distance within a step — an approximation that is
well within the hourly weather granularity).

`instructions` must stay enabled and `geometry_simplify` false on the ORS
request, otherwise way_points no longer align with the geometry.
"""

import math
from bisect import bisect_left

METERS_PER_MILE = 1609.344
EARTH_RADIUS_M = 6_371_008.8
MAX_CHECKPOINTS = 250

# A regular interval checkpoint landing this close to the destination is
# dropped in favor of the destination checkpoint itself.
_END_MERGE_METERS = 0.5 * METERS_PER_MILE


def haversine_m(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    """Great-circle distance in meters between two (lng, lat) points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def cumulative_distances(coords: list) -> list:
    """Cumulative haversine distance (m) at each vertex of [[lng, lat], ...]."""
    cum = [0.0]
    for (lng1, lat1), (lng2, lat2) in zip(coords, coords[1:]):
        cum.append(cum[-1] + haversine_m(lng1, lat1, lng2, lat2))
    return cum


def rescale(cum: list, total_m: float) -> list:
    """Scale cumulative distances so the last equals the ORS road distance."""
    if not cum or cum[-1] <= 0:
        return cum
    factor = total_m / cum[-1]
    return [d * factor for d in cum]


def vertex_durations(coords: list, cumdist: list, segments: list, total_duration_s: float) -> list:
    """Cumulative seconds at each vertex, from ORS steps + linear fill."""
    n = len(coords)
    if n == 0:
        return []
    if n == 1:
        return [0.0]

    marks = {0: 0.0, n - 1: total_duration_s}
    elapsed = 0.0
    for segment in segments or []:
        for step in segment.get("steps", []):
            elapsed += float(step.get("duration", 0.0))
            way_points = step.get("way_points") or []
            if len(way_points) == 2 and 0 < way_points[1] < n - 1:
                marks[way_points[1]] = elapsed

    durations = [0.0] * n
    indices = sorted(marks)
    for i1, i2 in zip(indices, indices[1:]):
        t1, t2 = marks[i1], marks[i2]
        span = cumdist[i2] - cumdist[i1]
        for j in range(i1, i2 + 1):
            frac = (cumdist[j] - cumdist[i1]) / span if span > 0 else 0.0
            durations[j] = t1 + (t2 - t1) * frac
    return durations


def checkpoint_targets(total_m: float, interval_miles: float) -> list:
    """Distances (m) to sample: 0, interval, ..., total (with end-merge + cap)."""
    interval_m = interval_miles * METERS_PER_MILE
    targets = []
    d = 0.0
    while d < total_m - _END_MERGE_METERS:
        targets.append(d)
        d += interval_m
    targets.append(total_m)

    if len(targets) > MAX_CHECKPOINTS:
        stride = math.ceil(len(targets) / MAX_CHECKPOINTS)
        kept = targets[::stride]
        if kept[-1] != targets[-1]:
            kept.append(targets[-1])
        targets = kept
    return targets


def _interp_at(cumdist: list, values: list, d: float) -> float:
    """Linear interpolation of `values` (aligned with `cumdist`) at distance d."""
    if d <= cumdist[0]:
        return values[0]
    if d >= cumdist[-1]:
        return values[-1]
    i = bisect_left(cumdist, d)
    span = cumdist[i] - cumdist[i - 1]
    frac = (d - cumdist[i - 1]) / span if span > 0 else 0.0
    return values[i - 1] + (values[i] - values[i - 1]) * frac


def build_checkpoints(
    coords: list,
    segments: list,
    summary_distance_m: float,
    summary_duration_s: float,
    departure_epoch: int,
    interval_miles: float,
) -> list:
    """Checkpoints as dicts: seq, lat, lng, distance_miles, eta_epoch, duration_hours."""
    if len(coords) < 2:
        lng, lat = coords[0]
        return [
            {
                "seq": 0,
                "lat": lat,
                "lng": lng,
                "distance_miles": 0.0,
                "eta_epoch": departure_epoch,
                "duration_hours": 0.0,
            }
        ]

    cumdist = rescale(cumulative_distances(coords), summary_distance_m)
    durations = vertex_durations(coords, cumdist, segments, summary_duration_s)
    lats = [c[1] for c in coords]
    lngs = [c[0] for c in coords]

    checkpoints = []
    for seq, d in enumerate(checkpoint_targets(summary_distance_m, interval_miles)):
        seconds = _interp_at(cumdist, durations, d)
        checkpoints.append(
            {
                "seq": seq,
                "lat": _interp_at(cumdist, lats, d),
                "lng": _interp_at(cumdist, lngs, d),
                "distance_miles": d / METERS_PER_MILE,
                "eta_epoch": int(round(departure_epoch + seconds)),
                "duration_hours": seconds / 3600.0,
            }
        )
    return checkpoints
