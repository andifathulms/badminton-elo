import { api } from '../api.js'
import { useAsync } from '../useAsync.js'

// Per-game "score worm": cumulative (team1 − team2) point difference across
// rallies. Above the centre line = side 1 ahead, below = side 2 ahead.
function ScoreWorm({ progression }) {
  const games = (progression || []).filter((g) => g && g.length)
  if (!games.length) return null
  const W = 720
  const GH = 90
  const gap = 18
  const H = games.length * (GH + gap)

  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img"
           aria-label="Point-by-point score progression">
        {games.map((g, gi) => {
          const y0 = gi * (GH + gap) + GH / 2
          const maxAbs = Math.max(1, ...g.map(([a, b]) => Math.abs(a - b)))
          const stepX = (W - 40) / Math.max(1, g.length - 1)
          const pts = g
            .map(([a, b], i) => {
              const x = 20 + i * stepX
              const y = y0 - ((a - b) / maxAbs) * (GH / 2 - 6)
              return `${x.toFixed(1)},${y.toFixed(1)}`
            })
            .join(' ')
          const last = g[g.length - 1]
          return (
            <g key={gi}>
              <line x1="20" x2={W - 20} y1={y0} y2={y0} className="grid" />
              <text x="20" y={y0 - GH / 2} className="axis">
                Game {gi + 1} · {last[0]}–{last[1]}
              </text>
              <polyline points={pts} className="worm" fill="none" />
            </g>
          )
        })}
      </svg>
      <p className="muted small">
        Score worm: cumulative point lead per game (up = side 1, down = side 2).
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
