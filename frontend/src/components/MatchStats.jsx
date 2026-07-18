import { useState } from 'react'
import { api } from '../api.js'
import { useAsync } from '../useAsync.js'

// Per-game score race: the two sides' running scores climb rally-by-rally to
// the game total (BWF-style). Two step-lines race each other; the side ahead is
// visually higher. Hover a rally to read the exact score.
function ScoreRace({ progression, side1Won }) {
  const [hover, setHover] = useState(null)
  const games = (progression || []).filter((g) => g && g.length)
  if (!games.length) return null
  const W = 720
  const PAD = { l: 26, r: 44, t: 24, b: 10 }
  const GH = 130
  const gap = 22
  const H = games.length * (GH + gap)

  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="chart race-chart" role="img"
           aria-label="Point-by-point score race">
        {games.map((g, gi) => {
          const top = gi * (GH + gap)
          const y0 = top + GH - PAD.b
          const yTop = top + PAD.t
          const last = g[g.length - 1]
          const maxScore = Math.max(last[0], last[1], 21)
          const stepX = (W - PAD.l - PAD.r) / Math.max(1, g.length - 1)
          const X = (i) => PAD.l + i * stepX
          const Y = (v) => y0 - (v / maxScore) * (y0 - yTop)
          const line = (idx) =>
            g.map((s, i) => `${X(i).toFixed(1)},${Y(s[idx]).toFixed(1)}`).join(' ')
          const s1win = last[0] > last[1]
          return (
            <g key={gi}>
              {/* horizontal gridlines every ~7 pts */}
              {[0, 7, 14, 21].filter((v) => v <= maxScore).map((v) => (
                <g key={v}>
                  <line x1={PAD.l} x2={W - PAD.r} y1={Y(v)} y2={Y(v)} className="grid" />
                  <text x={W - PAD.r + 6} y={Y(v) + 3} className="axis">{v}</text>
                </g>
              ))}
              <text x={PAD.l} y={top + 14} className="worm-title">Game {gi + 1}</text>
              <text x={W - PAD.r} y={top + 14} className="worm-score" textAnchor="end">
                {last[0]}–{last[1]}
              </text>
              <polyline points={line(1)} fill="none"
                        className={`race-line s2 ${!s1win ? 'winner' : ''}`} />
              <polyline points={line(0)} fill="none"
                        className={`race-line s1 ${s1win ? 'winner' : ''}`} />
              {g.map((s, i) => (
                <rect key={i} x={X(i) - stepX / 2} y={yTop} width={stepX} height={y0 - yTop}
                      fill="transparent"
                      onMouseEnter={() => setHover({ x: X(i), y: yTop, a: s[0], b: s[1] })}
                      onMouseLeave={() => setHover(null)} />
              ))}
              <circle cx={X(g.length - 1)} cy={Y(last[0])} r="3.5" className="race-dot s1" />
              <circle cx={X(g.length - 1)} cy={Y(last[1])} r="3.5" className="race-dot s2" />
            </g>
          )
        })}
        {hover && (
          <g className="worm-tip" pointerEvents="none">
            <rect x={Math.min(Math.max(hover.x - 30, 2), W - 62)} y={hover.y - 4}
                  width="60" height="21" rx="6" />
            <text x={Math.min(Math.max(hover.x, 32), W - 32)} y={hover.y + 11}
                  textAnchor="middle">{hover.a}–{hover.b}</text>
          </g>
        )}
      </svg>
      <p className="muted small">
        Score race: each side's running score per game (
        <b className="race-key s1">side&nbsp;1</b> vs{' '}
        <b className="race-key s2">side&nbsp;2</b>). Hover a rally for the exact score.
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
