import { useState } from 'react'
import { api } from '../api.js'
import { useAsync } from '../useAsync.js'

// Per-game "score worm": cumulative (team1 − team2) point difference across
// rallies. Above the centre line = side 1 ahead, below = side 2 ahead. Dots mark
// every rally; ties sit on the line; the game-point rally and the game-winning
// rally are called out. Hover any dot to read the exact score.
function ScoreWorm({ progression }) {
  const [hover, setHover] = useState(null)
  const games = (progression || []).filter((g) => g && g.length)
  if (!games.length) return null
  const W = 720
  const GH = 108
  const gap = 30
  const H = games.length * (GH + gap)
  const amp = GH / 2 - 12

  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="chart worm-chart" role="img"
           aria-label="Point-by-point score progression">
        {games.map((g, gi) => {
          const y0 = gi * (GH + gap) + GH / 2 + 10
          const maxAbs = Math.max(1, ...g.map(([a, b]) => Math.abs(a - b)))
          const stepX = (W - 40) / Math.max(1, g.length - 1)
          const X = (i) => 20 + i * stepX
          const Y = (a, b) => y0 - ((a - b) / maxAbs) * amp
          const pts = g.map(([a, b], i) => `${X(i).toFixed(1)},${Y(a, b).toFixed(1)}`).join(' ')
          const last = g[g.length - 1]
          const winner = last[0] > last[1] ? 0 : 1
          const target = Math.max(last[0], last[1]) - 1
          // First rally where the eventual winner reached game point while ahead.
          let gpIdx = -1
          for (let i = 0; i < g.length; i++) {
            if (g[i][winner] === target && g[i][winner] > g[i][1 - winner]) { gpIdx = i; break }
          }
          return (
            <g key={gi}>
              <line x1="20" x2={W - 20} y1={y0} y2={y0} className="grid" />
              <text x="20" y={y0 - GH / 2 + 2} className="worm-title">Game {gi + 1}</text>
              <text x={W - 20} y={y0 - GH / 2 + 2} className="worm-score" textAnchor="end">
                {last[0]}–{last[1]}
              </text>
              <polyline points={pts} className="worm" fill="none" />
              {g.map(([a, b], i) => {
                const tie = a === b
                const isGp = i === gpIdx
                const isFinal = i === g.length - 1
                const cls = isFinal ? 'wd-final' : isGp ? 'wd-gp' : tie ? 'wd-tie' : 'wd'
                return (
                  <circle key={i} cx={X(i)} cy={Y(a, b)}
                    r={isFinal || isGp ? 4 : tie ? 2.6 : 2} className={cls}
                    onMouseEnter={() => setHover({ i, a, b, x: X(i), y: Y(a, b) })}
                    onMouseLeave={() => setHover(null)} />
                )
              })}
              {gpIdx >= 0 && (
                <text x={X(gpIdx)} y={Y(g[gpIdx][0], g[gpIdx][1]) - 9}
                      className="worm-note" textAnchor="middle">game pt</text>
              )}
            </g>
          )
        })}
        {hover && (
          <g className="worm-tip" pointerEvents="none">
            <rect x={Math.min(Math.max(hover.x - 30, 2), W - 62)} y={hover.y - 31}
                  width="60" height="21" rx="6" />
            <text x={Math.min(Math.max(hover.x, 32), W - 32)} y={hover.y - 16}
                  textAnchor="middle">{hover.a}–{hover.b}</text>
          </g>
        )}
      </svg>
      <p className="muted small">
        Score worm: cumulative point lead per game (up = side 1, down = side 2).
        Dots on the centre line are ties; <b className="gp-key">game point</b> and the
        winning rally are highlighted. Hover a dot for the exact score.
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
      <ScoreWorm progression={data.point_progression} />
    </div>
  )
}
