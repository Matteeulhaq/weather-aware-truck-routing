/** Coordinate conventions: ORS/Open-Meteo use [lng, lat]; Leaflet wants [lat, lng]. */

export function toLeafletLatLngs(lngLatPairs) {
  return lngLatPairs.map(([lng, lat]) => [lat, lng])
}
