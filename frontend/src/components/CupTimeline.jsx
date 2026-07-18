import { useState } from 'react'
import { api } from '../api.js'
import { useAsync } from '../useAsync.js'
import { flag } from '../flags.js'

// Distinct, theme-agnostic line colours for up to 8 countries.
const COLORS = ['#4f46e5', '#e11d48', '#0f9d58', '#d19a1e', '#7c3aed',
  '#0891b2', '#db2777', '#65a30d']

export default function CupTimeline({ cup }) {
  const { data, error, loading } = useAsync(() => api.cupHistory(cup), [cup])
  const [hi, setHi] = useState(null)

  if (loading) return <p className="muted">Loading timeline…</p>
  if (error || !data?.series?.length) return null

  const { years, series } = data
  const W = 900
  const H = 320
  const PAD = { l: 46, r: 96, t: 16, b: 28 }
  const allVals = series.flatMap((s) => s.points.map((p) => p.power).filter(Boolean))
  const yMin = Math.min(...allVals) * 0.98
  const yMax = Math.max(...allVals) * 1.02
  const X = (yr) =>
    PAD.l + ((yr - years[0]) / Math.max(1, years.length - 1)) * (W - PAD.l - PAD.r)
  const Y = (v) => H - PAD.b - ((v - yMin) / (yMax - yMin || 1)) * (H - PAD.t - PAD.b)

  const path = (pts) => {
    const seg = pts.filter((p) => p.power != null)
    return seg.map((p, i) => `${i ? 'L' : 'M'}${X(p.year).toFixed(1)},${Y(p.power).toFixed(1)}`).join(' ')
  }
  const yticks = 4
  const ticks = Array.from({ length: yticks + 1 }, (_, k) =>
    Math.round(yMin + (k / yticks) * (yMax - yMin)))

  return (
    <div className="chart-wrap timeline-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img"
           aria-label="Cup power over time">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.l} x2={W - PAD.r} y1={Y(t)} y2={Y(t)} className="grid" />
            <text x={PAD.l - 8} y={Y(t) + 4} className="axis" textAnchor="end">
              {(t / 1000).toFixed(1)}k
            </text>
          </g>
        ))}
        {years.filter((_, i) => i % Math.ceil(years.length / 10) === 0).map((yr) => (
          <text key={yr} x={X(yr)} y={H - 8} className="axis" textAnchor="middle">{yr}</text>
        ))}
        {series.map((s, i) => {
          const dim = hi != null && hi !== s.country
          return (
            <g key={s.country} opacity={dim ? 0.18 : 1}
               onMouseEnter={() => setHi(s.country)} onMouseLeave={() => setHi(null)}>
              <path d={path(s.points)} fill="none" stroke={COLORS[i % COLORS.length]}
                    strokeWidth={hi === s.country ? 3.5 : 2} />
              {(() => {
                const last = [...s.points].reverse().find((p) => p.power != null)
                return last ? (
                  <text x={W - PAD.r + 6} y={Y(last.power) + 4}
                        className="tl-label" fill={COLORS[i % COLORS.length]}>
                    {flag(s.country)} {s.country}
                  </text>
                ) : null
              })()}
            </g>
          )
        })}
      </svg>
      <p className="muted small">Team power by year (top {series.length} nations) —
        reconstructed from each era's active players. Hover a line to highlight.</p>
    </div>
  )
}
