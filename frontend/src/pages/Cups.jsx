import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import { useAsync } from '../useAsync.js'
import { flag } from '../flags.js'
import PageHeader from '../components/PageHeader.jsx'

const CUPS = [
  { key: 'thomas', label: 'Thomas Cup', sub: "Men's team · 3 MS + 2 MD" },
  { key: 'uber', label: 'Uber Cup', sub: "Women's team · 3 WS + 2 WD" },
  { key: 'sudirman', label: 'Sudirman Cup', sub: 'Mixed team · MS/WS/MD/WD/XD' },
]

function Team({ contributors }) {
  return (
    <div className="team-slots">
      {contributors.map((c, i) => (
        <span key={i} className="slot">
          <b>{c.event}</b>{' '}
          {c.players.map((p, j) => (
            <span key={p.player_id}>
              {j > 0 ? '/' : ''}
              <Link to={`/players/${p.player_id}`}>{p.name_display}</Link>
            </span>
          ))}
          <span className="muted"> {c.rating}</span>
        </span>
      ))}
    </div>
  )
}

export default function Cups() {
  const [cup, setCup] = useState('thomas')
  const { data, error, loading } = useAsync(() => api.cup(cup), [cup])
  const meta = CUPS.find((c) => c.key === cup)

  return (
    <div>
      <PageHeader
        kicker="National Team Power"
        title="Cup Power"
        subtitle={
          <>Which country could field the strongest team <strong>right now</strong> —
          summed rating of each nation's top active players/pairs. Retired players
          (idle &gt; 1 year) don't count.</>
        }
      />

      <div className="tabs">
        {CUPS.map((c) => (
          <button key={c.key}
            className={`tab ${c.key === cup ? 'active' : ''}`}
            onClick={() => setCup(c.key)}>
            {c.label.split(' ')[0]}
            <span className="tab-label">{c.label.split(' ')[1]}</span>
          </button>
        ))}
      </div>
      <p className="muted small" style={{ marginTop: 8 }}>{meta.sub}</p>

      {loading && <p className="muted">Loading…</p>}
      {error && <p className="error">Could not load: {error.message}</p>}
      {data && (
        <table className="board">
          <thead>
            <tr>
              <th className="rank">#</th>
              <th>Country</th>
              <th className="num">Power</th>
              <th>Team</th>
            </tr>
          </thead>
          <tbody>
            {data.results.slice(0, 30).map((row, i) => (
              <tr key={row.country}>
                <td className="rank">{i + 1}</td>
                <td className="strong">
                  <span className="fl">{flag(row.country)}</span> {row.country}
                </td>
                <td className="num"><span className="metric">{row.power.toLocaleString()}</span></td>
                <td><Team contributors={row.contributors} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data && data.results.length === 0 && (
        <p className="muted">No country can field a full team.</p>
      )}
    </div>
  )
}
