import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchGeocode } from '../api'

function useDebounced(value, delay) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}

/**
 * Text input with server-backed autocomplete.
 *
 * `value` is the display text; `onChange` receives either a resolved place
 * {name, lat, lng} (user picked a suggestion — exact coordinates, no backend
 * re-geocode drift) or {name: <raw text>, lat: null} (free-typed; the
 * backend geocodes it).
 */
export default function GeocodeInput({ id, label, placeholder, value, onChange }) {
  const [open, setOpen] = useState(false)
  const [justPicked, setJustPicked] = useState(null) // name that was picked
  const debouncedText = useDebounced(value, 300)
  const containerRef = useRef(null)

  const query = useQuery({
    queryKey: ['geocode', debouncedText],
    queryFn: ({ signal }) => fetchGeocode(debouncedText, signal),
    enabled: open && debouncedText.length >= 2 && debouncedText !== justPicked,
    staleTime: 5 * 60_000,
  })

  // Close when clicking outside.
  useEffect(() => {
    function onPointerDown(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [])

  function pick(place) {
    setJustPicked(place.name)
    onChange(place)
    setOpen(false)
  }

  function edit(rawText) {
    setJustPicked(null)
    onChange({ name: rawText, lat: null, lng: null })
    setOpen(rawText.trim().length >= 2)
  }

  const results = query.data?.results ?? []
  const showDropdown = open && (query.isFetching || results.length > 0 || (debouncedText.length >= 2 && !query.isFetching))

  return (
    <div ref={containerRef} className="relative">
      <label htmlFor={id} className="mb-1 block text-xs font-medium text-slate-300">
        {label}
      </label>
      <input
        id={id}
        type="text"
        value={value}
        onChange={(e) => edit(e.target.value)}
        onFocus={() => setOpen(value.trim().length >= 2)}
        onKeyDown={(e) => e.key === 'Escape' && setOpen(false)}
        placeholder={placeholder}
        autoComplete="off"
        role="combobox"
        aria-expanded={showDropdown}
        aria-controls={`${id}-options`}
        className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:border-sky-500 focus:outline-none"
      />
      {showDropdown && (
        <ul
          id={`${id}-options`}
          role="listbox"
          className="absolute z-20 mt-1 max-h-56 w-full overflow-y-auto rounded-lg border border-slate-700 bg-slate-900 shadow-xl shadow-black/40"
        >
          {query.isFetching && results.length === 0 && (
            <li className="px-3 py-2 text-xs text-slate-500">Searching…</li>
          )}
          {!query.isFetching && results.length === 0 && (
            <li className="px-3 py-2 text-xs text-slate-500">No matches</li>
          )}
          {results.map((place) => (
            <li key={`${place.name}-${place.lat}`}>
              <button
                type="button"
                role="option"
                aria-selected="false"
                onClick={() => pick(place)}
                className="w-full px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-800"
              >
                {place.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
