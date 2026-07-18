import { Fragment, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, EVENTS } from '../api.js'
import { useAsync } from '../useAsync.js'
import { flag } from '../flags.js'
import Pager from '../components/Pager.jsx'
import PageHeader from '../components/PageHeader.jsx'

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

function PathDetail({ row }) {
  const { data, loading, error } = useAsync(
    () => api.performancePath(row.player.player_id, row.event, row.tournament.tournament_id),
    [row.player.player_id, row.event, row.tournament.tournament_id],
  )
  if (loading) return <p className="muted small">Loading path…</p>
  if (error || !data?.matches?.length) return <p className="muted small">No match path.</p>
  return (
    <table className="board compact path-table">
      <tbody>
        {data.matches.map((m) => (
          <tr key={m.match_id}>
            <td className="rnd muted small">{m.round_name}</td>
            <td><span className={`wl ${m.won ? 'w' : 'l'}`}>{m.won ? 'W' : 'L'}</span></td>
            <td>{m.opponents.map((p) => p.name_display).join(' / ') || '—'}</td>
            <td className="score-cell">
              {m.score.map((g, i) => <span key={i}>{g[0]}-{g[1]} </span>)}
              {m.score_status !== 'Normal' && (
                <span className="muted small">({m.score_status})</span>
              )}
            </td>
            <td className="num">
              {m.elo_delta != null && (
                <span className={m.elo_delta >= 0 ? 'pos' : 'neg'}>
                  {m.elo_delta >= 0 ? '+' : ''}{m.elo_delta.toFixed(1)}
                </span>
              )}
            </td>
            <td className="muted small">
              {m.match_time_utc ? new Date(m.match_time_utc).toLocaleString() : '—'}
            </td>
            <td><Link to={`/matches/${m.match_id}`} className="muted small">view →</Link></td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function GainsTable({ kind, event, includeNew }) {
  const [page, setPage] = useState(0)
  const [open, setOpen] = useState(null)
  useEffect(() => { setPage(0); setOpen(null) }, [kind, event, includeNew])
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
        {shown.map((row, i) => {
          const rkey = `${row.player.player_id}-${row.tournament.tournament_id}-${row.event}`
          const isOpen = open === rkey
          return (
          <Fragment key={rkey}>
          <tr className="expandable"
              onClick={() => setOpen(isOpen ? null : rkey)}>
            <td className="rank">{page * PAGE + i + 1}</td>
            <td><span className="caret">{isOpen ? '▾' : '▸'}</span> <NameCell row={row} /></td>
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
              <Link to={`/tournaments/${row.tournament.tournament_id}`}
                    onClick={(e) => e.stopPropagation()}>
                {row.tournament.name}
              </Link>
            </td>
          </tr>
          {isOpen && (
            <tr className="expand-row">
              <td colSpan={6}>
                <div className="path-wrap">
                  <div className="muted small path-head">
                    {row.player.name_display}
                    {row.partner ? ` / ${row.partner.name_display}` : ''}'s run at{' '}
                    {row.tournament.name}
                  </div>
                  <PathDetail row={row} />
                </div>
              </td>
            </tr>
          )}
          </Fragment>
          )
        })}
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
      <PageHeader
        kicker="Analytics"
        title="Insights"
        subtitle="Standout runs and giant-killings across two decades of BWF results — ranked by how much they moved the needle."
      />
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
