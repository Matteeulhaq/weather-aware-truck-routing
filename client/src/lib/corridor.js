/**
 * Corridor construction for the heatmap band.
 *
 * Route geometry is densified to ~3-mile spacing; each dense point remembers
 * its two bracketing checkpoints and the interpolation fraction between
 * them. At render time the band's intensity is the linear blend of those two
 * checkpoints' risk values (visualization only — the checkpoint markers stay
 * the authoritative analysis).
 */

const METERS_PER_MILE = 1609.344
const EARTH_RADIUS_M = 6_371_008.8

function haversineM(a, b) {
  // a, b: [lat, lng]
  const toRad = (d) => (d * Math.PI) / 180
  const dLat = toRad(b[0] - a[0])
  const dLng = toRad(b[1] - a[1])
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a[0])) * Math.cos(toRad(b[0])) * Math.sin(dLng / 2) ** 2
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(s))
}

/**
 * Dense corridor for a route: [{lat, lng, distMiles, i0, i1, f}...] where
 * i0/i1 index the route's checkpoints and f is the blend fraction.
 */
export function buildCorridor(route, spacingMiles = 3) {
  const checkpoints = route.checkpoints
  if (!checkpoints || checkpoints.length < 2) return []

  const pts = route.geometry.map(([lng, lat]) => [lat, lng])
  if (pts.length < 2) return []

  const spacingM = spacingMiles * METERS_PER_MILE

  // Cumulative distance per geometry vertex.
  const cum = [0]
  for (let i = 1; i < pts.length; i += 1) {
    cum.push(cum[i - 1] + haversineM(pts[i - 1], pts[i]))
  }
  const totalM = cum[cum.length - 1] || 1
  // Scale to the checkpoints' known road distances (mirrors backend rescale).
  const scale =
    checkpoints[checkpoints.length - 1].distance_miles / (totalM / METERS_PER_MILE)

  const corridor = []
  let vertex = 0
  let targetM = 0
  while (targetM <= totalM) {
    while (vertex + 1 < pts.length - 1 && cum[vertex + 1] < targetM) vertex += 1
    const next = Math.min(vertex + 1, pts.length - 1)
    const segM = cum[next] - cum[vertex] || 1
    const t = Math.min(1, Math.max(0, (targetM - cum[vertex]) / segM))
    const a = pts[vertex]
    const b = pts[next]

    const distMiles = (targetM / METERS_PER_MILE) * scale
    // Bracketing checkpoints by road distance.
    let i1 = 1
    while (i1 < checkpoints.length - 1 && checkpoints[i1].distance_miles < distMiles) i1 += 1
    const i0 = i1 - 1
    const span = checkpoints[i1].distance_miles - checkpoints[i0].distance_miles || 1
    const f = Math.min(1, Math.max(0, (distMiles - checkpoints[i0].distance_miles) / span))

    corridor.push({
      lat: a[0] + (b[0] - a[0]) * t,
      lng: a[1] + (b[1] - a[1]) * t,
      distMiles,
      i0,
      i1,
      f,
    })
    targetM += spacingM
  }
  return corridor
}

function scoreAt(checkpoint, hour) {
  /** Checkpoint risk score at a slider hour (null-safe), or at its own ETA when hour is null. */
  if (hour === null) return checkpoint.risk ? checkpoint.risk.score : null
  const scores = checkpoint.hourly?.risk_scores
  if (!scores || scores.length === 0) return null
  const idx = Math.min(hour, scores.length - 1)
  return idx >= 0 ? scores[idx] : null
}

function blendScore(cp0, cp1, f, hour) {
  const a = scoreAt(cp0, hour)
  const b = scoreAt(cp1, hour)
  if (a === null && b === null) return null
  if (a === null) return b
  if (b === null) return a
  return a + (b - a) * f
}

/**
 * Heat points for the band: [[lat, lng, intensity], ...], intensity 0..4.
 * hour === null -> "Scheduled (ETA)" mode (each point blends ETA-based risks).
 */
export function heatPoints(corridor, checkpoints, hour) {
  const points = []
  for (const p of corridor) {
    const intensity = blendScore(checkpoints[p.i0], checkpoints[p.i1], p.f, hour)
    if (intensity === null) continue
    points.push([p.lat, p.lng, Math.max(0, Math.min(4, intensity))])
  }
  return points
}
