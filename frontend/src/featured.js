import { api } from './api.js'
import { queryClient } from './queryClient.js'

// /api/home holds everything Home shows plus the most recent completed major
// (detail payload with its finals) — the default "story" for Home and
// Head-to-Head. One cached query, shared by both pages.
export function homeData() {
  return queryClient.fetchQuery({ queryKey: ['home'], queryFn: api.home, staleTime: 5 * 60 * 1000 })
}

export function latestMajor() {
  return homeData().then((h) => h.major)
}
