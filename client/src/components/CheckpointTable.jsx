import { riskColor } from '../lib/riskColors'
import { formatDateTime } from '../lib/format'

function RiskBadge({ risk }) {
  if (!risk) {
    return (
      <span className="inline-flex rounded-md bg-slate-800 px-2 py-0.5 text-[11px] font-medium text-slate-400">
        unknown
      </span>
    )
  }
  return (
    <span
      className="inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-semibold text-white"
      style={{ backgroundColor: riskColor(risk.overall) }}
    >
      {risk.load_rule_triggered ? '⚠ ' : ''}
      {risk.overall}
    </span>
  )
}

function WeatherCell({ value, unit }) {
  if (value === null || value === undefined || !Number.isFinite(value)) return <span className="text-slate-500">—</span>
  return (
    <span>
      {value} <span className="text-slate-500">{unit}</span>
    </span>
  )
}

/** Checkpoints of the selected route; clicking a row pans the map + opens the popup. */
export default function CheckpointTable({ plan, selectedRouteId, onFocusCheckpoint }) {
  if (!plan) return null

  const route = plan.routes.find((r) => r.route_id === selectedRouteId) ?? plan.routes[0]
  const routeNumber = route.route_id.replace('route_', '')

  return (
    <section aria-label="Checkpoints" className="space-y-2">
      <h2 className="text-xs font-semibold tracking-wide text-slate-400 uppercase">
        Checkpoints — Route {routeNumber}
      </h2>
      <div className="scroll-thin max-h-72 overflow-y-auto rounded-xl border border-slate-800">
        <table className="w-full border-collapse text-left text-xs">
          <thead className="sticky top-0 z-10 bg-slate-900">
            <tr className="text-slate-400">
              <th className="px-2 py-2 font-medium">#</th>
              <th className="px-2 py-2 font-medium">Mile</th>
              <th className="px-2 py-2 font-medium">ETA</th>
              <th className="px-2 py-2 font-medium">Wind</th>
              <th className="px-2 py-2 font-medium">Rain</th>
              <th className="px-2 py-2 font-medium">Snow</th>
              <th className="px-2 py-2 font-medium">Risk</th>
            </tr>
          </thead>
          <tbody>
            {route.checkpoints.map((cp) => (
              <tr
                key={cp.seq}
                onClick={() => onFocusCheckpoint({ routeId: route.route_id, seq: cp.seq })}
                className="cursor-pointer border-t border-slate-800 hover:bg-slate-800/60"
                title="Show on map"
              >
                <td className="px-2 py-1.5 text-slate-400">{cp.seq + 1}</td>
                <td className="px-2 py-1.5 text-slate-200">{cp.distance_miles}</td>
                <td className="px-2 py-1.5 text-slate-200">{formatDateTime(cp.eta)}</td>
                <td className="px-2 py-1.5">
                  <WeatherCell value={cp.weather?.available ? cp.weather.wind_mph : null} unit="mph" />
                </td>
                <td className="px-2 py-1.5">
                  <WeatherCell value={cp.weather?.available ? cp.weather.rain_in_hr : null} unit="in/h" />
                </td>
                <td className="px-2 py-1.5">
                  <WeatherCell value={cp.weather?.available ? cp.weather.snow_in_hr : null} unit="in/h" />
                </td>
                <td className="px-2 py-1.5">
                  <RiskBadge risk={cp.risk} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
