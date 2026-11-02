"""Checkpoint interpolation against synthetic routes with known geometry."""

import math

from routing.services import checkpoints as ck

METERS_PER_MILE = ck.METERS_PER_MILE

# One degree of latitude in meters on the module's earth model.
DEG_LAT_M = 2 * math.pi * ck.EARTH_RADIUS_M / 360


def ns_line(lat_start, n_vertices, miles_per_vertex):
    """North-south polyline with evenly spaced vertices, going north."""
    step_deg = miles_per_vertex * METERS_PER_MILE / DEG_LAT_M
    return [[-100.0, lat_start + i * step_deg] for i in range(n_vertices)]


def single_step(total_duration_s, last_index):
    return [
        {
            "steps": [
                {"duration": total_duration_s, "way_points": [0, last_index]},
            ]
        }
    ]


def test_cumulative_distances_monotonic_and_total_matches_haversine():
    coords = ns_line(35.0, 11, 1.0)  # 10 legs of ~1 mile each

    cum = ck.cumulative_distances(coords)

    assert cum[0] == 0.0
    assert all(b > a for a, b in zip(cum, cum[1:]))
    direct = ck.haversine_m(coords[0][0], coords[0][1], coords[-1][0], coords[-1][1])
    assert math.isclose(cum[-1], direct, rel_tol=1e-9)


def test_rescale_matches_summary_distance():
    coords = ns_line(35.0, 11, 1.0)
    cum = ck.cumulative_distances(coords)
    road_total = cum[-1] * 1.05  # pretend road distance is 5% longer

    scaled = ck.rescale(cum, road_total)

    assert math.isclose(scaled[-1], road_total, rel_tol=1e-9)
    assert scaled[0] == 0.0


def test_vertex_durations_linear_single_step():
    coords = ns_line(35.0, 11, 1.0)
    cum = ck.cumulative_distances(coords)
    durations = ck.vertex_durations(coords, cum, single_step(3600.0, 10), 3600.0)

    assert durations[0] == 0.0
    assert math.isclose(durations[5], 1800.0, rel_tol=1e-9)  # halfway
    assert math.isclose(durations[-1], 3600.0)


def test_vertex_durations_two_steps_meet_at_boundary():
    coords = ns_line(35.0, 11, 1.0)
    cum = ck.cumulative_distances(coords)
    segments = [
        {"steps": [{"duration": 1200.0, "way_points": [0, 5]}]},
        {"steps": [{"duration": 2400.0, "way_points": [5, 10]}]},
    ]

    durations = ck.vertex_durations(coords, cum, segments, 3600.0)

    assert math.isclose(durations[5], 1200.0, rel_tol=1e-6)
    assert math.isclose(durations[-1], 3600.0)
    assert durations[2] < durations[5] < durations[8]


def test_vertex_durations_falls_back_to_linear_without_steps():
    coords = ns_line(35.0, 11, 1.0)
    cum = ck.cumulative_distances(coords)

    durations = ck.vertex_durations(coords, cum, None, 3600.0)

    assert math.isclose(durations[5], 1800.0, rel_tol=1e-9)


def test_targets_include_origin_and_destination():
    total = 34.0 * METERS_PER_MILE

    targets = ck.checkpoint_targets(total, 10)

    assert targets[0] == 0.0
    assert math.isclose(targets[-1], total)
    # 0, 10, 20, 30 mi + destination
    assert len(targets) == 5


def test_targets_merge_final_checkpoint_within_half_mile():
    total = 9.8 * METERS_PER_MILE  # a 10-mi target would land 0.2 mi from the end

    targets = ck.checkpoint_targets(total, 10)

    assert len(targets) == 2  # origin + destination only
    assert math.isclose(targets[-1], total)


def test_targets_capped_at_maximum():
    total = 260.0 * METERS_PER_MILE

    targets = ck.checkpoint_targets(total, 1)

    assert len(targets) <= ck.MAX_CHECKPOINTS
    assert targets[0] == 0.0
    assert math.isclose(targets[-1], total)


def test_build_checkpoints_positions_and_etas():
    coords = ns_line(35.0, 21, 1.0)  # 20-mile route; the 10-mi checkpoint is the midpoint
    total = ck.cumulative_distances(coords)[-1]
    departure = 1_700_000_000

    cps = ck.build_checkpoints(coords, single_step(3600.0, 20), total, 3600.0, departure, 10)

    assert cps[0]["lat"] == coords[0][1]
    assert cps[0]["lng"] == coords[0][0]
    assert cps[0]["eta_epoch"] == departure
    assert cps[-1]["lat"] == coords[-1][1]
    assert cps[-1]["eta_epoch"] == departure + 3600
    # Monotonicity in mile and ETA.
    assert all(b["distance_miles"] > a["distance_miles"] for a, b in zip(cps, cps[1:]))
    assert all(b["eta_epoch"] >= a["eta_epoch"] for a, b in zip(cps, cps[1:]))
    # A checkpoint sits exactly at the halfway mile with halfway duration.
    mid = min(cps, key=lambda c: abs(c["distance_miles"] - 10.0))
    assert abs(mid["distance_miles"] - 10.0) < 0.05
    assert abs(mid["eta_epoch"] - (departure + 1800)) <= 1


def test_build_checkpoints_distance_rescaled_to_summary():
    coords = ns_line(35.0, 11, 1.0)
    hav_total = ck.cumulative_distances(coords)[-1]
    road_total = hav_total * 1.1
    departure = 1_700_000_000

    cps = ck.build_checkpoints(coords, single_step(3600.0, 10), road_total, 3600.0, departure, 10)

    assert math.isclose(cps[-1]["distance_miles"], road_total / METERS_PER_MILE, rel_tol=1e-9)
