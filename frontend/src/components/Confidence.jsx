import { confidence } from '../confidence.js'

// A small confidence indicator driven by rating deviation (rd): a coloured dot
// always, plus the label text when `showLabel` (or always for the provisional
// end, so uncertain ratings are called out). Hover shows the exact rd.
export default function Confidence({ rd, showLabel = false }) {
  const c = confidence(rd)
  const label = showLabel || c.level === 'low'
  return (
    <span className={`conf conf-${c.level}`}
          title={`${c.label} — rating deviation ±${Math.round(rd)} (${c.level} confidence)`}>
      <span className="conf-dot" />
      {label && <span className="conf-label">{c.label}</span>}
    </span>
  )
}
