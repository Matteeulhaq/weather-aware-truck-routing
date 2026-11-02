# Weather-Aware Truck Routing

Helps a truck driver choose the safest route based on **weather**, **load weight**, and **travel time**.
Built for the Spotter Full Stack Developer assessment: **React + Django**, OpenRouteService routing,
Open-Meteo hourly forecasts, and a 0–48 h weather-risk heatmap along the trip corridor.

## Status

| Phase | Scope | Status |
|---|---|---|
| 0 | Setup & repo bootstrap | ✅ |
| 1 | Backend foundations (risk engine, checkpoints) | ✅ |
| 2 | Routing & weather integrations | ✅ |
| 3 | Frontend core (map, cards, table) | ⏳ |
| 4 | Heatmap & 48 h timeline | ⏳ |
| 5 | Deploy & docs | ⏳ |

> Under active development — this table is updated as phases complete.

## Implemented so far

- **Risk engine** (`backend/routing/risk/`): wind/rain/snow classification tables, load-weight escalation rules, per-route band mileage (Severe/High/No-Travel miles), average risk, and the 4-level recommendation cascade — pure, unit-tested functions (68 tests passing).
- **Checkpoint interpolation** (`backend/routing/services/checkpoints.py`): places checkpoints every 10/25/50 miles along a route polyline and estimates arrival time at each one from per-step durations.
- **APIs** (`backend/routing/services/`): OpenRouteService directions (up to 3 alternatives; long trips get direct + via-point corridor routes since the public ORS API caps its alternatives algorithm at ~100 km) and geocoding; Open-Meteo batched hourly forecasts (wind mph, rain/snow in/hr) for every checkpoint at once.
- **`POST /api/plan/`** returns routes, checkpoints (weather + risk at the truck's ETA), per-route summaries, the recommendation with its reason, per-checkpoint 0–48 h hourly risk series for the slider, and warnings for checkpoints beyond the forecast horizon. Upstream calls are cached (directions 1 h / geocode 24 h / weather 15 min) with retry-once resilience.
