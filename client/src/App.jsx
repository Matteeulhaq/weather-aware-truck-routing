import { useState } from 'react'
import { usePlan } from './hooks/usePlan'
import PlanForm from './components/PlanForm'
import RouteMap from './components/RouteMap'
import Legend from './components/Legend'
import RouteCards from './components/RouteCards'
import CheckpointTable from './components/CheckpointTable'
import HeatTimeline from './components/HeatTimeline'
import ErrorBanner from './components/ErrorBanner'
import ErrorBoundary from './components/ErrorBoundary'
import SkeletonCards from './components/SkeletonCards'

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
  const [sliderHour, setSliderHour] = useState(0)
  const [timelineMode, setTimelineMode] = useState(false)
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

          {isPending && <SkeletonCards />}

          {!isPending && plan?.warnings?.length > 0 && (
            <ErrorBanner tone="warning" title="Forecast gaps" items={plan.warnings} />
          )}

          {!isPending && plan && (
            <>
              <RouteCards plan={plan} selectedRouteId={selectedRouteId} onSelectRoute={setSelectedRouteId} />
              <CheckpointTable
                plan={plan}
                selectedRouteId={selectedRouteId}
                onFocusCheckpoint={setFocusTarget}
              />
            </>
          )}

          {!isPending && !plan && (
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 text-xs leading-relaxed text-slate-400">
              <p className="mb-2 text-sm font-semibold text-slate-200">Plan a trip</p>
              <p>
                Enter an origin, destination, departure time, and load weight. The app fetches 3
                route options, forecasts the weather at each checkpoint's arrival time, applies
                wind/rain/snow and load-weight risk rules, and recommends the safest route.
              </p>
            </div>
          )}
        </div>
      </aside>

      <main className="relative h-1/2 flex-1 lg:h-full">
        <ErrorBoundary>
          <RouteMap
            plan={plan}
            selectedRouteId={selectedRouteId}
            onSelectRoute={setSelectedRouteId}
            focusTarget={focusTarget}
            sliderHour={sliderHour}
            timelineMode={timelineMode}
          />
        </ErrorBoundary>
        <Legend />
        <HeatTimeline
          plan={plan}
          hour={sliderHour}
          setHour={setSliderHour}
          timelineMode={timelineMode}
          setTimelineMode={setTimelineMode}
        />
      </main>
    </div>
  )
}
