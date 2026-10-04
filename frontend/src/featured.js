import { api } from './api.js'
import { today } from './dates.js'

// The most recent completed major / Super 750+ tournament (detail payload with
// its finals) — the default "story" for Home and Head-to-Head.
const MAJOR_TIERS = [
  'Grade 1 – Individual Tournaments', 'HSBC BWF World Tour Finals',
  'HSBC BWF World Tour Super 1000', 'HSBC BWF World Tour Super 750',
]
let cache = null
export function latestMajor() {
  if (!cache) {
    cache = Promise.all(MAJOR_TIERS.map((tier) => api.tournaments({ tier, limit: 3 })))
      .then((lists) => {
        const done = lists.flatMap((l) => l.results).filter((t) => t.end_date && t.end_date <= today())
        done.sort((a, b) => (a.end_date < b.end_date ? 1 : -1))
        return done[0] ? api.tournament(done[0].tournament_id) : null
      })
      .catch((e) => { cache = null; throw e })
  }
  return cache
}
