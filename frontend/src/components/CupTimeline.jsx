import { useMemo, useRef, useState } from 'react'
import { api } from '../api.js'
import { useAsync } from '../useAsync.js'
import { flag } from '../flags.js'

// Validated categorical palette (dataviz skill, light surface). Order is the
// CVD-safety mechanism — do not reshuffle. Colour follows the NATION, not its
// rank, so a cup switch never repaints a nation that carries over.
const PALETTE = ['#2a78d6', '#008300', '#e87ba4', '#eda100', '#1baf7a',
  '#eb6834', '#4a3aa7', '#e34948']
const NATION_COLOR = {
  CHN: '#2a78d6', INA: '#e34948', JPN: '#e87ba4', KOR: '#4a3aa7',
  DEN: '#eb6834', MAS: '#eda100', IND: '#1baf7a', TPE: '#008300',
}

// Deterministic, distinct colour per shown nation: fixed hue where we have one,
// otherwise the next unused palette slot (so the eight on screen never collide).
function assignColors(series) {
  const used = new Set()
  const out = {}
  for (const s of series) {
    const c = NATION_COLOR[s.country]
    if (c && !used.has(c)) { out[s.country] = c; used.add(c) }
  }
  let k = 0
  for (const s of series) {
    if (out[s.country]) continue
    while (k < PALETTE.length && used.has(PALETTE[k])) k++
    out[s.country] = PALETTE[k] || '#898781'
    used.add(out[s.country])
  }
  return out
}

// A series' value at any year, linearly interpolated between its known points
// (matching the drawn line); null outside the nation's range.
function valueAt(known, year) {
  if (!known.length || year < known[0].year || year > known[known.length - 1].year) return null
  for (let i = 1; i < known.length; i++) {
    if (known[i].year >= year) {
      const a = known[i - 1], b = known[i]
      if (b.year === a.year) return b.power
      const t = (year - a.year) / (b.year - a.year)
      return a.power + t * (b.power - a.power)
    }
  }
  return known[known.length - 1].power
}

const fmtK = (v) => `${(v / 1000).toFixed(1)}k`

export default function CupTimeline({ cup }) {
  const { data, error, loading } = useAsync(() => api.cupHistory(cup), [cup])
  const [hi, setHi] = useState(null)     // hovered/emphasised nation
  const [cursor, setCursor] = useState(null) // { idx, px } for crosshair+tooltip
  const svgRef = useRef(null)

  const model = useMemo(() => {
    if (!data?.series?.length) return null
    const { years, series } = data
    const colors = assignColors(series)
    const enriched = series.map((s) => {
      const known = s.points.filter((p) => p.power != null)
      return { country: s.country, color: colors[s.country], known,
               current: known.length ? known[known.length - 1].power : null }
    })
    // Legend order = strongest right now (the page's whole question).
    const ranked = [...enriched].filter((s) => s.current != null)
      .sort((a, b) => b.current - a.current)
    return { years, series: enriched, ranked }
  }, [data])

  if (loading) return <p className="muted">Loading timeline…</p>
  if (error || !model) return null

  const { years, series, ranked } = model
  const W = 900, H = 420
  const PAD = { l: 46, r: 18, t: 18, b: 32 }
  const allVals = series.flatMap((s) => s.known.map((p) => p.power))
  const yMin = Math.min(...allVals) * 0.98
  const yMax = Math.max(...allVals) * 1.02
  const y0 = years[0], yN = years[years.length - 1]
  const X = (yr) => PAD.l + ((yr - y0) / Math.max(1, yN - y0)) * (W - PAD.l - PAD.r)
  const Y = (v) => H - PAD.b - ((v - yMin) / (yMax - yMin || 1)) * (H - PAD.t - PAD.b)
  const linePath = (known) =>
    known.map((p, i) => `${i ? 'L' : 'M'}${X(p.year).toFixed(1)},${Y(p.power).toFixed(1)}`).join(' ')
  const areaPath = (known) =>
    `${linePath(known)} L${X(known[known.length - 1].year).toFixed(1)},${(H - PAD.b).toFixed(1)}` +
    ` L${X(known[0].year).toFixed(1)},${(H - PAD.b).toFixed(1)} Z`

  const ticks = Array.from({ length: 5 }, (_, k) => Math.round(yMin + (k / 4) * (yMax - yMin)))
  const step = Math.ceil(years.length / 9)
  const xYears = years.filter((_, i) => i % step === 0 || i === years.length - 1)

  const onMove = (e) => {
    const rect = svgRef.current.getBoundingClientRect()
    const relX = (e.clientX - rect.left) / rect.width
    const frac = Math.min(1, Math.max(0, (relX * W - PAD.l) / (W - PAD.l - PAD.r)))
    const idx = Math.round(frac * (years.length - 1))
    // keep the tooltip fully inside the plot
    const px = Math.min(Math.max(e.clientX - rect.left, 60), rect.width - 60)
    setCursor({ idx, px })
  }

  const hoverYear = cursor ? years[cursor.idx] : null
  const readout = cursor
    ? series.map((s) => ({ ...s, v: valueAt(s.known, hoverYear) }))
        .filter((s) => s.v != null).sort((a, b) => b.v - a.v)
    : []

  return (
    <div className="tl">
      <div className="tl-plot">
        <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="chart tl-chart" role="img"
             aria-label={`${cup} cup team power by year`}
             onMouseMove={onMove} onMouseLeave={() => setCursor(null)}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={PAD.l} x2={W - PAD.r} y1={Y(t)} y2={Y(t)} className="grid" />
              <text x={PAD.l - 8} y={Y(t) + 4} className="axis" textAnchor="end">{fmtK(t)}</text>
            </g>
          ))}
          {xYears.map((yr, i) => (
            <text key={yr} x={X(yr)} y={H - 9} className="axis"
                  textAnchor={i === 0 ? 'start' : yr === yN ? 'end' : 'middle'}>{yr}</text>
          ))}

          {/* crosshair + per-line markers at the hovered year */}
          {cursor && (
            <line x1={X(hoverYear)} x2={X(hoverYear)} y1={PAD.t} y2={H - PAD.b}
                  className="tl-cursor" />
          )}

          {series.map((s) => {
            const dim = hi != null && hi !== s.country
            const emph = hi === s.country
            return (
              <g key={s.country} opacity={dim ? 0.1 : 1}
                 onMouseEnter={() => setHi(s.country)} onMouseLeave={() => setHi(null)}>
                {emph && (
                  <path d={areaPath(s.known)} fill={s.color} fillOpacity="0.13" stroke="none" />
                )}
                <path d={linePath(s.known)} fill="none" stroke={s.color}
                      strokeWidth={emph ? 3.75 : 2.25} className={`tl-line ${emph ? 'emph' : ''}`} />
              </g>
            )
          })}

          {cursor && readout.map((s) => (
            <circle key={s.country} cx={X(hoverYear)} cy={Y(s.v)} r={hi === s.country ? 4 : 3}
                    fill={s.color} stroke="var(--surface)" strokeWidth="1.5" />
          ))}

          {/* direct-label only the emphasised line's endpoint (no collisions) */}
          {hi && (() => {
            const s = series.find((x) => x.country === hi)
            const last = s?.known[s.known.length - 1]
            return last ? (
              <text x={X(last.year) - 6} y={Y(last.power) - 8} className="tl-emph"
                    fill={s.color} textAnchor="end">{flag(hi)} {hi}</text>
            ) : null
          })()}
        </svg>

        {cursor && readout.length > 0 && (
          <div className="tl-tip" style={{ left: `${cursor.px}px` }}>
            <div className="tl-tip-year">{hoverYear}</div>
            {readout.map((s) => (
              <div key={s.country} className={`tl-tip-row ${hi === s.country ? 'on' : ''}`}>
                <span className="tl-key" style={{ background: s.color }} />
                <span className="tl-tip-v">{fmtK(s.v)}</span>
                <span className="tl-tip-c">{s.country}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* legend = strongest right now; identity carried by code, not colour alone */}
      <ol className="tl-legend">
        {ranked.map((s, i) => (
          <li key={s.country} className={hi === s.country ? 'on' : ''}
              onMouseEnter={() => setHi(s.country)} onMouseLeave={() => setHi(null)}>
            <span className="tl-rank">{i + 1}</span>
            <span className="tl-key" style={{ background: s.color }} />
            <span className="tl-fl">{flag(s.country)}</span>
            <span className="tl-cc">{s.country}</span>
            <span className="tl-now">{fmtK(s.current)}</span>
          </li>
        ))}
      </ol>

      <p className="muted small tl-note">
        Summed rating of each nation's strongest team by year (top {series.length} all-time),
        reconstructed from the players active that season. Legend is ranked by
        <strong> current</strong> power — hover the chart for any year, or a nation to isolate it.
      </p>
    </div>
  )
}
