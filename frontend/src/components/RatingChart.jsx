// Inline-SVG rating chart on a real time axis: skill line with a ±rd band, the
// all-time peak marked in gold and today's value called out. No chart library.
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { fmtMonth } from '../dates.js'

const W = 760
const H = 280
const PAD = { top: 30, right: 22, bottom: 30, left: 48 }

export default function RatingChart({ points }) {
  const [hover, setHover] = useState(null)
  const pts = useMemo(
    () => (points || []).filter((p) => p.applied_utc).map((p) => ({ ...p, t: Date.parse(p.applied_utc) })),
    [points],
  )
  if (pts.length === 0) return <p className="muted">No rating history.</p>

  const mus = pts.map((p) => p.mu_after)
  const lo = Math.min(...pts.map((p) => p.mu_after - p.rd_after))
  const hi = Math.max(...pts.map((p) => p.mu_after + p.rd_after))
  const step = hi - lo > 900 ? 400 : 200
  const yMin = Math.floor((lo - 20) / step) * step
  const yMax = Math.ceil((hi + 60) / step) * step
  const t0 = pts[0].t
  const t1 = pts.length > 1 ? pts[pts.length - 1].t : t0 + 86400000
  const iw = W - PAD.left - PAD.right
  const ih = H - PAD.top - PAD.bottom
  const x = (t) => PAD.left + ((t - t0) / (t1 - t0 || 1)) * iw
  const y = (v) => PAD.top + ih - ((v - yMin) / (yMax - yMin || 1)) * ih

  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)} ${y(p.mu_after).toFixed(1)}`).join('')
  const band = `${pts.map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)} ${y(p.mu_after + p.rd_after).toFixed(1)}`).join('')}${[...pts].reverse().map((p) => `L${x(p.t).toFixed(1)} ${y(p.mu_after - p.rd_after).toFixed(1)}`).join('')}Z`
  const area = `${line}L${x(t1).toFixed(1)} ${PAD.top + ih}L${PAD.left} ${PAD.top + ih}Z`

  let pk = 0
  mus.forEach((v, i) => { if (v > mus[pk]) pk = i })
  const last = pts[pts.length - 1]
  const peak = pts[pk]
  const peakIsNow = pk === pts.length - 1 || peak.mu_after - last.mu_after < 1

  const ticks = []
  for (let v = yMin; v <= yMax; v += step) ticks.push(v)
  const y0 = new Date(t0).getUTCFullYear()
  const y1 = new Date(t1).getUTCFullYear()
  const every = Math.max(1, Math.ceil((y1 - y0) / 8))
  const years = []
  for (let yr = y0 + 1; yr <= y1; yr += every) years.push(yr)

  const anchor = (px) => (px > W - 150 ? 'end' : px < PAD.left + 80 ? 'start' : 'middle')

  function onMove(e) {
    const r = e.currentTarget.getBoundingClientRect()
    const t = t0 + (((e.clientX - r.left) / r.width) * W - PAD.left) / iw * (t1 - t0)
    let best = 0
    for (let i = 0; i < pts.length; i++) if (Math.abs(pts[i].t - t) < Math.abs(pts[best].t - t)) best = i
    setHover(best)
  }
  const hp = hover != null ? pts[hover] : null

  return (
    <div className="chart-wrap card">
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Rating over time"
           onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        <defs>
          <linearGradient id="rc-area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--brand)" stopOpacity="0.20" />
            <stop offset="100%" stopColor="var(--brand)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} className="grid" />
            <text x={PAD.left - 8} y={y(t) + 3.5} className="axis" textAnchor="end">{t}</text>
          </g>
        ))}
        {years.map((yr) => {
          const tx = x(Date.UTC(yr, 0, 1))
          return <text key={yr} x={tx} y={H - 8} className="axis" textAnchor="middle">{yr}</text>
        })}
        <path d={band} className="band" />
        <path d={area} fill="url(#rc-area)" />
        <path d={line} className="line" fill="none" />

        {!peakIsNow && (
          <g>
            <line x1={x(peak.t)} x2={x(peak.t)} y1={y(peak.mu_after)} y2={PAD.top + ih} className="marker-line" />
            <circle cx={x(peak.t)} cy={y(peak.mu_after)} r={4.5} className="peak-dot" />
            <text x={x(peak.t)} y={y(peak.mu_after) - 10} className="marker-label peak" textAnchor={anchor(x(peak.t))}>
              Peak {peak.mu_after.toFixed(0)} · {fmtMonth(peak.applied_utc)}
            </text>
          </g>
        )}
        <circle cx={x(last.t)} cy={y(last.mu_after)} r={5} className={peakIsNow ? 'peak-dot' : 'now-dot'} />
        <text x={x(last.t) - 8} y={y(last.mu_after) - 12} className={`marker-label ${peakIsNow ? 'peak' : 'now'}`} textAnchor="end">
          {peakIsNow ? 'Career high · ' : 'Now '}{last.mu_after.toFixed(0)}
        </text>

        {hp && (
          <g className="hover">
            <line x1={x(hp.t)} x2={x(hp.t)} y1={PAD.top} y2={PAD.top + ih} className="marker-line" />
            <circle cx={x(hp.t)} cy={y(hp.mu_after)} r={4} className="now-dot" />
            <g transform={`translate(${Math.min(W - PAD.right - 128, Math.max(PAD.left, x(hp.t) - 64))},${PAD.top - 24})`}>
              <rect width="128" height="20" rx="6" className="tip-bg" />
              <text x="64" y="14" textAnchor="middle" className="tip-tx">
                {hp.mu_after.toFixed(0)} · {hp.applied_utc.slice(0, 10)}
              </text>
            </g>
          </g>
        )}
      </svg>
      <p className="muted small chart-note">
        Line = skill estimate after each match; shaded band = its uncertainty · {pts.length} rated matches
        {last.match && <> · <Link to={`/matches/${last.match}`}>latest match</Link></>}
      </p>
    </div>
  )
}
