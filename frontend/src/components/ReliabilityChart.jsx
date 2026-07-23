// Reliability diagram: predicted win probability (x) vs actual win rate (y) per
// bucket, against the y=x "perfectly calibrated" diagonal. Points on the line
// mean the rating's confidence matches reality. Inline SVG — no chart library.
const W = 420
const H = 420
const PAD = { top: 18, right: 18, bottom: 40, left: 44 }

export default function ReliabilityChart({ bins }) {
  const pts = (bins || []).filter((b) => b.n && b.predicted != null && b.actual != null)
  if (pts.length === 0) return <p className="muted">Not enough data.</p>

  const innerW = W - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom
  // Both axes span the meaningful favorite range [0.5, 1.0].
  const lo = 0.5
  const x = (v) => PAD.left + ((v - lo) / (1 - lo)) * innerW
  const y = (v) => PAD.top + innerH - ((v - lo) / (1 - lo)) * innerH
  const maxN = Math.max(...pts.map((b) => b.n))

  const ticks = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
  const line = pts.map((b) => `${x(b.predicted)},${y(b.actual)}`).join(' ')

  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img"
           aria-label="Reliability diagram">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={PAD.top} y2={PAD.top + innerH} className="grid" />
            <line x1={PAD.left} x2={PAD.left + innerW} y1={y(t)} y2={y(t)} className="grid" />
            <text x={x(t)} y={H - 22} className="axis" textAnchor="middle">
              {Math.round(t * 100)}%
            </text>
            <text x={PAD.left - 8} y={y(t) + 4} className="axis" textAnchor="end">
              {Math.round(t * 100)}%
            </text>
          </g>
        ))}

        {/* Perfectly-calibrated diagonal */}
        <line x1={x(lo)} y1={y(lo)} x2={x(1)} y2={y(1)} className="marker-line" />

        {/* Predicted-vs-actual, sized by sample count */}
        <polyline points={line} className="line" fill="none" />
        {pts.map((b) => (
          <circle key={b.bucket} cx={x(b.predicted)} cy={y(b.actual)}
                  r={4 + 7 * Math.sqrt(b.n / maxN)} className="now-dot">
            <title>{`predicted ${(b.predicted * 100).toFixed(1)}% · actual ${(b.actual * 100).toFixed(1)}% · ${b.n.toLocaleString()} matches`}</title>
          </circle>
        ))}

        <text x={PAD.left + innerW / 2} y={H - 4} className="axis" textAnchor="middle">
          Predicted win probability
        </text>
        <text transform={`translate(12 ${PAD.top + innerH / 2}) rotate(-90)`}
              className="axis" textAnchor="middle">
          Actual win rate
        </text>
      </svg>
      <p className="muted small">
        Dot size = number of matches. Points hugging the diagonal mean the rating’s
        confidence matches reality.
      </p>
    </div>
  )
}
