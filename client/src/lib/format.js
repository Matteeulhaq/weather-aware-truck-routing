/** Shared formatting and date helpers. */

const pad = (n) => String(n).padStart(2, '0')

/** Tomorrow 08:00 local, formatted for <input type="datetime-local">. */
export function defaultDeparture() {
  const date = new Date()
  date.setDate(date.getDate() + 1)
  date.setHours(8, 0, 0, 0)
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/** Current local time formatted for datetime-local min attributes. */
export function nowLocal() {
  const date = new Date()
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/** Epoch seconds / ISO string -> "3:42 PM" in the browser's timezone. */
export function formatTime(iso) {
  return new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

/** ISO string -> "Tue, Nov 3 · 3:42 PM" (browser timezone). */
export function formatDateTime(iso) {
  return new Date(iso).toLocaleString([], {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

/** 5.83 -> "5 h 50 m" */
export function formatHours(hours) {
  const total = Math.round(hours * 60)
  const h = Math.floor(total / 60)
  const m = total % 60
  return m === 0 ? `${h} h` : `${h} h ${m} m`
}

/** Departure-relative hour -> "T+12h · Wed 2:00 PM". */
export function formatSliderHour(hour, departureIso) {
  const label = hour === 0 ? 'Departure' : `T+${hour}h`
  const time = new Date(new Date(departureIso).getTime() + hour * 3600_000)
  return `${label} · ${time.toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' })}`
}
