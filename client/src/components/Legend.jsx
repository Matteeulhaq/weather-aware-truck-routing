import { RISK_LEGEND } from '../lib/riskColors'

export default function Legend() {
  return (
    <div className="pointer-events-none absolute left-3 top-3 z-[500] rounded-lg border border-slate-700/70 bg-slate-950/85 px-3 py-2 shadow-lg shadow-black/30 lg:bottom-5 lg:left-3 lg:top-auto">
      <p className="mb-1.5 text-[10px] font-semibold tracking-wide text-slate-400 uppercase">
        Checkpoint risk
      </p>
      <ul className="space-y-1">
        {RISK_LEGEND.map(({ label, color }) => (
          <li key={label} className="flex items-center gap-2 text-xs text-slate-200">
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
            {label}
          </li>
        ))}
      </ul>
    </div>
  )
}
