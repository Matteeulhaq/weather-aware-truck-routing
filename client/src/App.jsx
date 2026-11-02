function Header() {
  return (
    <header className="border-b border-slate-800 px-4 py-3">
      <h1 className="flex items-center gap-2 text-sm font-semibold tracking-tight text-white">
        <span aria-hidden>🚚</span> Weather-Aware Truck Routing
      </h1>
      <p className="mt-0.5 text-xs text-slate-400">The safest route, not just the fastest.</p>
    </header>
  )
}

export default function App() {
  return (
    <div className="flex h-full flex-col lg:flex-row">
      <aside className="flex h-1/2 w-full flex-col border-b border-slate-800 bg-slate-950 lg:h-full lg:w-[380px] lg:border-b-0 lg:border-r">
        <Header />
        <div className="scroll-thin flex-1 space-y-4 overflow-y-auto p-4">
          {/* PlanForm (task T3.2) and route results (T3.6/T3.7) mount here. */}
          <p className="text-sm text-slate-500">Trip planner loads here.</p>
        </div>
      </aside>

      <main className="relative h-1/2 flex-1 lg:h-full">
        {/* RouteMap (T3.4) mounts here. */}
        <div className="flex h-full w-full items-center justify-center bg-slate-900 text-sm text-slate-500">
          Map loads here.
        </div>
        {/* HeatTimeline (T4.2) floats bottom-center; Legend (T3.5) bottom-left. */}
      </main>
    </div>
  )
}
