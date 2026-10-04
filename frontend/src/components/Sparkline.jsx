// Tiny trend line with an area fill and an emphasised endpoint.
export default function Sparkline({ values, width = 96, height = 28, className = '' }) {
  const v = (values || []).filter((x) => x != null)
  if (v.length < 2) return <span className={`spark spark-empty ${className}`} style={{ width, height }} />
  const mn = Math.min(...v), mx = Math.max(...v), r = mx - mn || 1
  const pts = v.map((y, i) => [2 + (i * (width - 6)) / (v.length - 1), height - 4 - ((y - mn) / r) * (height - 8)])
  const d = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join('')
  const [lx, ly] = pts[pts.length - 1]
  const up = v[v.length - 1] >= v[0]
  return (
    <svg className={`spark ${up ? 'up' : 'down'} ${className}`} viewBox={`0 0 ${width} ${height}`}
         width={width} height={height} aria-hidden="true">
      <path className="spark-a" d={`${d}L${lx.toFixed(1)} ${height}L2 ${height}Z`} />
      <path className="spark-l" d={d} />
      <circle className="spark-d" cx={lx.toFixed(1)} cy={ly.toFixed(1)} r="2.6" />
    </svg>
  )
}
