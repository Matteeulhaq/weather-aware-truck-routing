/** Risk level -> color, shared by markers, cards, badges, and the heat gradient. */

export const RISK_COLORS = {
  Low: '#22c55e',
  Moderate: '#eab308',
  High: '#f97316',
  Severe: '#ef4444',
  'No Travel': '#7f1d1d',
}

export const NO_DATA_COLOR = '#64748b'

export function riskColor(level) {
  return RISK_COLORS[level] ?? NO_DATA_COLOR
}

/** Legend entries in severity order. */
export const RISK_LEGEND = Object.entries(RISK_COLORS).map(([label, color]) => ({ label, color }))
