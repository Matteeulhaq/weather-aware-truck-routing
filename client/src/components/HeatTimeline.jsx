import { useEffect, useState } from 'react'
import { formatSliderHour } from '../lib/format'

const MAX_HOURS = 48
const PLAY_STEP_MS = 400

export default function HeatTimeline({ plan, hour, setHour, timelineMode, setTimelineMode }) {
  const [playing, setPlaying] = useState(false)
  const maxHour = Math.min(MAX_HOURS, (plan?.hours?.length ?? 1) - 1)

  // Reset when a new plan narrows the window.
  const effectiveHour = Math.min(hour, Math.max(0, maxHour))

  useEffect(() => {
    if (!playing || !timelineMode || maxHour <= 0) return undefined
    const timer = setInterval(() => {
      setHour((h) => {
        if (h >= maxHour) {
          setPlaying(false)
          return h
        }
        return h + 1
      })
    }, PLAY_STEP_MS)
    return () => clearInterval(timer)
  }, [playing, timelineMode, maxHour, setHour])

  if (!plan || maxHour < 1) return null

  const tickEvery = 6
  const ticks = []
  for (let t = 0; t <= maxHour; t += tickEvery) ticks.push(t)
  if (ticks[ticks.length - 1] !== maxHour) ticks.push(maxHour)

  return (
    <div className="absolute bottom-4 left-1/2 z-[500] w-[min(560px,calc(100%-2rem))] -translate-x-1/2 rounded-xl border border-slate-700/70 bg-slate-950/90 px-4 py-3 shadow-xl shadow-black/40 backdrop-blur">
      <div className="flex items-center justify-between gap-3">
        <span className="min-w-0 truncate text-xs font-medium text-slate-200">
          {timelineMode ? (
            <>
              Forecast <span className="text-sky-300">{formatSliderHour(effectiveHour, plan.departure_time)}</span>
            </>
          ) : (
            <>Scheduled — risk at each checkpoint's own ETA</>
          )}
        </span>
        <div className="flex shrink-0 items-center gap-1.5">
          <div className="flex overflow-hidden rounded-lg border border-slate-700 text-[11px]">
            <button
              type="button"
              onClick={() => {
                setPlaying(false)
                setTimelineMode(false)
              }}
              aria-pressed={!timelineMode}
              className={`px-2 py-1 font-medium ${!timelineMode ? 'bg-sky-600 text-white' : 'bg-slate-900 text-slate-300 hover:bg-slate-800'}`}
            >
              Scheduled
            </button>
            <button
              type="button"
              onClick={() => setTimelineMode(true)}
              aria-pressed={timelineMode}
              className={`px-2 py-1 font-medium ${timelineMode ? 'bg-sky-600 text-white' : 'bg-slate-900 text-slate-300 hover:bg-slate-800'}`}
            >
              Timeline
            </button>
          </div>
          {timelineMode && (
            <button
              type="button"
              onClick={() => setPlaying((p) => !p)}
              aria-label={playing ? 'Pause animation' : 'Play forecast animation'}
              className="flex h-7 w-7 items-center justify-center rounded-lg border border-slate-700 bg-slate-900 text-xs text-slate-200 hover:bg-slate-800"
            >
              {playing ? '⏸' : '▶'}
            </button>
          )}
        </div>
      </div>

      <input
        type="range"
        min={0}
        max={maxHour}
        step={1}
        value={effectiveHour}
        disabled={!timelineMode}
        onChange={(e) => {
          setPlaying(false)
          setHour(Number(e.target.value))
        }}
        aria-label="Forecast hours after departure"
        className="mt-2 w-full accent-sky-500 disabled:opacity-40"
      />
      <div className="flex justify-between text-[10px] text-slate-500">
        {ticks.map((t) => (
          <span key={t}>{t}h</span>
        ))}
      </div>
    </div>
  )
}
