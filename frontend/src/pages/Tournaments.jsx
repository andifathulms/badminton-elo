import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import { useAsync } from '../useAsync.js'
import Select from '../components/Select.jsx'

const YEARS = Array.from({ length: 21 }, (_, i) => 2026 - i)
const YEAR_OPTS = [{ value: '', label: 'All years' }, ...YEARS.map((y) => ({ value: y, label: String(y) }))]

export default function Tournaments() {
  const [year, setYear] = useState('')
  const { data, error, loading } = useAsync(
    () => api.tournaments({ year, limit: 60 }),
    [year],
  )

  return (
    <div>
      <div className="toolbar">
        <div className="page-head" style={{ marginBottom: 0 }}>
          <div className="kicker">BWF World Tour · History</div>
          <h1 className="page-title">Tournaments</h1>
        </div>
        <Select label="Year" value={year} onChange={setYear} options={YEAR_OPTS} />
      </div>
      {loading && <p className="muted">Loading…</p>}
      {error && <p className="error">Could not load: {error.message}</p>}
      {data && (
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
                </td>
                <td className="muted small">
                  {(t.category_name || '').replace('HSBC BWF World Tour ', '')}
                </td>
                <td className="num muted small">
                  {t.start_date}{t.end_date ? ` → ${t.end_date.slice(5)}` : ''}
                </td>
                <td className="num muted">{t.match_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
