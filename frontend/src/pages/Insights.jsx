import { Fragment, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, EVENTS } from '../api.js'
import { useAsync } from '../useAsync.js'
import { flag } from '../flags.js'
import Pager from '../components/Pager.jsx'
import PageHeader from '../components/PageHeader.jsx'
import UpsetsTable from '../components/UpsetsTable.jsx'

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

// Biggest upsets — same table as the dashboard, paginated. Each row links to
// its match.
function UpsetsSection({ event, includeNew }) {
  const [page, setPage] = useState(0)
  useEffect(() => { setPage(0) }, [event, includeNew])
  const { data, error, loading } = useAsync(
    () => api.analytics('upsets', { event, minMatches: 3, limit: 100, includeNew }),
    [event, includeNew],
  )
  if (loading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">Could not load: {error.message}</p>
  const shown = data.results.slice(page * PAGE, page * PAGE + PAGE)
  return (
    <>
      <UpsetsTable rows={shown} />
      <Pager page={page} setPage={setPage} count={data.results.length} pageSize={PAGE} />
    </>
  )
}

const RECORD_TABS = [
  { kind: 'longest', label: '⏱️ Longest matches', unit: 'min', field: 'duration_min' },
  { kind: 'rallies', label: '🏸 Most rallies', unit: 'rallies', field: 'rallies' },
  { kind: 'comebacks', label: '🔥 Biggest comebacks', unit: 'pts down', field: 'max_comeback' },
]

function Side({ players, win }) {
  return (
    <span className={win ? 'strong' : ''}>
      {players.map((p, i) => (
        <span key={p.player_id}>
          {i > 0 ? ' / ' : ''}
          <span className="fl">{flag(p.country_code)}</span>{' '}
          <Link to={`/players/${p.player_id}`}>{p.name_display}</Link>
        </span>
      ))}
    </span>
  )
}

function RecordsSection({ event }) {
  const [kind, setKind] = useState('longest')
  const tab = RECORD_TABS.find((t) => t.kind === kind)
  const { data, error, loading } = useAsync(
    () => api.records(kind, { event, limit: 25 }), [kind, event])

  return (
    <div>
      <div className="tabs mini-tabs">
        {RECORD_TABS.map((t) => (
          <button key={t.kind}
            className={`tab ${t.kind === kind ? 'active' : ''}`}
            onClick={() => setKind(t.kind)}>{t.label}</button>
        ))}
      </div>
      {kind === 'comebacks' && (
        <p className="muted small">Biggest points deficit a side clawed back to{' '}
          <strong>win a game</strong> (e.g. 10 = down 10-20, won 22-20).</p>
      )}
      {loading && <p className="muted">Loading…</p>}
      {error && <p className="error">Could not load: {error.message}</p>}
      {data && (
        <table className="board">
          <thead>
            <tr>
              <th className="rank">#</th>
              <th className="num">{tab.unit === 'min' ? 'Min' : tab.unit === 'rallies' ? 'Rallies' : 'Comeback'}</th>
              <th>Matchup</th>
              <th className="score-cell">Score</th>
              <th>Tournament</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data.results.map((m, i) => {
              const s1win = m.winner_side === 1
              return (
                <tr key={m.match_id}>
                  <td className="rank">{i + 1}</td>
                  <td className="num strong">
                    <span className="metric">{m.value}</span>
                    {kind === 'comebacks' && <span className="muted small"> down</span>}
                  </td>
                  <td>
                    <Side players={m.side1} win={s1win} />
                    <span className="muted"> vs </span>
                    <Side players={m.side2} win={!s1win} />
                    <span className="muted small"> {m.event} · {m.round_name}</span>
                  </td>
                  <td className="score-cell">
                    {m.score.map((g, j) => <span key={j}>{g[0]}-{g[1]} </span>)}
                  </td>
                  <td className="muted small">
                    <Link to={`/tournaments/${m.tournament.id}`}>{m.tournament.name}</Link>
                  </td>
                  <td><Link to={`/matches/${m.match_id}`} className="muted small">view →</Link></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
      {data && !data.results.length && (
        <p className="muted">No matches with stats for this filter yet.</p>
      )}
    </div>
  )
}

const INSIGHTS = [
  { key: 'breakouts', icon: '🚀', title: 'Biggest tournament breakouts',
    blurb: 'Most ELO gained by an established player across a single tournament — the standout runs.',
    sub: 'Most ELO gained by an established player across a single tournament. Start→End is the rating before and after; debut players are hidden by default since a first-timer\'s rating swings hugely.',
    toolbar: true },
  { key: 'upsets', icon: '⚡', title: 'Biggest upsets',
    blurb: "The single wins that moved a rating the most — beating someone you weren't supposed to.",
    sub: "The single wins that moved a rating the most — beating someone you weren't supposed to. Click a row to open the match.",
    toolbar: true },
  { key: 'performances', icon: '🎯', title: 'Best tournament performances',
    blurb: 'The level a player/pair actually played at, based on the strength of the field they beat.',
    sub: 'Chess-style performance rating — the level a player/pair played AT across a tournament, based on the strength of the opponents they beat. Walkovers and retirements don\'t count — only contested wins vs a rated opponent (open a row to see the run).',
    toolbar: true },
  { key: 'records', icon: '🏟️', title: 'Match records',
    blurb: 'Longest matches, most rallies, and biggest comebacks — from rally-by-rally stats.',
    sub: 'Extremes pulled from the rally-by-rally match statistics — only matches we\'ve collected point-by-point data for.',
    toolbar: false },
]

function Toolbar({ event, setEvent, includeNew, setIncludeNew }) {
  return (
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
  )
}

export default function Insights() {
  const [view, setView] = useState(null)
  const [event, setEvent] = useState('')
  const [includeNew, setIncludeNew] = useState(false)
  const active = INSIGHTS.find((i) => i.key === view)

  if (!active) {
    return (
      <div>
        <PageHeader
          kicker="Analytics"
          title="Insights"
          subtitle="Standout runs and giant-killings across two decades of BWF results. Pick a lens to dig in."
        />
        <div className="insight-cards">
          {INSIGHTS.map((i) => (
            <button key={i.key} className="insight-card" onClick={() => setView(i.key)}>
              <span className="insight-icon">{i.icon}</span>
              <span className="insight-title">{i.title}</span>
              <span className="insight-desc">{i.blurb}</span>
              <span className="insight-go">Explore →</span>
            </button>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div>
      <button className="back" onClick={() => setView(null)}>← All insights</button>
      <PageHeader kicker="Analytics" title={`${active.icon} ${active.title}`} subtitle={active.sub} />
      {active.toolbar && (
        <Toolbar event={event} setEvent={setEvent}
                 includeNew={includeNew} setIncludeNew={setIncludeNew} />
      )}
      {view === 'breakouts' && (
        <GainsTable kind="tournament-gains" event={event} includeNew={includeNew} />
      )}
      {view === 'upsets' && <UpsetsSection event={event} includeNew={includeNew} />}
      {view === 'performances' && (
        <GainsTable kind="performances" event={event} includeNew={includeNew} />
      )}
      {view === 'records' && <RecordsSection event={event} />}
    </div>
  )
}
