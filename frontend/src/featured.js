import { api } from './api.js'

// /api/home holds everything Home shows plus the most recent completed major
// (detail payload with its finals) — the default "story" for Home and
// Head-to-Head. One request, shared by both pages for a few minutes.
const TTL_MS = 5 * 60 * 1000
let cache = null
let at = 0

export function homeData() {
  if (!cache || Date.now() - at > TTL_MS) {
    at = Date.now()
    cache = api.home().catch((e) => { cache = null; throw e })
  }
  return cache
}

export function latestMajor() {
  return homeData().then((h) => h.major)
}
