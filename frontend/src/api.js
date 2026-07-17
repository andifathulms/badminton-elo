// Single source of truth for API calls. Dev uses the Vite proxy (/api ->
// Django); set VITE_API_BASE at build time for Docker/prod.
const BASE = import.meta.env.VITE_API_BASE || '/api'

async function get(path) {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

const qs = (params) =>
  Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
    .join('&')

export const api = {
  events: () => get('/events'),
  leaderboard: (event, { minMatches = 5, order = 'rating', ranking = 'current', gender, limit = 50, offset = 0 } = {}) =>
    get(`/leaderboard?${qs({ event, min_matches: minMatches, order, ranking, gender, limit, offset })}`),
  pairs: (event, { minMatches = 5, limit = 50, offset = 0 } = {}) =>
    get(`/pairs?${qs({ event, min_matches: minMatches, limit, offset })}`),
  player: (id) => get(`/players/${id}`),
  playerHistory: (id, event) => get(`/players/${id}/history?${qs({ event })}`),
  playerMatches: (id, { event, limit = 25, offset = 0 } = {}) =>
    get(`/players/${id}/matches?${qs({ event, limit, offset })}`),
  match: (id) => get(`/matches/${id}`),
}

export const EVENTS = [
  { code: 'MS', label: "Men's Singles" },
  { code: 'WS', label: "Women's Singles" },
  { code: 'MD', label: "Men's Doubles" },
  { code: 'WD', label: "Women's Doubles" },
  { code: 'XD', label: 'Mixed Doubles' },
]
