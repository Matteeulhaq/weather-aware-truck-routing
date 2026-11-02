import { riskColor } from '../lib/riskColors'
import { formatDateTime, formatHours } from '../lib/format'

function MileageChip({ label, miles, color }) {
  const active = miles > 0
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium ${
        active ? 'text-white' : 'text-slate-500'
      }`}
      style={active ? { backgroundColor: color } : { backgroundColor: '#1e293b' }}
    >
      {label} {miles} mi
    </span>
  )
}

function AvgRiskBadge({ score, label }) {
  return (
    <span
      className="inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-semibold text-white"
      style={{ backgroundColor: riskColor(label) }}
      title={`Average risk score ${score}`}
    >
      avg: {label} ({score})
    </span>
  )
}

export default function RouteCards({ plan, selectedRouteId, onSelectRoute }) {
  if (!plan) return null

  return (
    <section aria-label="Route options" className="space-y-2">
      <h2 className="text-xs font-semibold tracking-wide text-slate-400 uppercase">Route options</h2>
      {plan.routes.map((route) => {
        const { summary } = route
        const isRecommended = route.is_recommended
        const isSelected = route.route_id === selectedRouteId
        return (
          <button
            key={route.route_id}
            type="button"
            onClick={() => onSelectRoute(route.route_id)}
            aria-pressed={isSelected}
            className={`w-full rounded-xl border p-3 text-left transition-all ${
              isSelected
                ? 'border-sky-500 bg-slate-900 ring-1 ring-sky-500'
                : 'border-slate-800 bg-slate-900/60 hover:border-slate-600'
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-white">
                Route {route.route_id.replace('route_', '')}
              </span>
              {isRecommended && (
                <span className="rounded-full bg-sky-600 px-2 py-0.5 text-[11px] font-semibold text-white">
                  ★ Recommended
                </span>
              )}
            </div>

            <div className="mt-1 text-xs text-slate-400">
              {summary.distance_miles} mi · {formatHours(summary.duration_hours)} · arrive{' '}
              {formatDateTime(summary.eta)}
            </div>

            <div className="mt-2 flex flex-wrap gap-1.5">
              <MileageChip label="Severe" miles={summary.severe_miles} color="#ef4444" />
              <MileageChip label="High" miles={summary.high_miles} color="#f97316" />
              <MileageChip label="No Travel" miles={summary.no_travel_miles} color="#7f1d1d" />
              <AvgRiskBadge score={summary.avg_risk_score} label={summary.avg_risk_label} />
            </div>

            {isRecommended && plan.recommendation_reason && (
              <p className="mt-2 text-[11px] text-sky-300">{plan.recommendation_reason}</p>
            )}
          </button>
        )
      })}
    </section>
  )
}
