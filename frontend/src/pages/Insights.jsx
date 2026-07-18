import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, EVENTS } from '../api.js'
import { useAsync } from '../useAsync.js'
import { flag } from '../flags.js'
import Pager from '../components/Pager.jsx'

const PAGE = 10

function Achievement({ label }) {
  if (!label) return null
  const cls = label === 'Champion' ? 'champ' : label === 'Runner-up' ? 'runner' : ''
  return <span className={`ach ${cls}`}>{label === 'Champion' ? '🏆 ' : ''}{label}</span>
}

function NameCell({ row }) {
  if (!row.player) return '—'
  return (
    <>
      <span className="fl">{flag(row.player.country_code)}</span>{' '}
      <Link to={`/players/${row.player.player_id}`}>{row.player.name_display}</Link>
      {row.partner && (
        <>
          {' / '}
          <Link to={`/players/${row.partner.player_id}`}>{row.partner.name_display}</Link>
        </>
      )}
      <span className="muted small"> {row.event}</span>
    </>
  )
}

function GainsTable({ kind, event, includeNew }) {
  const [page, setPage] = useState(0)
  useEffect(() => setPage(0), [kind, event, includeNew])
  const { data, error, loading } = useAsync(
    () => api.analytics(kind, { event, minMatches: 3, limit: 100, includeNew }),
    [kind, event, includeNew],
  )
  const isUpset = kind === 'upsets'
  const isPerf = kind === 'performances'
  if (loading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">Could not load: {error.message}</p>

  const metricHead = isUpset ? 'Gain' : isPerf ? 'Perf' : 'Net ELO'
  const shown = data.results.slice(page * PAGE, page * PAGE + PAGE)
  return (
    <>
    <table className="board">
      <thead>
        <tr>
          <th className="rank">#</th>
          <th>Player</th>
          <th className="num">{metricHead}</th>
          <th>Result</th>
          {isUpset ? <th>Beat (round)</th> : <th className="num">Start→End</th>}
          <th>Tournament</th>
        </tr>
      </thead>
      <tbody>
        {shown.map((row, i) => (
          <tr key={`${row.player.player_id}-${row.tournament.tournament_id}-${row.event}`}>
            <td className="rank">{page * PAGE + i + 1}</td>
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
              ) : isPerf ? (
                <span className="metric">{Math.round(row.perf_rating)}</span>
              ) : (
                <span className={row.net_delta >= 0 ? 'pos' : 'neg'}>
                  {row.net_delta >= 0 ? '+' : ''}
                  {row.net_delta.toFixed(1)}
                </span>
              )}
            </td>
            <td><Achievement label={row.achievement} /></td>
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
    <Pager page={page} setPage={setPage} count={data.results.length} pageSize={PAGE} />
    </>
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

      <h2>🎯 Best tournament performances</h2>
      <p className="muted small">Chess-style performance rating — the level a
        player/pair played AT across a tournament, based on the strength of the
        opponents they beat. Winning against a brutal field beats an easy title.</p>
      <GainsTable kind="performances" event={event} includeNew={includeNew} />
    </div>
  )
}
