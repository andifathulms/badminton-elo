import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, EVENTS } from '../api.js'
import { useAsync } from '../useAsync.js'
import Avatar from '../components/Avatar.jsx'
import Sparkline from '../components/Sparkline.jsx'
import Confidence from '../components/Confidence.jsx'
import Icon from '../components/Icon.jsx'
import { Move } from '../components/Chips.jsx'
import { Skeleton, SkeletonList } from '../components/Skeleton.jsx'
import { EmptyState, ErrorState } from '../components/Empty.jsx'
import { uncertainty } from '../confidence.js'
import { flag } from '../flags.js'
import { fmtMonth } from '../dates.js'

const isDoubles = (e) => e === 'MD' || e === 'WD' || e === 'XD'
const PAGE = 25
const CAP = 250
const eventLabel = (code) => EVENTS.find((e) => e.code === code)?.label || code
const fmt = (n) => Math.round(n).toLocaleString()

function Medal({ n }) {
  return <span className={`medal ${n <= 3 ? `m${n}` : ''}`}>{n}</span>
}

function HowRatingsWork() {
  return (
    <details className="how">
      <summary><Icon name="info" size={15} /> How ratings work</summary>
      <div className="how-body">
        <p><b>Rating</b> is the number players are ranked by. It's a cautious estimate: the engine's best guess of a player's skill, minus twice its uncertainty, so a player can't top the table on a lucky handful of results.</p>
        <p><b>Skill ± certainty</b> shows that best guess and how sure it is. Three green bars mean settled; amber means still firming up; one grey bar means provisional (new or long inactive).</p>
        <p><b>Arrows</b> show rank movement over the last 4 weeks. Ratings change on who you beat, not on points or rounds reached. The maths is Glicko-2, with doubles rated through each partner.</p>
      </div>
    </details>
  )
}

function Pager({ page, setPage, count }) {
  const pages = Math.min(Math.ceil(count / PAGE), CAP / PAGE)
  if (pages <= 1) return null
  return (
    <div className="pager">
      <button className="pgbtn" disabled={page <= 0} onClick={() => setPage(page - 1)}><Icon name="arrowLeft" size={14} /> Prev</button>
      <span className="muted small">Ranks {page * PAGE + 1}–{Math.min((page + 1) * PAGE, count)} of {count.toLocaleString()}</span>
      <button className="pgbtn" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>Next <Icon name="arrowRight" size={14} /></button>
    </div>
  )
}

export default function Leaderboard() {
  const [params, setParams] = useSearchParams()
  const event = EVENTS.some((e) => e.code === params.get('event')) ? params.get('event') : 'MS'
  const ranking = params.get('ranking') === 'peak' ? 'peak' : 'current'
  const doubles = isDoubles(event)
  const mode = doubles && params.get('view') === 'pairs' ? 'pairs' : 'individual'
  const gender = event === 'XD' && mode === 'individual' && ['M', 'F'].includes(params.get('gender')) ? params.get('gender') : ''
  const order = params.get('order') === 'mu' ? 'mu' : 'rating'
  const page = Math.max(0, parseInt(params.get('page') || '0', 10) || 0)

  // Keep everything in the URL so a board is shareable and Back works.
  function set(next) {
    const merged = { event, ranking, view: mode === 'pairs' ? 'pairs' : '', gender, order, page: 0, ...next }
    const out = {}
    if (merged.event !== 'MS') out.event = merged.event
    if (merged.ranking === 'peak') out.ranking = 'peak'
    if (merged.view === 'pairs') out.view = 'pairs'
    if (merged.gender) out.gender = merged.gender
    if (merged.order === 'mu') out.order = 'mu'
    if (merged.page) out.page = String(merged.page)
    setParams(out, { replace: false })
  }

  return (
    <div className="rankings">
      <header className="phead">
        <div className="phead-text">
          <div className="crumb"><span>Rankings</span><span className="sep">/</span><span>{ranking === 'peak' ? 'All-time peak' : 'Current'}</span></div>
          <h1>{eventLabel(event)}</h1>
        </div>
        <div className="phead-aside">
          <div className="tabs" role="tablist" aria-label="Discipline">
            {EVENTS.map((e) => (
              <button key={e.code} role="tab" aria-selected={e.code === event} title={e.label}
                className={`tab ${e.code === event ? 'active' : ''}`}
                onClick={() => set({ event: e.code, view: '', gender: '' })}>{e.code}</button>
            ))}
          </div>
          <div className="segmented">
            <button className={`seg ${ranking === 'current' ? 'active' : ''}`} onClick={() => set({ ranking: 'current' })}>Current</button>
            <button className={`seg ${ranking === 'peak' ? 'active' : ''}`} onClick={() => set({ ranking: 'peak' })}>All-time peak</button>
          </div>
        </div>
      </header>

      <div className="rk-sub">
        {(doubles || event === 'XD') && (
          <div className="rk-filters">
            {doubles && (
              <div className="segmented">
                <button className={`seg ${mode === 'individual' ? 'active' : ''}`} onClick={() => set({ view: '' })}>Players</button>
                <button className={`seg ${mode === 'pairs' ? 'active' : ''}`} onClick={() => set({ view: 'pairs', gender: '' })}>Pairs</button>
              </div>
            )}
            {event === 'XD' && mode === 'individual' && (
              <div className="segmented">
                {[['', 'All'], ['M', 'Men'], ['F', 'Women']].map(([g, l]) => (
                  <button key={g || 'all'} className={`seg ${gender === g ? 'active' : ''}`} onClick={() => set({ gender: g })}>{l}</button>
                ))}
              </div>
            )}
          </div>
        )}
        <HowRatingsWork />
      </div>

      {mode === 'pairs' ? (
        <PairsBoard key={`${event}-${ranking}-${page}`} event={event} ranking={ranking} page={page} setPage={(p) => set({ page: p })} />
      ) : (
        <IndividualBoard key={`${event}-${ranking}-${order}-${gender}-${page}`} event={event} ranking={ranking}
          order={order} gender={gender} page={page}
          setOrder={(o) => set({ order: o })} setPage={(p) => set({ page: p })} />
      )}
    </div>
  )
}

// All-time values: the smoothed history engine's best when present (it judges
// a past peak with results from before AND after it), else the live peak.
const bestMu = (row) => row.alltime_mu ?? row.peak_mu
const bestWhen = (row) => row.alltime_date ?? row.peak_utc

function Podium({ rows, peak, pairs, event }) {
  return (
    <div className="podium">
      {rows.slice(0, 3).map((row, i) => {
        const players = pairs ? [row.player1, row.player2] : [row.player]
        const to = pairs ? `/pairs/${event}/${row.player1.player_id}/${row.player2.player_id}` : `/players/${row.player.player_id}`
        const value = peak ? (pairs ? row.peak_rating : bestMu(row)) : row.rating
        return (
          <Link key={players.map((p) => p.player_id).join('-')} to={to} className={`pod card ${i === 0 ? 'first' : ''}`}>
            <Medal n={i + 1} />
            <span className="pair-av">{players.map((p) => <Avatar key={p.player_id} player={p} size={i === 0 ? 52 : 44} />)}</span>
            <span className="pod-info">
              <span className="pod-nm">{players.map((p) => p.name_display).join(' / ')}</span>
              <span className="pod-cc">{flag(players[0].country_code)} {players[0].country_code}
                {!pairs && row.matches_played ? ` · ${row.matches_played} matches` : ''}
                {pairs ? ` · ${row.matches_together} together` : ''}</span>
            </span>
            <span className="pod-big">
              <span className="num-display">{value != null ? fmt(value) : '—'}</span>
              {!peak && row.form?.length > 1 && <Sparkline values={row.form} width={110} height={34} />}
            </span>
            <span className="pod-meta">
              {!pairs && !peak && <span>Skill <b>{fmt(row.mu)}</b> ±{uncertainty(row.rd)}</span>}
              {peak && !pairs && bestWhen(row) && <span>Peaked <b>{fmtMonth(bestWhen(row))}</b></span>}
              {row.win_pct != null && <span>Wins <b>{Math.round(row.win_pct)}%</b></span>}
              {!pairs && !peak && row.peak_mu != null && <span>Peak <b>{fmt(row.peak_mu)}</b></span>}
            </span>
          </Link>
        )
      })}
    </div>
  )
}

function SortHead({ label, active, onClick, title }) {
  return (
    <th className={`num sortable ${active ? 'sorted' : ''}`} title={title}>
      <button onClick={onClick} aria-sort={active ? 'descending' : 'none'}>
        {label}{active && <Icon name="arrowDown" size={11} stroke={2.4} />}
      </button>
    </th>
  )
}

function IndividualBoard({ event, ranking, order, setOrder, gender, page, setPage }) {
  const isPeak = ranking === 'peak'
  const { data, error, loading, reload } = useAsync(
    () => api.leaderboard(event, { order, ranking, gender, minMatches: 5, limit: PAGE, offset: page * PAGE }),
    [event, ranking, order, gender, page],
  )
  if (loading) return <><div className="podium">{[0, 1, 2].map((i) => <div key={i} className="pod card"><Skeleton h={110} /></div>)}</div><SkeletonList rows={10} /></>
  if (error) return <ErrorState error={error} onRetry={reload} what="the rankings" />
  if (!data.results.length) {
    return <EmptyState icon="users" title="No players yet" hint="No rated players match this filter. Try another discipline." />
  }
  const showMove = !isPeak && data.results.some((r) => 'rank_change' in r)
  return (
    <>
      {page === 0 && <Podium rows={data.results} peak={isPeak} event={event} />}
      <div className="table-scroll card">
        <table className="board rank-table">
          <thead>
            <tr>
              <th className="rank">#</th>
              <th>Player</th>
              {isPeak ? <th className="num">Peak</th> : (
                <SortHead label="Rating" active={order === 'rating'} onClick={() => setOrder('rating')}
                  title="Ranked by the cautious rating (skill minus twice the uncertainty)" />
              )}
              {isPeak ? <th className="num">Peaked</th> : (
                <SortHead label="Skill · certainty" active={order === 'mu'} onClick={() => setOrder('mu')}
                  title="The engine's best estimate of skill, ± how sure it is" />
              )}
              <th className="num">Win rate</th>
              <th className="num hide-md">Matches</th>
              {!isPeak && <th className="hide-md">Form · last 20 events</th>}
            </tr>
          </thead>
          <tbody>
            {data.results.map((row, i) => {
              const rank = page * PAGE + i + 1
              return (
                <tr key={row.player.player_id}>
                  <td className="rank">
                    <span className="rank-cell"><Medal n={rank} />{showMove && <Move value={row.rank_change} />}</span>
                  </td>
                  <td>
                    <Link to={`/players/${row.player.player_id}`} className="pcell">
                      <Avatar player={row.player} />
                      <span className="pmeta">
                        <span className="pname">{row.player.name_display}</span>
                        <span className="psub"><span className="fl">{flag(row.player.country_code)}</span>{row.player.country_code}</span>
                      </span>
                    </Link>
                  </td>
                  <td className="num"><span className="metric">{isPeak ? fmt(bestMu(row)) : fmt(row.rating)}</span></td>
                  <td className="num">
                    {isPeak
                      ? <span className="muted mono">{bestWhen(row) ? fmtMonth(bestWhen(row)) : '—'}</span>
                      : <span className="skill-cell"><span className="mono">{fmt(row.mu)}</span><span className="pm">±{uncertainty(row.rd)}</span><Confidence rd={row.rd} /></span>}
                  </td>
                  <td className="num">
                    {row.win_pct != null
                      ? <span className="wbar"><span className="mono">{row.win_pct.toFixed(1)}%</span><span className="b"><i style={{ width: `${row.win_pct}%` }} /></span></span>
                      : <span className="muted">—</span>}
                  </td>
                  <td className="num muted mono hide-md">{row.matches_played}</td>
                  {!isPeak && <td className="hide-md"><Sparkline values={row.form} width={96} height={24} /></td>}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <Pager page={page} setPage={setPage} count={data.count} />
    </>
  )
}

function PairsBoard({ event, ranking, page, setPage }) {
  const isPeak = ranking === 'peak'
  const { data, error, loading, reload } = useAsync(
    () => api.pairs(event, { minMatches: 5, ranking, limit: PAGE, offset: page * PAGE }),
    [event, ranking, page],
  )
  if (loading) return <SkeletonList rows={10} />
  if (error) return <ErrorState error={error} onRetry={reload} what="the pairs" />
  if (!data.results.length) {
    return <EmptyState icon="link" title="No pairs yet" hint="No partnerships match this filter. They may not have played enough together." />
  }
  return (
    <>
      {page === 0 && <Podium rows={data.results} peak={isPeak} pairs event={event} />}
      <div className="table-scroll card">
        <table className="board rank-table">
          <thead>
            <tr>
              <th className="rank">#</th><th>Pair</th>
              <th className="num">{isPeak ? 'Peak' : 'Rating'}</th>
              <th className="num">Together</th>
              <th className="num">Win rate</th>
            </tr>
          </thead>
          <tbody>
            {data.results.map((row, i) => {
              const to = `/pairs/${event}/${row.player1.player_id}/${row.player2.player_id}`
              const rank = page * PAGE + i + 1
              return (
                <tr key={`${row.player1.player_id}-${row.player2.player_id}`}>
                  <td className="rank"><Medal n={rank} /></td>
                  <td>
                    <Link to={to} className="pcell">
                      <span className="pair-av"><Avatar player={row.player1} size="sm" /><Avatar player={row.player2} size="sm" /></span>
                      <span className="pmeta">
                        <span className="pname">{row.player1.name_display} / {row.player2.name_display}</span>
                        <span className="psub">
                          <span className="fl">{flag(row.player1.country_code)}</span>{row.player1.country_code}
                          {row.player2.country_code !== row.player1.country_code
                            ? <> <span className="fl">{flag(row.player2.country_code)}</span>{row.player2.country_code}</> : ''}
                        </span>
                      </span>
                    </Link>
                  </td>
                  <td className="num"><span className="metric">
                    {isPeak ? (row.peak_rating != null ? fmt(row.peak_rating) : '—') : fmt(row.rating)}
                  </span></td>
                  <td className="num muted mono">{row.matches_together}</td>
                  <td className="num">
                    {row.win_pct != null
                      ? <span className="wbar"><span className="mono">{row.win_pct.toFixed(1)}%</span><span className="b"><i style={{ width: `${row.win_pct}%` }} /></span></span>
                      : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <Pager page={page} setPage={setPage} count={data.count} />
    </>
  )
}
