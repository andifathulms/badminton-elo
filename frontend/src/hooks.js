import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, withSignal } from './api.js'

// `value`, but only after it has stopped changing for `ms` — for search boxes,
// so typing "lin dan" sends one request instead of seven.
export function useDebounced(value, ms = 250) {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

// A page index that snaps back to 0 whenever `key` (the filters) changes —
// in the same render, so a filter change fetches page 0 directly instead of
// fetching the old page first and then resetting.
export function usePageFor(key) {
  const k = JSON.stringify(key)
  const [state, setState] = useState({ k, page: 0 })
  const page = state.k === k ? state.page : 0
  const setPage = (p) => setState((s) => {
    const cur = s.k === k ? s.page : 0
    return { k, page: typeof p === 'function' ? p(cur) : p }
  })
  return [page, setPage]
}

// Search-as-you-type player results for `q` (debounced, cached, stale
// requests cancelled). Empty until the query has 2+ characters.
export function usePlayerSearch(q) {
  const query = useDebounced(q.trim(), 250)
  const { data } = useQuery({
    queryKey: ['playerSearch', query],
    queryFn: ({ signal }) => withSignal(signal, () => api.searchPlayers(query)),
    enabled: query.length >= 2,
  })
  return q.trim().length >= 2 && data ? data.results : []
}
