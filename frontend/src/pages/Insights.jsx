import { Fragment, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, EVENTS } from '../api.js'
import { useAsync } from '../useAsync.js'
import { flag } from '../flags.js'
import Pager from '../components/Pager.jsx'
import PageHeader from '../components/PageHeader.jsx'
import UpsetsTable from '../components/UpsetsTable.jsx'
import Entity from '../components/Entity.jsx'
import ReliabilityChart from '../components/ReliabilityChart.jsx'
import AgeCurveChart from '../components/AgeCurveChart.jsx'
import DynastyTimeline from '../components/DynastyTimeline.jsx'

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

function CalibrationSection({ event }) {
  const { data, error, loading } = useAsync(
    () => api.calibration(event || 'ALL'), [event])
  if (loading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">Could not load: {error.message}</p>
  if (!data.n) return <p className="muted">No calibration data for this filter yet.</p>
  return (
    <div>
      <div className="statgrid">
        <div className="statcard">
          <div className="k">Accuracy</div>
          <div className="v">{(data.accuracy * 100).toFixed(1)}%</div>
          <div className="sub">favorite wins</div>
        </div>
        <div className="statcard">
          <div className="k">Calibration error</div>
          <div className="v">{(data.calibration_error * 100).toFixed(1)}%</div>
          <div className="sub">mean |predicted − actual|</div>
        </div>
        <div className="statcard">
          <div className="k">Matches</div>
          <div className="v">{data.n.toLocaleString()}</div>
          <div className="sub">rated, decisive</div>
        </div>
      </div>
      <ReliabilityChart bins={data.bins} />
      <table className="board compact">
        <thead>
          <tr>
            <th>Predicted band</th>
            <th className="num">Predicted</th>
            <th className="num">Actual</th>
            <th className="num">Matches</th>
          </tr>
        </thead>
        <tbody>
          {data.bins.filter((b) => b.n).map((b) => (
            <tr key={b.bucket}>
              <td>{Math.round(b.lo * 100)}–{Math.round(b.hi * 100)}%</td>
              <td className="num">{(b.predicted * 100).toFixed(1)}%</td>
              <td className="num strong">{(b.actual * 100).toFixed(1)}%</td>
              <td className="num muted">{b.n.toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function AgingSection({ event }) {
  const { data, error, loading } = useAsync(() => api.aging(event || ''), [event])
  if (loading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">Could not load: {error.message}</p>
  if (!data.n) return <p className="muted">No age data for this filter yet.</p>
  return (
    <div>
      <div className="statgrid">
        <div className="statcard">
          <div className="k">Median peak age</div>
          <div className="v">{data.median_peak_age}</div>
          <div className="sub">half peak younger</div>
        </div>
        <div className="statcard">
          <div className="k">Mean peak age</div>
          <div className="v">{data.mean_peak_age}</div>
          <div className="sub">{data.n.toLocaleString()} players</div>
        </div>
      </div>
      <AgeCurveChart bins={data.bins} medianAge={data.median_peak_age} />
      <h2>Latest to peak</h2>
      <table className="board compact">
        <thead>
          <tr>
            <th>Player</th>
            <th className="num">Peak age</th>
            <th className="num">Peak</th>
            <th>Event</th>
          </tr>
        </thead>
        <tbody>
          {[...data.peakers].sort((a, b) => b.peak_age - a.peak_age).map((p) => (
            <tr key={`${p.player.player_id}-${p.event}`}>
              <td>
                <span className="fl">{flag(p.player.country_code)}</span>{' '}
                <Link to={`/players/${p.player.player_id}`}>{p.player.name_display}</Link>
              </td>
              <td className="num strong">{p.peak_age}</td>
              <td className="num">{Math.round(p.peak_mu)}</td>
              <td className="muted small">{p.event}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">Top-10 highest peaks in this filter, ordered by the age they hit it.</p>
    </div>
  )
}

function ClutchSection({ event }) {
  const [order, setOrder] = useState('pct')
  const { data, error, loading } = useAsync(
    () => api.clutch(event, { min: 15, order }), [event, order])
  if (loading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">Could not load: {error.message}</p>
  if (!data.results.length) return <p className="muted">No clutch data for this filter yet.</p>
  return (
    <div>
      <div className="tabs mini-tabs">
        <button className={`tab ${order === 'pct' ? 'active' : ''}`}
                onClick={() => setOrder('pct')}>Best win %</button>
        <button className={`tab ${order === 'played' ? 'active' : ''}`}
                onClick={() => setOrder('played')}>Most deciders</button>
      </div>
      <table className="board">
        <thead>
          <tr>
            <th className="rank">#</th>
            <th>Player</th>
            <th className="num">3rd-game W%</th>
            <th className="num">Deciders</th>
            <th className="num">Overall W%</th>
          </tr>
        </thead>
        <tbody>
          {data.results.map((r, i) => (
            <tr key={r.player.player_id}>
              <td className="rank">{i + 1}</td>
              <td>
                <span className="fl">{flag(r.player.country_code)}</span>{' '}
                <Link to={`/players/${r.player.player_id}`}>{r.player.name_display}</Link>
              </td>
              <td className="num strong">
                <span className="metric">{r.decider_pct}%</span>
              </td>
              <td className="num muted small">{r.deciders_won}/{r.deciders_played}</td>
              <td className="num muted small">{r.overall_pct != null ? `${r.overall_pct}%` : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">
        Deciding game = a match that went to a third game (Normal matches only).
        Minimum 15 deciders to rank.
      </p>
    </div>
  )
}

function DynastiesSection({ event }) {
  const { data, error, loading } = useAsync(() => api.dynasties(event), [event])
  if (loading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">Could not load: {error.message}</p>
  if (!data.timeline.length) return <p className="muted">No dynasty data for this filter yet.</p>
  const current = data.timeline[data.timeline.length - 1]
  return (
    <div>
      <DynastyTimeline reigns={data.reigns} timeline={data.timeline} />
      <div className="dyn-grids">
        <div>
          <h2>Longest reigns</h2>
          <table className="board compact">
            <thead>
              <tr><th>Nation</th><th>Era</th><th className="num">Years</th></tr>
            </thead>
            <tbody>
              {data.reigns.slice(0, 8).map((r, i) => (
                <tr key={i}>
                  <td><span className="fl">{flag(r.country)}</span> {r.country}</td>
                  <td className="muted small">{r.start}{r.end !== r.start ? `–${r.end}` : ''}</td>
                  <td className="num strong">{r.span}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          <h2>Most years at #1</h2>
          <table className="board compact">
            <thead>
              <tr><th>Nation</th><th className="num">Years #1</th></tr>
            </thead>
            <tbody>
              {data.totals.slice(0, 8).map((t) => (
                <tr key={t.country}>
                  <td><span className="fl">{flag(t.country)}</span> {t.country}</td>
                  <td className="num strong">{t.years}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <p className="muted small">
        Current #1: <span className="fl">{flag(current.country)}</span>{' '}
        <strong>{current.country}</strong> ({current.year}). #1 = highest summed
        top-3 rating that year.
      </p>
    </div>
  )
}

function ConsistencySection({ event }) {
  const [order, setOrder] = useState('steady')
  const { data, error, loading } = useAsync(
    () => api.consistency(event, { min: 40, order }), [event, order])
  if (loading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">Could not load: {error.message}</p>
  if (!data.results.length) return <p className="muted">No consistency data for this filter yet.</p>
  return (
    <div>
      <div className="tabs mini-tabs">
        <button className={`tab ${order === 'steady' ? 'active' : ''}`}
                onClick={() => setOrder('steady')}>🧊 Steadiest</button>
        <button className={`tab ${order === 'volatile' ? 'active' : ''}`}
                onClick={() => setOrder('volatile')}>🎲 Most volatile</button>
      </div>
      <table className="board">
        <thead>
          <tr>
            <th className="rank">#</th>
            <th>Player</th>
            <th className="num">Volatility</th>
            <th className="num">Rating</th>
            <th className="num">Matches</th>
          </tr>
        </thead>
        <tbody>
          {data.results.map((r, i) => (
            <tr key={r.player.player_id}>
              <td className="rank">{i + 1}</td>
              <td>
                <span className="fl">{flag(r.player.country_code)}</span>{' '}
                <Link to={`/players/${r.player.player_id}`}>{r.player.name_display}</Link>
              </td>
              <td className="num strong"><span className="metric">±{r.volatility}</span></td>
              <td className="num muted small">{r.rating.toFixed(0)}</td>
              <td className="num muted small">{r.matches_played}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">
        Volatility = standard deviation of a player’s per-match rating change
        (points). Low = steady, predictable form; high = big swings. Minimum 40
        matches.
      </p>
    </div>
  )
}

function SynergySection({ event }) {
  const [order, setOrder] = useState('best')
  const { data, error, loading } = useAsync(
    () => api.synergy(event, { min: 20, order }), [event, order])
  if (loading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">Could not load: {error.message}</p>
  if (!data.results.length) return <p className="muted">No synergy data for this filter yet.</p>
  return (
    <div>
      <div className="tabs mini-tabs">
        <button className={`tab ${order === 'best' ? 'active' : ''}`}
                onClick={() => setOrder('best')}>🤝 Best chemistry</button>
        <button className={`tab ${order === 'worst' ? 'active' : ''}`}
                onClick={() => setOrder('worst')}>💔 Underperformers</button>
      </div>
      <table className="board">
        <thead>
          <tr>
            <th className="rank">#</th>
            <th>Pair</th>
            <th className="num">Synergy</th>
            <th className="num">Perf</th>
            <th className="num">Combined</th>
            <th className="num">Together</th>
          </tr>
        </thead>
        <tbody>
          {data.results.map((r, i) => (
            <tr key={r.players.map((p) => p.player_id).join('-')}>
              <td className="rank">{i + 1}</td>
              <td><Entity players={r.players} event={event} /></td>
              <td className="num strong">
                <span className={r.synergy >= 0 ? 'pos' : 'neg'}>
                  {r.synergy >= 0 ? '+' : ''}{r.synergy}
                </span>
              </td>
              <td className="num muted small">{r.perf_rating}</td>
              <td className="num muted small">{r.combined_mu}</td>
              <td className="num muted small">{r.wins_together}/{r.matches_together}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">
        Synergy = the pair’s performance rating (from their own results vs the
        fields they faced) minus their combined member rating. Positive = they
        punch above the sum of their parts. Minimum 20 matches together.
      </p>
    </div>
  )
}

// Groups organise the landing into scannable sections (see GROUPS below).
const INSIGHTS = [
  { key: 'breakouts', icon: '🚀', title: 'Biggest tournament breakouts', group: 'runs',
    blurb: 'Most ELO gained by an established player across a single tournament — the standout runs.',
    sub: 'Most ELO gained by an established player across a single tournament. Start→End is the rating before and after; debut players are hidden by default since a first-timer\'s rating swings hugely.',
    toolbar: true },
  { key: 'upsets', icon: '⚡', title: 'Biggest upsets', group: 'runs',
    blurb: "The single wins that moved a rating the most — beating someone you weren't supposed to.",
    sub: "The single wins that moved a rating the most — beating someone you weren't supposed to. Click a row to open the match.",
    toolbar: true },
  { key: 'performances', icon: '🎯', title: 'Best tournament performances', group: 'runs',
    blurb: 'The level a player/pair actually played at, based on the strength of the field they beat.',
    sub: 'Chess-style performance rating — the level a player/pair played AT across a tournament, based on the strength of the opponents they beat. Walkovers and retirements don\'t count — only contested wins vs a rated opponent (open a row to see the run).',
    toolbar: true },
  { key: 'consistency', icon: '🧊', title: 'Consistency', group: 'players',
    blurb: 'The steadiest performers vs the most volatile — measured by how much a rating swings match to match.',
    sub: 'Form volatility: the standard deviation of a player’s per-match rating change. Low means predictable (results match their level); high means erratic (big upsets and bad losses). Toggle steadiest vs most volatile; pick a discipline.',
    toolbar: 'event-req' },
  { key: 'aging', icon: '📈', title: 'When players peak', group: 'players',
    blurb: 'The age players reach their career-best rating — and how peak level rises then fades with age.',
    sub: 'Each rated player’s career peak placed on an age axis. Bars show how many players peaked at each age; the line is the average peak rating reached. Most players peak young (they don’t last), but the highest ratings come later. Pick a discipline to compare.',
    toolbar: 'event' },
  { key: 'synergy', icon: '🤝', title: 'Partnership synergy', group: 'teams',
    blurb: 'Which doubles pairs overperform the sum of their parts — real on-court chemistry, and the duos that never gelled.',
    sub: 'Synergy = a pair’s performance rating (from their own results) minus their combined individual rating. Positive means they’re better together than their solo levels predict. Toggle best chemistry vs underperformers; pick a doubles discipline.',
    toolbar: 'doubles' },
  { key: 'dynasties', icon: '👑', title: 'Nation dynasties', group: 'teams',
    blurb: 'Which country ruled each discipline, and for how long — dominance eras from four decades of results.',
    sub: 'The #1 nation in a discipline each year (by summed top-3 player rating), and the reigns those years form. Pick a discipline to trace its dynasties.',
    toolbar: 'event-req' },
  { key: 'clutch', icon: '🔥', title: 'Clutch: deciding games', group: 'matchplay',
    blurb: 'Who wins the matches that go the distance — third-game win rate across a discipline.',
    sub: 'When a match reaches a deciding third game, who comes out on top? Ranked by third-game win rate (Normal matches only, minimum 15 deciders). Pick a discipline.',
    toolbar: 'event-req' },
  { key: 'records', icon: '🏟️', title: 'Match records', group: 'matchplay',
    blurb: 'Longest matches, most rallies, and biggest comebacks — from rally-by-rally stats.',
    sub: 'Extremes pulled from the rally-by-rally match statistics — only matches we\'ve collected point-by-point data for.',
    toolbar: false },
  { key: 'accuracy', icon: '🎯', title: 'Rating accuracy', group: 'model',
    blurb: 'How often the higher-rated side actually wins — and whether the model’s confidence matches reality.',
    sub: 'A reliability check: every rated match bucketed by the favorite’s pre-match win probability, versus how often that favorite actually won. Points on the diagonal mean the rating is well-calibrated. Pick a discipline to filter.',
    toolbar: 'event' },
]

// Ordered sections for the landing. Each card's `group` maps to one of these.
const GROUPS = [
  { id: 'runs', label: 'Standout runs', hint: 'The biggest gains, upsets, and tournament performances.' },
  { id: 'players', label: 'Players', hint: 'Career shape and match-to-match form.' },
  { id: 'teams', label: 'Pairs & nations', hint: 'Doubles chemistry and national dominance eras.' },
  { id: 'matchplay', label: 'Match play', hint: 'What happens inside the matches themselves.' },
  { id: 'model', label: 'The rating model', hint: 'How trustworthy the numbers are.' },
]

function Toolbar({ event, setEvent, includeNew, setIncludeNew, showDebut = true, allowAll = true, codes }) {
  const list = codes || EVENTS.map((e) => e.code)
  return (
    <div className="toolbar wrap">
      <div className="segmented">
        {allowAll && (
          <button className={event === '' ? 'seg active' : 'seg'}
                  onClick={() => setEvent('')}>All</button>
        )}
        {list.map((code) => (
          <button key={code}
            className={event === code ? 'seg active' : 'seg'}
            onClick={() => setEvent(code)}>{code}</button>
        ))}
      </div>
      {showDebut && (
        <label className="checkbox">
          <input type="checkbox" checked={includeNew}
                 onChange={(e) => setIncludeNew(e.target.checked)} />
          {' '}include debut players
        </label>
      )}
    </div>
  )
}

export default function Insights() {
  const [view, setView] = useState(null)
  const [event, setEvent] = useState('')
  const [includeNew, setIncludeNew] = useState(false)
  const active = INSIGHTS.find((i) => i.key === view)

  // Cards that require a specific discipline can't use the "All" bucket.
  useEffect(() => {
    if (active?.toolbar === 'event-req' && event === '') setEvent('MS')
    if (active?.toolbar === 'doubles' && !['MD', 'WD', 'XD'].includes(event)) setEvent('MD')
  }, [active, event])

  if (!active) {
    return (
      <div>
        <PageHeader
          kicker="Analytics"
          title="Insights"
          subtitle="Standout runs and giant-killings, how accurate the ratings actually are, when players peak, and who wins the tight ones — across two decades of BWF results. Pick a lens to dig in."
        />
        {GROUPS.map((g) => {
          const cards = INSIGHTS.filter((i) => i.group === g.id)
          if (!cards.length) return null
          return (
            <section key={g.id} className="insight-group">
              <div className="insight-group-head">
                <h2>{g.label}</h2>
                <span className="muted small">{g.hint}</span>
              </div>
              <div className="insight-cards">
                {cards.map((i) => (
                  <button key={i.key} className="insight-card" onClick={() => setView(i.key)}>
                    <span className="insight-icon">{i.icon}</span>
                    <span className="insight-title">{i.title}</span>
                    <span className="insight-desc">{i.blurb}</span>
                    <span className="insight-go">Explore →</span>
                  </button>
                ))}
              </div>
            </section>
          )
        })}
      </div>
    )
  }

  return (
    <div>
      <button className="back" onClick={() => setView(null)}>← All insights</button>
      <PageHeader kicker="Analytics" title={`${active.icon} ${active.title}`} subtitle={active.sub} />
      {active.toolbar && (
        <Toolbar event={event} setEvent={setEvent}
                 includeNew={includeNew} setIncludeNew={setIncludeNew}
                 showDebut={active.toolbar === true}
                 allowAll={active.toolbar === true || active.toolbar === 'event'}
                 codes={active.toolbar === 'doubles' ? ['MD', 'WD', 'XD'] : undefined} />
      )}
      {view === 'accuracy' && <CalibrationSection event={event} />}
      {view === 'aging' && <AgingSection event={event} />}
      {view === 'clutch' && <ClutchSection event={event || 'MS'} />}
      {view === 'dynasties' && <DynastiesSection event={event || 'MS'} />}
      {view === 'consistency' && <ConsistencySection event={event || 'MS'} />}
      {view === 'synergy' && <SynergySection event={['MD', 'WD', 'XD'].includes(event) ? event : 'MD'} />}
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
