import { useEffect, useRef } from 'react'
import L from 'leaflet'
import { toLeafletLatLngs } from '../lib/geo'
import { riskColor, NO_DATA_COLOR } from '../lib/riskColors'
import { formatDateTime } from '../lib/format'

const RECOMMENDED_STYLE = { color: '#38bdf8', weight: 6, opacity: 0.95 }
const SELECTED_STYLE = { color: '#7dd3fc', weight: 6, opacity: 0.95 }
const BASE_STYLE = { color: '#64748b', weight: 3.5, opacity: 0.7 }
const DIM_STYLE = { color: '#475569', weight: 2.5, opacity: 0.4 }

const MARKER_OPACITY = { normal: 0.95, dimmed: 0.3 }

function esc(value) {
  return String(value).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))
}

function popupHtml(checkpoint) {
  const { weather, risk } = checkpoint
  const rows = []
  if (weather?.available) {
    rows.push(`<div class="mt-1">💨 ${esc(weather.wind_mph)} mph · 🌧 ${esc(weather.rain_in_hr)} in/h · ❄ ${esc(weather.snow_in_hr)} in/h</div>`)
  } else {
    rows.push('<div class="mt-1">No forecast available</div>')
  }
  if (risk) {
    rows.push(
      `<div class="mt-1">Wind <b>${esc(risk.wind)}</b> · Rain <b>${esc(risk.rain)}</b> · Snow <b>${esc(risk.snow)}</b></div>`,
    )
    if (risk.load_rule_triggered) {
      rows.push(`<div class="mt-1" style="color:#fbbf24">⚠ ${esc(risk.load_rule_triggered)}</div>`)
    }
  } else {
    rows.push('<div class="mt-1">Risk unknown (outside forecast horizon)</div>')
  }
  return (
    `<div style="min-width:190px">` +
    `<div><b>Checkpoint ${esc(checkpoint.seq + 1)}</b> · mile ${esc(checkpoint.distance_miles)}</div>` +
    `<div>ETA ${esc(formatDateTime(checkpoint.eta))}</div>` +
    rows.join('') +
    `</div>`
  )
}

export default function RouteMap({ plan, selectedRouteId, onSelectRoute, focusTarget }) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const routesGroupRef = useRef(null)
  const checkpointsGroupRef = useRef(null)
  const polylineRefs = useRef(new Map())
  const markerRefs = useRef(new Map())

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
      checkpointsGroupRef.current = null
      polylineRefs.current = new Map()
      markerRefs.current = new Map()
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

    // Checkpoint markers, colored by risk at the truck's ETA.
    if (checkpointsGroupRef.current) checkpointsGroupRef.current.remove()
    checkpointsGroupRef.current = L.layerGroup().addTo(map)
    markerRefs.current = new Map()

    for (const route of plan.routes) {
      for (const checkpoint of route.checkpoints) {
        const color = riskColor(checkpoint.risk?.overall) || NO_DATA_COLOR
        const marker = L.circleMarker([checkpoint.lat, checkpoint.lng], {
          radius: 5.5,
          fillColor: color,
          fillOpacity: MARKER_OPACITY.normal,
          color: '#0f172a',
          weight: 1.5,
        })
        marker.bindPopup(popupHtml(checkpoint), {
          className: 'risk-popup',
          closeButton: true,
        })
        marker.on('click', () => onSelectRoute?.(route.route_id))
        marker.addTo(checkpointsGroupRef.current)
        markerRefs.current.set(`${route.route_id}:${checkpoint.seq}`, marker)
      }
    }
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
    for (const [key, marker] of markerRefs.current) {
      const routeId = key.split(':')[0]
      const dimmed = Boolean(selectedRouteId) && routeId !== selectedRouteId
      marker.setStyle({ fillOpacity: dimmed ? MARKER_OPACITY.dimmed : MARKER_OPACITY.normal })
    }
  }, [plan, selectedRouteId])

  // Fly to a checkpoint (from the table) and open its popup.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !focusTarget) return
    const marker = markerRefs.current.get(`${focusTarget.routeId}:${focusTarget.seq}`)
    if (!marker) return
    map.flyTo(marker.getLatLng(), Math.max(map.getZoom(), 9), { duration: 0.8 })
    marker.openPopup()
  }, [focusTarget])

  return (
    <>
      <div ref={containerRef} className="h-full w-full" aria-label="Route map" />
    </>
  )
}
