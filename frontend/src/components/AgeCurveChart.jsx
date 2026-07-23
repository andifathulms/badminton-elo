// Aging curve: bars = how many players peaked at each age, line = the average
// peak rating reached at that age. The two tell different stories — most players
// peak young (they're transient), but the highest ratings come later. A dashed
// marker shows the median peak age. Inline SVG, no chart library.
const W = 620
const H = 340
const PAD = { top: 22, right: 46, bottom: 42, left: 44 }

export default function AgeCurveChart({ bins, medianAge }) {
  const pts = (bins || []).filter((b) => b.count >= 3)
  if (pts.length < 2) return <p className="muted">Not enough data.</p>

  const ages = pts.map((b) => b.age)
  const aMin = Math.min(...ages)
  const aMax = Math.max(...ages)
  const maxCount = Math.max(...pts.map((b) => b.count))
  const mus = pts.map((b) => b.avg_peak)
  const muMin = Math.min(...mus)
  const muMax = Math.max(...mus)
  const muPad = (muMax - muMin) * 0.1 || 20

  const innerW = W - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom
  const span = aMax - aMin || 1
  const x = (a) => PAD.left + ((a - aMin) / span) * innerW
  const yCount = (c) => PAD.top + innerH - (c / maxCount) * innerH
  const yMu = (m) =>
    PAD.top + innerH - ((m - (muMin - muPad)) / ((muMax + muPad) - (muMin - muPad))) * innerH
  const bw = Math.max(4, (innerW / pts.length) * 0.62)

  const line = pts.map((b) => `${x(b.age)},${yMu(b.avg_peak)}`).join(' ')
  const muTicks = 4
  const muTickVals = Array.from({ length: muTicks + 1 }, (_, k) =>
    Math.round(muMin - muPad + (k / muTicks) * ((muMax + muPad) - (muMin - muPad))))

  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img"
           aria-label="Peak rating by age">
        {muTickVals.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={W - PAD.right} y1={yMu(t)} y2={yMu(t)} className="grid" />
            <text x={W - PAD.right + 6} y={yMu(t) + 4} className="axis" textAnchor="start">{t}</text>
          </g>
        ))}

        {pts.map((b) => (
          <rect key={b.age} x={x(b.age) - bw / 2} y={yCount(b.count)}
                width={bw} height={PAD.top + innerH - yCount(b.count)}
                className="age-bar">
            <title>{`age ${b.age}: ${b.count} players peaked, avg peak ${b.avg_peak}`}</title>
          </rect>
        ))}

        {medianAge != null && (
          <g>
            <line x1={x(medianAge)} x2={x(medianAge)} y1={PAD.top} y2={PAD.top + innerH}
                  className="marker-line" />
            <text x={x(medianAge)} y={PAD.top - 6} className="marker-label" textAnchor="middle">
              median {medianAge}
            </text>
          </g>
        )}

        <polyline points={line} className="line" fill="none" />
        {pts.map((b) => (
          <circle key={b.age} cx={x(b.age)} cy={yMu(b.avg_peak)} r={2.5} className="dot" />
        ))}

        {[aMin, Math.round((aMin + aMax) / 2), aMax].map((a) => (
          <text key={a} x={x(a)} y={H - 22} className="axis" textAnchor="middle">{a}</text>
        ))}
        <text x={PAD.left + innerW / 2} y={H - 4} className="axis" textAnchor="middle">
          Age at peak
        </text>
      </svg>
      <p className="muted small">
        Bars = players who peaked at that age · line = average peak rating reached
        (right axis).
      </p>
    </div>
  )
}
