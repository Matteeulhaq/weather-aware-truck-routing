/** Shimmer placeholders shown while a plan is being analyzed. */
export default function SkeletonCards() {
  return (
    <section aria-label="Loading results" className="space-y-2">
      <h2 className="text-xs font-semibold tracking-wide text-slate-400 uppercase">
        Analyzing routes…
      </h2>
      {[0, 1, 2].map((i) => (
        <div key={i} className="animate-pulse rounded-xl border border-slate-800 bg-slate-900/60 p-3">
          <div className="flex items-center justify-between">
            <div className="h-3.5 w-16 rounded bg-slate-700" />
            {i === 0 && <div className="h-4 w-24 rounded-full bg-sky-900/70" />}
          </div>
          <div className="mt-2 h-3 w-40 rounded bg-slate-800" />
          <div className="mt-3 flex gap-1.5">
            {[20, 16, 20, 24].map((w, j) => (
              <div key={j} className="h-4 rounded-md bg-slate-800" style={{ width: `${w * 4}px` }} />
            ))}
          </div>
        </div>
      ))}
    </section>
  )
}
