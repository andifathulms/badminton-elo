// Self-contained inline-SVG line chart of mu over time, with a ±rd uncertainty
// band, the all-time peak marked, and the current value called out. No external
// chart library — keeps the bundle small and CSP-friendly.
import { Link } from 'react-router-dom'

const W = 720
const H = 280
const PAD = { top: 26, right: 18, bottom: 34, left: 46 }

const yr = (iso) => (iso ? iso.slice(0, 4) : '')
const ym = (iso) => (iso ? iso.slice(0, 7) : '')

export default function RatingChart({ points }) {
  if (!points || points.length === 0) {
    return <p className="muted">No rating history.</p>
  }

  const xs = points.map((_, i) => i)
  const mus = points.map((p) => p.mu_after)
  const lows = points.map((p) => p.mu_after - p.rd_after)
  const highs = points.map((p) => p.mu_after + p.rd_after)

  const pad = (Math.max(...highs) - Math.min(...lows)) * 0.06 || 10
  const yMin = Math.min(...lows) - pad
  const yMax = Math.max(...highs) + pad
  const innerW = W - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom

  const xScale = (i) =>
    PAD.left + (xs.length === 1 ? innerW / 2 : (i / (xs.length - 1)) * innerW)
  const yScale = (v) =>
    PAD.top + innerH - ((v - yMin) / (yMax - yMin || 1)) * innerH

  const line = mus.map((v, i) => `${xScale(i)},${yScale(v)}`).join(' ')
  const area =
    `${xScale(0)},${yScale(yMin)} ` +
    mus.map((v, i) => `${xScale(i)},${yScale(v)}`).join(' ') +
    ` ${xScale(xs.length - 1)},${yScale(yMin)}`
  const band =
    highs.map((v, i) => `${xScale(i)},${yScale(v)}`).join(' ') +
    ' ' +
    lows
      .map((v, i) => `${xScale(xs.length - 1 - i)},${yScale(lows[xs.length - 1 - i])}`)
      .join(' ')

  // Peak (highest mu ever) and the current (latest) value.
  let peakIdx = 0
  mus.forEach((v, i) => { if (v > mus[peakIdx]) peakIdx = i })
  const lastIdx = mus.length - 1
  const peak = points[peakIdx]
  const last = points[lastIdx]

  const yticks = 4
  const ticks = Array.from({ length: yticks + 1 }, (_, k) =>
    Math.round(yMin + (k / yticks) * (yMax - yMin)),
  )
  // Keep labels inside the frame.
  const clampX = (x, w) => Math.max(PAD.left + w / 2, Math.min(W - PAD.right - w / 2, x))

  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img"
           aria-label="Rating over time">
        <defs>
          <linearGradient id="rc-area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--brand)" stopOpacity="0.20" />
            <stop offset="100%" stopColor="var(--brand)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={W - PAD.right} y1={yScale(t)} y2={yScale(t)} className="grid" />
            <text x={PAD.left - 8} y={yScale(t) + 4} className="axis" textAnchor="end">{t}</text>
          </g>
        ))}
        <polygon points={band} className="band" />
        <polygon points={area} fill="url(#rc-area)" />
        <polyline points={line} className="line" fill="none" />

        {mus.length <= 60 &&
          mus.map((v, i) => (
            <circle key={i} cx={xScale(i)} cy={yScale(v)} r={2} className="dot" />
          ))}

        {/* Peak marker */}
        {peakIdx !== lastIdx && (
          <g>
            <line x1={xScale(peakIdx)} x2={xScale(peakIdx)} y1={yScale(peak.mu_after)}
                  y2={PAD.top + innerH} className="marker-line" />
            <circle cx={xScale(peakIdx)} cy={yScale(peak.mu_after)} r={4} className="peak-dot" />
            <text x={clampX(xScale(peakIdx), 90)} y={yScale(peak.mu_after) - 10}
                  className="marker-label peak" textAnchor="middle">
              ▲ Peak {peak.mu_after.toFixed(0)} · {ym(peak.applied_utc)}
            </text>
          </g>
        )}

        {/* Current value */}
        <circle cx={xScale(lastIdx)} cy={yScale(last.mu_after)} r={4.5} className="now-dot" />
        <text x={clampX(xScale(lastIdx), 70)} y={yScale(last.mu_after) - 12}
              className="marker-label now" textAnchor="middle">
          Now {last.mu_after.toFixed(0)}
        </text>

        <text x={PAD.left} y={H - 10} className="axis">{yr(points[0].applied_utc)}</text>
        <text x={W - PAD.right} y={H - 10} className="axis" textAnchor="end">
          {yr(last.applied_utc)}
        </text>
      </svg>
      <p className="muted small">
        Shaded band = ±rd (uncertainty) · {points.length} rated matches · peak{' '}
        <b>{peak.mu_after.toFixed(0)}</b>, now <b>{last.mu_after.toFixed(0)}</b>.{' '}
        {last.match && <Link to={`/matches/${last.match}`}>last match →</Link>}
      </p>
    </div>
  )
}
