import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, EVENTS } from '../api.js'
import { useAsync } from '../useAsync.js'

const pair = (row) =>
  row.player ? row.player.name_display : '—'

function GainsTable({ kind, event }) {
  const { data, error, loading } = useAsync(
    () => api.analytics(kind, { event, minMatches: 3, limit: 40 }),
    [kind, event],
  )
  const isUpset = kind === 'upsets'
  if (loading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">Could not load: {error.message}</p>

  return (
    <table className="board">
      <thead>
        <tr>
          <th>#</th>
          <th>Player</th>
          <th className="num">{isUpset ? 'Best win' : 'Net ELO'}</th>
          <th className="num">{isUpset ? 'M' : 'Start→End'}</th>
          <th>Tournament</th>
        </tr>
      </thead>
      <tbody>
        {data.results.map((row, i) => (
          <tr key={`${row.player.player_id}-${row.tournament.tournament_id}-${row.event}`}>
            <td className="rank">{i + 1}</td>
            <td>
              <Link to={`/players/${row.player.player_id}`}>{pair(row)}</Link>
              <span className="muted small"> {row.event} · {row.player.country_code}</span>
            </td>
            <td className="num strong">
              {isUpset ? (
                row.best_match ? (
                  <Link to={`/matches/${row.best_match}`} className="pos">
                    +{row.best_delta.toFixed(1)}
                  </Link>
                ) : (
                  <span className="pos">+{row.best_delta.toFixed(1)}</span>
                )
              ) : (
                <span className={row.net_delta >= 0 ? 'pos' : 'neg'}>
                  {row.net_delta >= 0 ? '+' : ''}
                  {row.net_delta.toFixed(1)}
                </span>
              )}
            </td>
            <td className="num muted small">
              {isUpset ? row.matches : `${Math.round(row.mu_start)}→${Math.round(row.mu_end)}`}
            </td>
            <td className="muted small">
              <Link to={`/tournaments/${row.tournament.tournament_id}`}>
                {row.tournament.name}
              </Link>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function Insights() {
  const [event, setEvent] = useState('')

  return (
    <div>
      <h1 className="page-title">Insights</h1>
      <div className="toolbar wrap">
        <div className="segmented">
          <button className={event === '' ? 'seg active' : 'seg'}
                  onClick={() => setEvent('')}>All</button>
          {EVENTS.map((e) => (
            <button key={e.code}
              className={event === e.code ? 'seg active' : 'seg'}
              onClick={() => setEvent(e.code)}>{e.code}</button>
          ))}
        </div>
      </div>

      <h2>🚀 Biggest tournament breakouts</h2>
      <p className="muted small">Most ELO gained across a single tournament — the
        standout runs. (Start→End is the rating before and after.)</p>
      <GainsTable kind="tournament-gains" event={event} />

      <h2>⚡ Biggest upsets</h2>
      <p className="muted small">The single wins that moved a rating the most —
        beating someone you weren't supposed to.</p>
      <GainsTable kind="upsets" event={event} />
    </div>
  )
}
