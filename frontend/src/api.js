// Single source of truth for API calls. Dev uses the Vite proxy (/api ->
// Django); set VITE_API_BASE at build time for Docker/prod.
const BASE = import.meta.env.VITE_API_BASE || '/api'

async function get(path) {
  const res = await fetch(`${BASE}${path}`, { credentials: 'same-origin' })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

// Django's CSRF token, planted as a cookie by GET /api/auth/me. Echoed back in
// the X-CSRFToken header on every write so session-authenticated writes pass.
function csrfToken() {
  const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return m ? decodeURIComponent(m[1]) : ''
}

// Unsafe-method request with JSON body + CSRF. Throws an Error whose .status and
// .data carry the server's response so callers can show a real message.
async function send(method, path, body) {
  const hasBody = body !== undefined
  const res = await fetch(`${BASE}${path}`, {
    method,
    credentials: 'same-origin',
    headers: {
      ...(hasBody ? { 'Content-Type': 'application/json' } : {}),
      'X-CSRFToken': csrfToken(),
    },
    body: hasBody ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    let data = null
    try { data = await res.json() } catch { /* non-JSON error */ }
    const msg = data?.detail || Object.values(data || {})[0] || `${res.status} ${res.statusText}`
    const err = new Error(Array.isArray(msg) ? msg[0] : msg)
    err.status = res.status
    err.data = data
    throw err
  }
  return res.status === 204 ? null : res.json()
}

const post = (path, body) => send('POST', path, body)
const patch = (path, body) => send('PATCH', path, body)
const del = (path) => send('DELETE', path)

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
  // s1/s2 are arrays of player ids (1 for singles, up to 2 for doubles).
  h2h: (event, s1, s2) =>
    get(`/h2h?${qs({ event, s1: s1.join(','), s2: s2.join(',') })}`),
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
  dynasties: (event) => get(`/analytics/dynasties?${qs({ event })}`),
  consistency: (event, { min = 40, order = 'steady' } = {}) =>
    get(`/analytics/consistency?${qs({ event, min, order })}`),
  synergy: (event, { min = 20, order = 'best' } = {}) =>
    get(`/analytics/synergy?${qs({ event, min, order })}`),
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
  refreshStatus: () => get('/refresh/status'),
  refreshStart: () => post('/refresh'),

  // --- Auth (session) ---
  authMe: () => get('/auth/me'),
  authLogin: (username, password) => post('/auth/login', { username, password }),
  authLogout: () => post('/auth/logout'),

  // --- Studio (staff-only writes) ---
  studioTournamentCreate: (body) => post('/studio/tournaments', body),
  studioTournamentEdit: (id, patchBody) => patch(`/studio/tournaments/${id}`, patchBody),
  studioMatches: (tid) => get(`/studio/tournaments/${tid}/matches`),
  studioMatchCreate: (tid, body) => post(`/studio/tournaments/${tid}/matches`, body),
  studioMatchEdit: (id, body) => patch(`/studio/matches/${id}`, body),
  studioMatchDelete: (id) => del(`/studio/matches/${id}`),
  studioPlayerCreate: (body) => post('/studio/players', body),
  studioPlayerEdit: (id, body) => patch(`/studio/players/${id}`, body),
  studioRebuild: () => post('/studio/rebuild'),
}

export const EVENTS = [
  { code: 'MS', label: "Men's Singles" },
  { code: 'WS', label: "Women's Singles" },
  { code: 'MD', label: "Men's Doubles" },
  { code: 'WD', label: "Women's Doubles" },
  { code: 'XD', label: 'Mixed Doubles' },
]
