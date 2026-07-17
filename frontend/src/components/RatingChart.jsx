// Self-contained inline-SVG line chart of mu over time, with a ±rd uncertainty
// band. No external chart library — keeps the bundle small and CSP-friendly.
import { Link } from 'react-router-dom'

const W = 720
const H = 260
const PAD = { top: 16, right: 16, bottom: 28, left: 44 }

export default function RatingChart({ points }) {
  if (!points || points.length === 0) {
    return <p className="muted">No rating history.</p>
  }

  const xs = points.map((_, i) => i)
  const mus = points.map((p) => p.mu_after)
  const lows = points.map((p) => p.mu_after - p.rd_after)
  const highs = points.map((p) => p.mu_after + p.rd_after)

  const yMin = Math.min(...lows)
  const yMax = Math.max(...highs)
  const innerW = W - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom

  const xScale = (i) =>
    PAD.left + (xs.length === 1 ? innerW / 2 : (i / (xs.length - 1)) * innerW)
  const yScale = (v) =>
    PAD.top + innerH - ((v - yMin) / (yMax - yMin || 1)) * innerH

  const line = mus.map((v, i) => `${xScale(i)},${yScale(v)}`).join(' ')
  const band =
    highs.map((v, i) => `${xScale(i)},${yScale(v)}`).join(' ') +
    ' ' +
    lows
      .map((v, i) => `${xScale(xs.length - 1 - i)},${yScale(lows[xs.length - 1 - i])}`)
      .join(' ')

  const yticks = 4
  const ticks = Array.from({ length: yticks + 1 }, (_, k) =>
    Math.round(yMin + (k / yticks) * (yMax - yMin)),
  )

  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img"
           aria-label="Rating over time">
        {ticks.map((t) => (
          <g key={t}>
            <line
              x1={PAD.left} x2={W - PAD.right}
              y1={yScale(t)} y2={yScale(t)}
              className="grid"
            />
            <text x={PAD.left - 6} y={yScale(t) + 4} className="axis" textAnchor="end">
              {t}
            </text>
          </g>
        ))}
        <polygon points={band} className="band" />
        <polyline points={line} className="line" fill="none" />
        {mus.map((v, i) => (
          <circle key={i} cx={xScale(i)} cy={yScale(v)} r={points.length > 60 ? 0 : 2.5}
                  className="dot" />
        ))}
        <text x={PAD.left} y={H - 8} className="axis">first match</text>
        <text x={W - PAD.right} y={H - 8} className="axis" textAnchor="end">latest</text>
      </svg>
      <p className="muted small">
        Shaded band = ±rd (uncertainty). {points.length} rated matches; latest mu{' '}
        {mus[mus.length - 1].toFixed(0)}.{' '}
        {points[points.length - 1].match && (
          <Link to={`/matches/${points[points.length - 1].match}`}>last match →</Link>
        )}
      </p>
    </div>
  )
}
