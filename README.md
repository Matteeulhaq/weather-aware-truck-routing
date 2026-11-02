# Weather-Aware Truck Routing

Helps a truck driver choose the **safest** route based on **weather**, **load weight**, and
**travel time**. Framework used: **React + Django**,
OpenRouteService routing, Open-Meteo hourly forecasts, and a 0–48 h weather-risk heatmap
along the trip corridor.

**Deployed link:** https://weather-aware-truck-routing-0i0q.onrender.com
**Walkthrough video:** _Loom link pending_

## Features

- **3 route options** per trip via OpenRouteService (`driving-hgv` profile, native
  alternatives; long trips fall back to direct + via-point corridor routes because the
  public ORS API caps its alternatives algorithm at ~100 km).
- **Weather sampled at each checkpoint** (every 10 / 25 / 50 miles) at the *truck's
  estimated arrival time* — not the departure time — using Open-Meteo's hourly forecast
  (wind mph, rain in/hr, snow in/hr, requested natively in those units).
- **Risk engine** with the assessment's wind/rain/snow threshold tables plus load-weight
  escalation rules, aggregated per route into Severe / High / No-Travel mileage and an
  average risk score.
- **Recommendation cascade**: fewest Severe miles → fewest High miles → lowest average
  risk → shortest travel time, with a human-readable reason for every win.
- **Map view** (Leaflet + Carto dark tiles): all routes, checkpoint markers colored by
  risk with detailed popups, ETAs, route summaries, and selection sync across cards,
  table, and map.
- **Weather heatmap** along the selected route's corridor with a **0–48 h forecast
  slider** (Scheduled-ETA and Timeline modes, play animation). One fetch covers the whole
  window — dragging the slider re-renders with **zero network calls**.

## Architecture

```
┌──────────────┐  POST /api/plan   ┌───────────────────────┐  directions (+alternatives)
│ React (Vite) │ ────────────────▶ │  Django + DRF          │ ─────────────────────────▶ OpenRouteService
│ Leaflet map  │ ◀──────────────── │  risk engine (pure)    │  geocode (autocomplete)    (free key)
│ heat slider  │   plan JSON       │  checkpoint sampling   │  forecast (hourly, batched)─▶ Open-Meteo (keyless)
└──────────────┘                   │  caching + retries     │
                                   └───────────────────────┘
```

Single Render web service: Django serves both the API and the built React bundle
(WhiteNoise + gzip) — same origin, so no CORS anywhere. Stateless; no database tables
(sqlite exists only as Django's default). Upstream responses are cached in-process:
directions 1 h, geocode 24 h, weather 15 min — with one retry (1 s backoff) on transient
5xx/network errors and friendly 429/502 API errors.

## Quickstart (local)

Prerequisites: Python 3.12+, Node 18+, an [OpenRouteService](https://openrouteservice.org)
free API key.

```bash
# backend
python -m venv .venv && source .venv/Scripts/activate   # Git Bash; .venv/bin/activate on macOS/Linux
pip install -r backend/requirements.txt
cp .env.example backend/.env                            # then paste your ORS_API_KEY
python backend/manage.py migrate
python backend/manage.py runserver 8000

# frontend (second terminal)
cd client && npm install && npm run dev                  # http://localhost:5173
```

The Vite dev server proxies `/api` to `localhost:8000`. Production parity check:
`npm run build` (in `client/`), then open `http://localhost:8000/` — Django serves the SPA.

## Environment variables

| Variable | Where | Purpose |
|---|---|---|
| `SECRET_KEY` | `backend/.env` / Render | Django secret (auto-generated on Render) |
| `DEBUG` | both | `True` locally, `False` in production |
| `ORS_API_KEY` | both | OpenRouteService key — server-side only, never in the client bundle |
| `VITE_CARTO_API_KEY` | `client/.env.local` / Render | [CARTO basemaps](https://carto.com/basemaps) key for the dark map tiles (free account). Inlined into the client bundle at build time; without it the map falls back to keyless OpenStreetMap tiles |
| `ALLOWED_HOSTS` | Render | Comma-separated hosts (`.onrender.com`) |

## API

### `POST /api/plan/`

```bash
curl -X POST http://localhost:8000/api/plan/ -H "Content-Type: application/json" -d '{
  "origin": "Amarillo, TX",
  "destination": "Oklahoma City, OK",
  "departure_time": "2026-11-03T14:00:00Z",
  "load_weight_lbs": 35000,
  "sample_interval_miles": 25
}'
```

`origin`/`destination` accept a free-text place (backend geocodes the first hit) or a
resolved `{"name", "lat", "lng"}` object (used by the autocomplete picker). Response:
`hours[]` (departure-relative UTC epoch grid, ≤ 49 entries), `recommended_route_id`,
`recommendation_reason`, `routes[]` (summary + `geometry` + `checkpoints[]`), `warnings[]`.

Each checkpoint carries: `distance_miles`, `eta` (ISO UTC), `lat/lng`, `weather`
(wind/rain/snow + `available`), `risk` (overall + per-condition levels, score, and which
load rule fired), and `hourly` (the 0–48 h series driving the heatmap slider,
`risk_scores` aligned with the top-level `hours[]`).

### `GET /api/geocode/?text=…` — autocomplete proxy (keeps the ORS key server-side)
### `GET /api/health/` — liveness probe

## Risk & load rules (as specified by the assessment)

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind (mph) | <25 | 25–34 | 35–44 | 45–54 | ≥55 |
| Rain (in/hr) | <0.10 | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | >1.00 |
| Snow (in/hr) | <0.5 | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | >3.0 |

Load rules (wind + load weight):
- **≥55 mph → No Travel** for any load
- **45–54 mph + >30,000 lb → No Travel**
- **35–44 mph + >40,000 lb → Severe**

### Stated conventions

- **Band boundaries** follow the table's own notation: wind bands are lower-edge
  inclusive (45 mph → Severe, 55 mph → No Travel); rain/snow No-Travel cells are strict
  (">"), so exactly 1.00 in/hr rain is Severe and exactly 3.0 in/hr snow is Severe.
- **Load rules key off the classified wind band**, not raw integer ranges — 54.5 mph is
  Severe-band wind and is load-rule eligible (covered by tests).
- **Overall checkpoint risk** = max(weather conditions), escalated by load rules; the
  fired rule is reported as `load_rule_triggered`.
- **Miles attribution**: checkpoint *i* covers the road to checkpoint *i+1* (the final
  checkpoint covers nothing), so band mileage equals "count × interval" for interior
  bands and handles the final partial segment exactly.
- **Average risk**: mean ordinal score (Low=0 … No Travel=4), labeled by monotonic
  banding (<0.5 Low, <1.5 Moderate, <2.5 High, <3.5 Severe, else No Travel).
- **ETA→forecast hour**: nearest hour of Open-Meteo's hourly grid (UTC epochs).
- **Heatmap band** interpolates risk *scores* between bracketing checkpoints for
  visualization only; the checkpoint markers carry the authoritative analysis.
- Checkpoints beyond the ~72 h forecast horizon return `weather.available=false`, are
  excluded from mileage/averages, and are listed in `warnings[]`.

## Testing

```bash
cd backend && python -m pytest        # 109 tests: threshold boundary matrices, load rules,
                                      # aggregation, recommendation cascade, interpolation, mocked clients
cd client && npm run lint && npm run build
```

CI (`.github/workflows/ci.yml`) runs both on every push.

## Deployment (Render)

Single free web service via the committed Blueprint (`render.yaml`): pip install →
`npm ci && npm run build` → migrate → collectstatic → gunicorn (1 worker × 4 threads,
health-checked at `/api/health/`). Deploy: Render dashboard → **New + → Blueprint** →
select this repository → paste `ORS_API_KEY` → deploy. Node is preflighted
(`node -v`); the documented fallback is a multi-stage Dockerfile swap if the build image
ever lacks Node.

## Assumptions & limitations

- Forecast horizon: Open-Meteo provides ~72 h from *now*; departures further out return
  routes with unknown weather and an amber warning (the slider clamps to what's available).
- ETA-to-hour matching rounds to the nearest hour (hourly forecast granularity).
- Wind is sampled at 10 m above ground (`wind_speed_10m`), the forecast model's standard.
- The public ORS API's alternatives algorithm is limited to ~100 km routes; longer trips
  use direct + via-point corridor routes (each a genuine HGV-profile route), so a trip
  may return 1–3 options.
- Free-tier Render instances cold-start in ~50 s; the first request may be slow.
- The heatmap band is a visualization aid; risk classification itself lives exclusively
  in the backend risk engine (`backend/routing/risk/`), which has no I/O and is fully
  unit-tested.
