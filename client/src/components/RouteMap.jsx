import { useEffect, useRef } from 'react'
import L from 'leaflet'
import { toLeafletLatLngs } from '../lib/geo'

const RECOMMENDED_STYLE = { color: '#38bdf8', weight: 6, opacity: 0.95 }
const SELECTED_STYLE = { color: '#7dd3fc', weight: 6, opacity: 0.95 }
const BASE_STYLE = { color: '#64748b', weight: 3.5, opacity: 0.7 }
const DIM_STYLE = { color: '#475569', weight: 2.5, opacity: 0.4 }

export default function RouteMap({ plan, selectedRouteId, onSelectRoute }) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const routesGroupRef = useRef(null)
  const polylineRefs = useRef(new Map())

  // Map lifecycle — once. The remove() cleanup keeps StrictMode's
  // double-mount from hitting "Map container is already initialized".
  useEffect(() => {
    if (mapRef.current || !containerRef.current) return undefined

    const map = L.map(containerRef.current, { preferCanvas: true })
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
      maxZoom: 19,
    }).addTo(map)
    map.setView([39.5, -98.35], 4)

    mapRef.current = map
    return () => {
      map.remove()
      mapRef.current = null
      routesGroupRef.current = null
      polylineRefs.current = new Map()
    }
  }, [])

  // Rebuild route polylines when a new plan arrives.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !plan) return

    if (routesGroupRef.current) routesGroupRef.current.remove()
    routesGroupRef.current = L.layerGroup().addTo(map)
    polylineRefs.current = new Map()

    for (const route of plan.routes) {
      const polyline = L.polyline(toLeafletLatLngs(route.geometry), BASE_STYLE)
      polyline.on('click', () => onSelectRoute?.(route.route_id))
      polyline.bindTooltip(
        `${route.route_id.replace('route_', 'Route ')} · ${route.summary.distance_miles} mi`,
        { sticky: true },
      )
      polyline.addTo(routesGroupRef.current)
      polylineRefs.current.set(route.route_id, polyline)
    }

    const bounds = routesGroupRef.current.getBounds()
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [45, 45] })
  }, [plan, onSelectRoute])

  // Selection styling — pure imperative restyle, no layer rebuild.
  useEffect(() => {
    if (!plan) return
    for (const [routeId, polyline] of polylineRefs.current) {
      const isRecommended = routeId === plan.recommended_route_id
      const isSelected = routeId === selectedRouteId
      let style
      if (isSelected && !isRecommended) style = SELECTED_STYLE
      else if (isRecommended) style = RECOMMENDED_STYLE
      else if (selectedRouteId) style = DIM_STYLE
      else style = BASE_STYLE
      polyline.setStyle(style)
      polyline.bringToFront?.()
    }
  }, [plan, selectedRouteId])

  return <div ref={containerRef} className="h-full w-full" aria-label="Route map" />
}
