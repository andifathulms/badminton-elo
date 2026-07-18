import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, EVENTS } from '../api.js'
import { useAsync } from '../useAsync.js'

function NameCell({ row }) {
  if (!row.player) return '—'
  return (
    <>
      <Link to={`/players/${row.player.player_id}`}>{row.player.name_display}</Link>
      {row.partner && (
        <>
          {' / '}
          <Link to={`/players/${row.partner.player_id}`}>{row.partner.name_display}</Link>
        </>
      )}
      <span className="muted small"> {row.event} · {row.player.country_code}</span>
    </>
  )
}

function GainsTable({ kind, event, includeNew }) {
  const { data, error, loading } = useAsync(
    () => api.analytics(kind, { event, minMatches: 3, limit: 40, includeNew }),
    [kind, event, includeNew],
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
          <th className="num">{isUpset ? 'Gain' : 'Net ELO'}</th>
          {isUpset ? <th>Beat (round)</th> : <th className="num">Start→End</th>}
          <th>Tournament</th>
        </tr>
      </thead>
      <tbody>
        {data.results.map((row, i) => (
          <tr key={`${row.player.player_id}-${row.tournament.tournament_id}-${row.event}`}>
            <td className="rank">{i + 1}</td>
            <td><NameCell row={row} /></td>
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
            {isUpset ? (
              <td className="small">
                {(row.beat || []).map((p) => p.name_display).join(' / ') || '—'}
                {row.best_round && <span className="muted"> · {row.best_round}</span>}
              </td>
            ) : (
              <td className="num muted small">
                {Math.round(row.mu_start)}→{Math.round(row.mu_end)}
              </td>
            )}
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
  const [includeNew, setIncludeNew] = useState(false)

  return (
    <div>
      <div className="page-head">
        <div className="kicker">Analytics</div>
        <h1 className="page-title">Insights</h1>
        <p className="page-sub">
          Standout runs and giant-killings across two decades of BWF results —
          ranked by how much they moved the needle.
        </p>
      </div>
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
        <label className="checkbox">
          <input type="checkbox" checked={includeNew}
                 onChange={(e) => setIncludeNew(e.target.checked)} />
          {' '}include debut players
        </label>
      </div>

      <h2>🚀 Biggest tournament breakouts</h2>
      <p className="muted small">Most ELO gained by an <strong>established</strong>{' '}
        player across a single tournament — the standout runs. (Start→End is the
        rating before and after; debut players are hidden by default since a
        first-timer's rating swings hugely.)</p>
      <GainsTable kind="tournament-gains" event={event} includeNew={includeNew} />

      <h2>⚡ Biggest upsets</h2>
      <p className="muted small">The single wins that moved a rating the most —
        beating someone you weren't supposed to.</p>
      <GainsTable kind="upsets" event={event} includeNew={includeNew} />
    </div>
  )
}
