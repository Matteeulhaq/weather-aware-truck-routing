const TONES = {
  error: 'border-red-900 bg-red-950/60 text-red-300',
  warning: 'border-amber-800 bg-amber-950/50 text-amber-300',
}

/** Inline banner for API errors and forecast warnings. */
export default function ErrorBanner({ tone = 'error', title, items }) {
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={`rounded-lg border px-3 py-2 text-xs ${TONES[tone] ?? TONES.error}`}
    >
      {title && <p className="font-semibold">{title}</p>}
      {items?.length > 0 && (
        <ul className="mt-1 list-inside list-disc space-y-0.5">
          {items.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      )}
      {!items?.length && title}
    </div>
  )
}
