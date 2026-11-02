# Loom walkthrough script (5–10 min)

Demo-day notes. Warm the Render service ~1 min before recording (free tier cold-starts
in ~50 s). Two browser tabs: the live app + the GitHub repo.

## Demo trips (pick whichever shows weather that day)

| Pair | Load | Why |
|---|---|---|
| Amarillo, TX → Oklahoma City, OK | 35,000 lb | I-40 wind corridor; classic long-haul |
| Denver, CO → Kansas City, MO | 45,000 lb | Front-range wind/snow in season |
| Chicago, IL → Omaha, NE | 45,000 lb | Plains wind; run twice to show load-rule flip |

Check the forecast the morning of recording: pick a pair whose route shows wind ≥25 mph
so Moderate/High checkpoints are visible on the map. If a Severe band exists, the
45,000-lb run demonstrates the escalation rules live (45–54 mph + >30,000 lb = No Travel;
35–44 mph + >40,000 lb = Severe).

## Script (~8 minutes)

1. **The problem** (30 s). Truck drivers get ETAs but not weather. This app answers:
   "which of my 3 realistic routes is *safest* given when I'll actually be on each road
   segment, carrying *this* load?"

2. **Form** (45 s). Type origin/destination (autocomplete → note it resolves exact
   coordinates). Departure tomorrow 8 AM, load 35,000 lb, interval 25 mi. Submit.

3. **Map** (60 s). Three routes; the recommended one is highlighted blue. Hover a
   checkpoint: popup shows wind/rain/snow values, per-condition risk, ETA at that mile.
   **Key point:** the forecast is for the truck's *arrival time* at that checkpoint, not
   departure time.

4. **Route cards** (60 s). Severe/High/No-Travel miles + average risk per route.
   The recommended card shows the *reason* — e.g. "Fewest severe miles (0 mi vs 25 mi)".
   Emphasize the cascade is strict: severe miles first, then high miles, then average
   risk, and only then travel time. Click another card → map thickens it, table follows.

5. **Checkpoint table** (30 s). Rows are checkpoints; click a row → map flies there and
   opens the popup. Unknown-weather rows (beyond the horizon) show "unknown" — surfaced
   honestly rather than guessed.

6. **Heatmap + slider** (90 s — the centerpiece). The colored band along the route is
   the risk corridor. Default "Scheduled" mode = each point colored by risk at its own
   ETA. Switch to **Timeline**: drag 0→48 h. Note in DevTools' Network tab there are
   **zero new requests** — one fetch returned every checkpoint's full hourly series;
   the slider is pure re-render. Show the ▶ play animation sweeping the day.
   Markers recede while the band leads; flip back to Scheduled.

7. **Load rules live** (60 s). Re-run the same trip at 45,000 lb (interval 25 mi).
   On a windy day, High checkpoints flip to Severe and the recommendation can change.
   This is the assessment's load table applied at every checkpoint.

8. **Architecture + code** (90 s, second tab). Monorepo: `backend/` (Django + DRF)
   and `client/` (Vite React). Show:
   - `backend/routing/risk/` — pure, unit-tested tables & recommendation (no I/O).
   - `backend/routing/services/checkpoints.py` — mile-marker interpolation + ETA math
     from ORS step durations.
   - `backend/routing/services/planner.py` — one pipeline: geocode → routes →
     checkpoints → one batched weather call → risk → recommend.
   - `backend/routing/services/ors.py` — the ORS 100 km alternatives cap story and the
     via-point corridor fallback.
   - `client/src/components/RouteMap.jsx` — imperative Leaflet + persistent heat layer
     (`setLatLngs` per frame, rAF-throttled).
   - 109 backend tests; CI runs pytest + client build on every push.

9. **Deployment** (30 s). Single free Render service, one URL, health check, cached
   upstreams. Close with: "correctness and clarity over extra features — exactly as the
   brief asked."
