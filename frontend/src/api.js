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
  pairs: (event, { minMatches = 5, ranking = 'current', limit = 50, offset = 0 } = {}) =>
    get(`/pairs?${qs({ event, min_matches: minMatches, ranking, limit, offset })}`),
  pairDetail: (event, p1, p2) => get(`/pairs/detail?${qs({ event, p1, p2 })}`),
  h2h: (event, p1, p2) => get(`/h2h?${qs({ event, p1, p2 })}`),
  tournamentMatches: (id, { event, limit = 100, offset = 0 } = {}) =>
    get(`/tournaments/${id}/matches?${qs({ event, limit, offset })}`),
  tournamentTies: (id) => get(`/tournaments/${id}/ties`),
  analytics: (kind, { event, minMatches = 2, limit = 40, includeNew } = {}) =>
    get(`/analytics/${kind}?${qs({ event, min_matches: minMatches, limit, include_new: includeNew ? 1 : '' })}`),
  performancePath: (player, event, tournament) =>
    get(`/performance/path?${qs({ player, event, tournament })}`),
  records: (kind, { event, limit = 25 } = {}) =>
    get(`/records/${kind}?${qs({ event, limit })}`),
  calibration: (event) => get(`/analytics/calibration?${qs({ event })}`),
  aging: (event) => get(`/analytics/aging?${qs({ event })}`),
  clutch: (event, { min = 15, order = 'pct' } = {}) =>
    get(`/analytics/clutch?${qs({ event, min, order })}`),
  player: (id) => get(`/players/${id}`),
  playerStyle: (id, partner) => get(`/players/${id}/style?${qs({ partner })}`),
  playerHistory: (id, event) => get(`/players/${id}/history?${qs({ event })}`),
  playerMatches: (id, { event, limit = 25, offset = 0 } = {}) =>
    get(`/players/${id}/matches?${qs({ event, limit, offset })}`),
  match: (id) => get(`/matches/${id}`),
  matchStatistics: (id) => get(`/matches/${id}/statistics`),
  searchPlayers: (q) => get(`/players?${qs({ q, limit: 12 })}`),
  tournaments: ({ year, tier, q, limit = 40, offset = 0 } = {}) =>
    get(`/tournaments?${qs({ year, tier, q, limit, offset })}`),
  tournamentTiers: () => get('/tournaments/tiers'),
  tournamentMaster: (year) => get(`/tournaments/master?${qs({ year })}`),
  tournament: (id) => get(`/tournaments/${id}`),
  cup: (cup) => get(`/cups/${cup}`),
  cupHistory: (cup) => get(`/cups/${cup}/history`),
}

export const EVENTS = [
  { code: 'MS', label: "Men's Singles" },
  { code: 'WS', label: "Women's Singles" },
  { code: 'MD', label: "Men's Doubles" },
  { code: 'WD', label: "Women's Doubles" },
  { code: 'XD', label: 'Mixed Doubles' },
]
