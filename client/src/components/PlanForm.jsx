import { useEffect, useState } from 'react'

const INTERVALS = [10, 25, 50]
const MAX_WEIGHT = 80_000

const LOADING_STAGES = [
  'Geocoding places…',
  'Fetching route options…',
  'Sampling checkpoint weather…',
  'Scoring risk & recommending…',
]

/** Tomorrow 08:00 local, formatted for <input type="datetime-local">. */
export function defaultDeparture() {
  const date = new Date()
  date.setDate(date.getDate() + 1)
  date.setHours(8, 0, 0, 0)
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function nowLocal() {
  const date = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function useLoadingStage(pending) {
  const [stage, setStage] = useState(0)
  useEffect(() => {
    if (!pending) {
      setStage(0)
      return undefined
    }
    const timer = setInterval(() => setStage((s) => (s + 1) % LOADING_STAGES.length), 1400)
    return () => clearInterval(timer)
  }, [pending])
  return LOADING_STAGES[stage]
}

export default function PlanForm({ onSubmit, pending, error }) {
  const [origin, setOrigin] = useState('')
  const [destination, setDestination] = useState('')
  const [departure, setDeparture] = useState(defaultDeparture)
  const [weight, setWeight] = useState('35000')
  const [intervalMiles, setIntervalMiles] = useState(25)
  const [validationError, setValidationError] = useState(null)
  const stage = useLoadingStage(pending)

  function handleSubmit(event) {
    event.preventDefault()
    if (!origin.trim() || !destination.trim()) {
      setValidationError('Origin and destination are both required.')
      return
    }
    const weightNum = Number(weight)
    if (!Number.isFinite(weightNum) || weightNum < 1 || weightNum > MAX_WEIGHT) {
      setValidationError(`Load weight must be between 1 and ${MAX_WEIGHT.toLocaleString()} lb.`)
      return
    }
    const departureDate = new Date(departure)
    if (Number.isNaN(departureDate.getTime())) {
      setValidationError('Departure date/time is invalid.')
      return
    }
    setValidationError(null)
    onSubmit({
      origin: origin.trim(),
      destination: destination.trim(),
      departure_time: departureDate.toISOString(),
      load_weight_lbs: Math.round(weightNum),
      sample_interval_miles: intervalMiles,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label htmlFor="origin" className="mb-1 block text-xs font-medium text-slate-300">
          Origin
        </label>
        <input
          id="origin"
          type="text"
          value={origin}
          onChange={(e) => setOrigin(e.target.value)}
          placeholder="City or address"
          autoComplete="off"
          className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:border-sky-500 focus:outline-none"
        />
      </div>

      <div>
        <label htmlFor="destination" className="mb-1 block text-xs font-medium text-slate-300">
          Destination
        </label>
        <input
          id="destination"
          type="text"
          value={destination}
          onChange={(e) => setDestination(e.target.value)}
          placeholder="City or address"
          autoComplete="off"
          className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:border-sky-500 focus:outline-none"
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="departure" className="mb-1 block text-xs font-medium text-slate-300">
            Departure
          </label>
          <input
            id="departure"
            type="datetime-local"
            value={departure}
            min={nowLocal()}
            onChange={(e) => setDeparture(e.target.value)}
            className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none"
          />
        </div>
        <div>
          <label htmlFor="weight" className="mb-1 block text-xs font-medium text-slate-300">
            Load weight (lb)
          </label>
          <input
            id="weight"
            type="number"
            min="1"
            max={MAX_WEIGHT}
            step="500"
            value={weight}
            onChange={(e) => setWeight(e.target.value)}
            className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none"
          />
        </div>
      </div>

      <div>
        <span className="mb-1 block text-xs font-medium text-slate-300">Weather checkpoint interval</span>
        <div className="grid grid-cols-3 overflow-hidden rounded-lg border border-slate-700">
          {INTERVALS.map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => setIntervalMiles(value)}
              aria-pressed={intervalMiles === value}
              className={`py-2 text-sm font-medium transition-colors ${
                intervalMiles === value
                  ? 'bg-sky-600 text-white'
                  : 'bg-slate-900 text-slate-300 hover:bg-slate-800'
              }`}
            >
              {value} mi
            </button>
          ))}
        </div>
        <p className="mt-1.5 text-xs text-slate-500">
          Heavy loads (over 30,000 / 40,000 lb) tighten wind rules at every checkpoint.
        </p>
      </div>

      {(validationError || error) && (
        <p
          role="alert"
          className="rounded-lg border border-red-900 bg-red-950/60 px-3 py-2 text-xs text-red-300"
        >
          {validationError ?? error.message}
        </p>
      )}

      <button
        type="submit"
        disabled={pending}
        className="w-full rounded-lg bg-sky-600 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {pending ? stage : 'Find safest routes'}
      </button>
    </form>
  )
}
