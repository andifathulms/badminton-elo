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
  const PAD = { l: 30, r: 46, t: 30, b: 22 }
  const a = analyse(g)
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
            <stop offset="0%" stopColor="var(--ink-2)" stopOpacity="0.16" />
            <stop offset="100%" stopColor="var(--ink-2)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 7, 14, 21].filter((v) => v <= maxScore).map((v) => (
          <g key={v}>
            <line x1={PAD.l} x2={W - PAD.r} y1={Y(v)} y2={Y(v)} className="grid" />
            <text x={W - PAD.r + 6} y={Y(v) + 3} className="axis">{v}</text>
          </g>
        ))}
        <text x={PAD.l} y={16} className="worm-title">Game {index + 1}</text>
        <text x={W - PAD.r} y={16} className="worm-score" textAnchor="end">
          {a.last[0]}–{a.last[1]}
        </text>
        <polygon points={areaPts(0)} fill={`url(#s1grad${index}${big ? 'b' : ''})`} />
        <polygon points={areaPts(1)} fill={`url(#s2grad${index}${big ? 'b' : ''})`} />
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

function ScoreRace({ progression }) {
  const games = (progression || []).filter((g) => g && g.length)
  const [tab, setTab] = useState(0) // selected game index (defaults to Game 1)
  if (!games.length) return null
  const game = games[Math.min(tab, games.length - 1)]

  return (
    <div className="chart-wrap">
      {games.length > 1 && (
        <div className="tabs mini-tabs">
          {games.map((_, i) => (
            <button key={i} className={`tab ${tab === i ? 'active' : ''}`}
                    onClick={() => setTab(i)}>
              Game {i + 1}
            </button>
          ))}
        </div>
      )}
      <GameChart key={tab} g={game} index={Math.min(tab, games.length - 1)} big />
      <p className="muted small">
        Each side's running score, rally by rally (
        <b className="race-key s1">side&nbsp;1</b> vs{' '}
        <b className="race-key s2">side&nbsp;2</b>). Hover to read the exact score.
      </p>
    </div>
  )
}

function StatBar({ label, a, b }) {
  const total = (a || 0) + (b || 0)
  const pctA = total ? (100 * a) / total : 50
  return (
    <div className="statbar">
      <span className="statbar-a">{a ?? '—'}</span>
      <div className="statbar-track">
        <div className="statbar-fill" style={{ width: `${pctA}%` }} />
      </div>
      <span className="statbar-b">{b ?? '—'}</span>
      <span className="statbar-label">{label}</span>
    </div>
  )
}

export default function MatchStats({ matchId }) {
  const { data, error, loading } = useAsync(() => api.matchStatistics(matchId), [matchId])

  if (loading) return <p className="muted">Loading statistics…</p>
  if (error || !data || data.available === false)
    return <p className="muted">No detailed statistics available for this match.</p>

  return (
    <div>
      <div className="statbars">
        <StatBar label="Rallies won" a={data.team1_rallies_won} b={data.team2_rallies_won} />
        <StatBar label="Longest streak" a={data.team1_consecutive_points} b={data.team2_consecutive_points} />
        <StatBar label="Game points" a={data.team1_game_points} b={data.team2_game_points} />
      </div>
      {data.duration_min != null && (
        <p className="muted small">Duration: {data.duration_min} min · Total rallies:{' '}
          {data.team1_rallies_played ?? '?'}</p>
      )}
      <ScoreRace progression={data.point_progression} />
    </div>
  )
}
