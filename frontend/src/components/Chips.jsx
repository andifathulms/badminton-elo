// Small result atoms shared across pages.

// Rating change: +12.2 (green) / −11.7 (slate).
export function Delta({ value, digits = 1, className = '' }) {
  if (value == null || Number.isNaN(value)) return null
  const up = value >= 0
  return (
    <span className={`delta ${up ? 'up' : 'dn'} ${className}`}>
      {up ? '+' : '−'}{Math.abs(value).toFixed(digits)}
    </span>
  )
}

// Games as chips, oriented to the subject (`games` = [[mine, theirs], …]).
export function ScoreChips({ games }) {
  return (
    <span className="scores">
      {(games || []).map(([a, b], i) => (
        <span key={i} className={`sc${a > b ? ' w' : ''}`}>{a}–{b}</span>
      ))}
    </span>
  )
}

// W / L badge.
export function WL({ won }) {
  return <span className={`wl ${won ? 'w' : 'l'}`} aria-label={won ? 'Won' : 'Lost'}>{won ? 'W' : 'L'}</span>
}

// Discipline code chip (MS, XD…).
export function Ev({ code }) {
  return <span className="ev">{code}</span>
}

// Rank movement arrow: ▲3 / ▼2 / new.
export function Move({ value }) {
  if (value == null) return <span className="move new" title="New to the rankings">new</span>
  if (value === 0) return <span className="move same" title="No change">–</span>
  const up = value > 0
  return (
    <span className={`move ${up ? 'up' : 'dn'}`} title={`${up ? 'Up' : 'Down'} ${Math.abs(value)} in 4 weeks`}>
      {up ? '▲' : '▼'}{Math.abs(value)}
    </span>
  )
}
