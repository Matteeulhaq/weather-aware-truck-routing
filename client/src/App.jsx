import { useState } from 'react'
import { usePlan } from './hooks/usePlan'
import PlanForm from './components/PlanForm'
import RouteMap from './components/RouteMap'
import Legend from './components/Legend'
import RouteCards from './components/RouteCards'

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
  const [plan, setPlan] = useState(null)
  const [selectedRouteId, setSelectedRouteId] = useState(null)
  const [focusTarget, setFocusTarget] = useState(null)
  const { mutate, isPending, error } = usePlan((data) => {
    setPlan(data)
    setSelectedRouteId(data.recommended_route_id)
  })

  return (
    <div className="flex h-full flex-col lg:flex-row">
      <aside className="flex h-1/2 w-full flex-col border-b border-slate-800 bg-slate-950 lg:h-full lg:w-[380px] lg:border-b-0 lg:border-r">
        <Header />
        <div className="scroll-thin flex-1 space-y-4 overflow-y-auto p-4">
          <PlanForm onSubmit={mutate} pending={isPending} error={error} />
          <RouteCards plan={plan} selectedRouteId={selectedRouteId} onSelectRoute={setSelectedRouteId} />
          {/* CheckpointTable (T3.7) mounts below the cards. */}
        </div>
      </aside>

      <main className="relative h-1/2 flex-1 lg:h-full">
        <RouteMap
          plan={plan}
          selectedRouteId={selectedRouteId}
          onSelectRoute={setSelectedRouteId}
          focusTarget={focusTarget}
        />
        <Legend />
        {/* HeatTimeline (T4.2) floats bottom-center. */}
      </main>
    </div>
  )
}
