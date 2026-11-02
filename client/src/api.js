/** Thin API layer — all backend access goes through the /api proxy. */

const BASE = '/api'

/** Extract a readable message from DRF error bodies (string detail or field errors). */
function detailFrom(body) {
  if (!body) return null
  if (typeof body.detail === 'string') return body.detail
  for (const [field, errors] of Object.entries(body)) {
    const first = Array.isArray(errors) ? errors[0] : errors
    const text = typeof first === 'string' ? first : first?.message
    if (text) return field === 'detail' ? text : `${field}: ${text}`
  }
  return null
}

async function parse(response) {
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    throw new Error(detailFrom(body) ?? `Request failed (${response.status})`)
  }
  return body
}

export async function postPlan(payload) {
  const response = await fetch(`${BASE}/plan/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return parse(response)
}

export async function fetchGeocode(text, signal) {
  const response = await fetch(`${BASE}/geocode/?text=${encodeURIComponent(text)}`, { signal })
  return parse(response)
}
