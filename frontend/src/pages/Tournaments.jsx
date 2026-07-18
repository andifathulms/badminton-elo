import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import { useAsync } from '../useAsync.js'
import Select from '../components/Select.jsx'
import Pager from '../components/Pager.jsx'

const YEARS = Array.from({ length: 21 }, (_, i) => 2026 - i)
const YEAR_OPTS = [{ value: '', label: 'All years' }, ...YEARS.map((y) => ({ value: y, label: String(y) }))]
const PAGE = 40
const shortTier = (s) => (s || '').replace('HSBC BWF World Tour ', '').replace('BWF ', '')

// A tournament is live if today falls within its date window.
function isOngoing(t) {
  if (!t.start_date) return false
  const today = new Date().toISOString().slice(0, 10)
  const end = t.end_date || t.start_date
  return t.start_date <= today && today <= end
}

export default function Tournaments() {
  const [year, setYear] = useState('')
  const [tier, setTier] = useState('')
  const [page, setPage] = useState(0)
  useEffect(() => setPage(0), [year, tier])

  const { data: tiers } = useAsync(() => api.tournamentTiers(), [])
  const { data, error, loading } = useAsync(
    () => api.tournaments({ year, tier, limit: PAGE, offset: page * PAGE }),
    [year, tier, page],
  )

  const tierOpts = [
    { value: '', label: 'All tiers' },
    ...(tiers || []).map((t) => ({ value: t.tier, label: `${shortTier(t.tier)} (${t.count})` })),
  ]

  return (
    <div>
      <div className="toolbar wrap" style={{ justifyContent: 'space-between' }}>
        <div className="page-head" style={{ marginBottom: 0 }}>
          <div className="kicker">BWF World Tour · History</div>
          <h1 className="page-title">Tournaments</h1>
        </div>
        <div className="filters">
          <Select label="Tier" value={tier} onChange={setTier} options={tierOpts} />
          <Select label="Year" value={year} onChange={setYear} options={YEAR_OPTS} />
        </div>
      </div>
      {loading && <p className="muted">Loading…</p>}
      {error && <p className="error">Could not load: {error.message}</p>}
      {data && (
        <>
          <table className="board">
            <thead>
              <tr>
                <th>Tournament</th>
                <th>Tier</th>
                <th className="num">Dates</th>
                <th className="num">Matches</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((t) => (
                <tr key={t.tournament_id}>
                  <td>
                    <Link to={`/tournaments/${t.tournament_id}`}>{t.name}</Link>
                    {isOngoing(t) && <span className="badge-live">● Live</span>}
                  </td>
                  <td className="muted small">{shortTier(t.category_name)}</td>
                  <td className="num muted small">
                    {t.start_date}{t.end_date ? ` → ${t.end_date.slice(5)}` : ''}
                  </td>
                  <td className="num muted">{t.match_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pager page={page} setPage={setPage} count={data.count} pageSize={PAGE} unit="tournaments" />
          {data.results.length === 0 && <p className="muted">No tournaments match.</p>}
        </>
      )}
    </div>
  )
}
