import { useState } from 'react'
import { api } from '../api.js'
import { useAsync } from '../useAsync.js'

// Analyse one game's rally-by-rally progression for the little annotations
// (lead changes, biggest lead, whether the winner came from behind).
function analyse(g) {
  const last = g[g.length - 1]
  const s1win = last[0] > last[1]
  let leadChanges = 0
  let prev = 0
  let maxLead = 0
  let maxLeadAt = 0
  let winnerMaxDeficit = 0
  g.forEach((s, i) => {
    const diff = s[0] - s[1]
    const sign = Math.sign(diff)
    if (sign !== 0 && prev !== 0 && sign !== prev) leadChanges++
    if (sign !== 0) prev = sign
    if (Math.abs(diff) > maxLead) { maxLead = Math.abs(diff); maxLeadAt = i }
    // deficit the eventual game-winner was staring at
    const winnerBehind = s1win ? s[1] - s[0] : s[0] - s[1]
    if (winnerBehind > winnerMaxDeficit) winnerMaxDeficit = winnerBehind
  })
  return { last, s1win, leadChanges, maxLead, maxLeadAt, winnerMaxDeficit }
}

// One game rendered as two racing, area-filled step-lines. `big` scales it up
// for the single-game tabs.
function GameChart({ g, index, big }) {
  const [hover, setHover] = useState(null)
  const W = big ? 760 : 720
  const H = big ? 300 : 150
  const PAD = { l: 16, r: 44, t: 30, b: 24 }
  const a = analyse(g)
  const winnerIdx = a.s1win ? 0 : 1
  const maxScore = Math.max(a.last[0], a.last[1], 21)
  const stepX = (W - PAD.l - PAD.r) / Math.max(1, g.length - 1)
  const X = (i) => PAD.l + i * stepX
  const y0 = H - PAD.b
  const yTop = PAD.t
  const Y = (v) => y0 - (v / maxScore) * (y0 - yTop)
  const linePts = (idx) => g.map((s, i) => `${X(i).toFixed(1)},${Y(s[idx]).toFixed(1)}`).join(' ')
  const areaPts = (idx) =>
    `${X(0)},${y0} ${linePts(idx)} ${X(g.length - 1)},${y0}`

  return (
    <div className={`gc ${big ? 'gc-big' : ''}`}>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart race-chart" role="img"
           aria-label={`Game ${index + 1} score race`}>
        <defs>
          <linearGradient id={`s1grad${index}${big ? 'b' : ''}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--brand)" stopOpacity="0.22" />
            <stop offset="100%" stopColor="var(--brand)" stopOpacity="0" />
          </linearGradient>
          <linearGradient id={`s2grad${index}${big ? 'b' : ''}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--race-2)" stopOpacity="0.18" />
            <stop offset="100%" stopColor="var(--race-2)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 7, 14, 21].filter((v) => v <= maxScore).map((v) => (
          <g key={v}>
            <line x1={PAD.l} x2={W - PAD.r} y1={Y(v)} y2={Y(v)} className="grid" />
            <text x={W - PAD.r + 6} y={Y(v) + 3} className="axis">{v}</text>
          </g>
        ))}
        <text x={W - PAD.r} y={17} className="worm-score" textAnchor="end">
          {a.last[0]}–{a.last[1]}
        </text>
        {/* One soft fill under the winner's line — two stacked areas muddied it. */}
        <polygon points={areaPts(winnerIdx)}
                 fill={`url(#s${winnerIdx + 1}grad${index}${big ? 'b' : ''})`} />
        <polyline points={linePts(1)} fill="none"
                  className={`race-line s2 ${!a.s1win ? 'winner' : ''}`} />
        <polyline points={linePts(0)} fill="none"
                  className={`race-line s1 ${a.s1win ? 'winner' : ''}`} />
        {/* biggest-lead marker */}
        {big && a.maxLead >= 3 && (
          <line x1={X(a.maxLeadAt)} x2={X(a.maxLeadAt)}
                y1={Y(g[a.maxLeadAt][0])} y2={Y(g[a.maxLeadAt][1])}
                className="lead-mark" />
        )}
        {g.map((s, i) => (
          <rect key={i} x={X(i) - stepX / 2} y={yTop} width={stepX} height={y0 - yTop}
                fill="transparent"
                onMouseEnter={() => setHover({ x: X(i), a: s[0], b: s[1], i })}
                onMouseLeave={() => setHover(null)} />
        ))}
        {hover && (
          <line x1={hover.x} x2={hover.x} y1={yTop} y2={y0} className="race-cursor" />
        )}
        <circle cx={X(g.length - 1)} cy={Y(a.last[0])} r="3.8" className="race-dot s1" />
        <circle cx={X(g.length - 1)} cy={Y(a.last[1])} r="3.8" className="race-dot s2" />
        {hover && (
          <g className="worm-tip" pointerEvents="none">
            <rect x={Math.min(Math.max(hover.x - 34, 2), W - 70)} y={yTop - 20}
                  width="68" height="20" rx="6" />
            <text x={Math.min(Math.max(hover.x, 36), W - 36)} y={yTop - 6}
                  textAnchor="middle">{hover.a}–{hover.b}</text>
          </g>
        )}
      </svg>
      {big && (
        <div className="gc-facts">
          <span><b>{a.leadChanges}</b> lead change{a.leadChanges === 1 ? '' : 's'}</span>
          <span>Biggest lead <b>{a.maxLead}</b></span>
          {a.winnerMaxDeficit >= 2 && (
            <span className="comeback">Winner came back from <b>−{a.winnerMaxDeficit}</b></span>
          )}
        </div>
      )}
    </div>
  )
}

function ScoreRace({ progression, names = ['side 1', 'side 2'] }) {
  const games = (progression || []).filter((g) => g && g.length)
  const [tab, setTab] = useState(0) // selected game index (defaults to Game 1)
  if (!games.length) return null
  const game = games[Math.min(tab, games.length - 1)]

  return (
    <div className="chart-wrap card">
      {games.length > 1 && (
        <div className="segmented" style={{ marginBottom: 8 }}>
          {games.map((_, i) => (
            <button key={i} className={`seg ${tab === i ? 'active' : ''}`}
                    onClick={() => setTab(i)}>
              Game {i + 1}
            </button>
          ))}
        </div>
      )}
      <GameChart key={tab} g={game} index={Math.min(tab, games.length - 1)} big />
      <p className="muted small">
        Each side's running score, rally by rally (
        <b className="race-key s1">{names[0]}</b> vs{' '}
        <b className="race-key s2">{names[1]}</b>). Hover to read the exact score.
      </p>
    </div>
  )
}

// Lead after every rally for one game: area above the line = side 2 ahead,
// below = side 1 ahead (oriented to the names shown beside it).
function Worm({ g, index, names }) {
  const W = 300, H = 96, mid = H / 2
  const leads = [0, ...g.map(([a, b]) => b - a)]
  const mx = Math.max(6, ...leads.map(Math.abs))
  const x = (i) => 4 + (i * (W - 8)) / Math.max(1, leads.length - 1)
  const y = (l) => mid - (l / mx) * (mid - 10)
  const path = (f) => leads.map((l, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(f(l)).toFixed(1)}`).join('')
  const close = `L${x(leads.length - 1).toFixed(1)} ${mid}L4 ${mid}Z`
  const last = g[g.length - 1]
  return (
    <div className="worm">
      <div className="worm-h"><span>Game {index + 1}</span><b className="mono">{last[0]}–{last[1]}</b></div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={`Lead after every rally, game ${index + 1}`}>
        <line className="z" x1="0" x2={W} y1={mid} y2={mid} />
        <path className="pa" d={path((l) => Math.max(0, l)) + close} />
        <path className="na" d={path((l) => Math.min(0, l)) + close} />
        <path className="wl2" d={path((l) => l)} />
        <text x="4" y="10">{names[1]} ahead</text>
        <text x="4" y={H - 3}>{names[0]} ahead</text>
      </svg>
    </div>
  )
}

function StatBar({ label, a, b }) {
  const total = (a || 0) + (b || 0)
  return (
    <div className="mst">
      <span className="mst-lab">{label}</span>
      <div className="mst-row">
        <span className="mst-v">{a ?? '—'}</span>
        <span className="mst-bars">
          <span><i style={{ width: `${total ? (100 * a) / total : 0}%` }} /></span>
          <span><i style={{ width: `${total ? (100 * b) / total : 0}%` }} /></span>
        </span>
        <span className="mst-v r">{b ?? '—'}</span>
      </div>
    </div>
  )
}

// The API answers {pending: true} while it fetches a match's stats from BWF in
// the background; poll until they land (or give up after ~30 s).
const POLL_MS = 2000
const POLL_TRIES = 15
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function statisticsWhenReady(matchId) {
  let res = await api.matchStatistics(matchId)
  for (let i = 0; res?.pending && i < POLL_TRIES; i++) {
    await sleep(POLL_MS)
    res = await api.matchStatistics(matchId)
  }
  return res
}

export default function MatchStats({ matchId, names = ['Side 1', 'Side 2'] }) {
  const { data, error, loading } = useAsync(() => statisticsWhenReady(matchId), [matchId])

  if (loading) return <div className="card" style={{ padding: 18 }}><p className="muted" style={{ margin: 0 }}>Loading statistics…</p></div>
  if (error || !data || data.available === false)
    return <p className="muted">No rally-by-rally statistics are available for this match.</p>
  const games = (data.point_progression || []).filter((g) => g && g.length)

  return (
    <>
      <div className="ms-grid">
        {games.length > 0 && (
          <section className="card t-panel">
            <div className="t-panel-h"><h3>Momentum</h3><span className="muted small">lead after every rally</span></div>
            <div className="worms">{games.map((g, i) => <Worm key={i} g={g} index={i} names={names} />)}</div>
          </section>
        )}
        <section className="card t-panel">
          <div className="t-panel-h"><h3>Match stats</h3>
            {data.duration_min != null && <span className="muted small">{data.duration_min} min · {data.team1_rallies_played ?? '?'} rallies</span>}</div>
          <div className="mst-names"><span>{names[0]}</span><span>{names[1]}</span></div>
          <StatBar label="Rallies won" a={data.team1_rallies_won} b={data.team2_rallies_won} />
          <StatBar label="Longest run of points" a={data.team1_consecutive_points} b={data.team2_consecutive_points} />
          <StatBar label="Game points" a={data.team1_game_points} b={data.team2_game_points} />
        </section>
      </div>
      {games.length > 0 && (
        <>
          <div className="sec-head" style={{ marginTop: 6 }}><h2>Score race</h2></div>
          <ScoreRace progression={data.point_progression} names={names} />
        </>
      )}
    </>
  )
}
