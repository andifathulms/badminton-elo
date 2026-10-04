import { confidence, uncertainty } from '../confidence.js'

// Certainty meter: three bars (settled / firming up / provisional) driven by the
// rating deviation. The label shows when asked, and always for provisional
// ratings so uncertain numbers are called out. Hover gives the exact ±.
export default function Confidence({ rd, showLabel = false }) {
  const c = confidence(rd)
  const label = showLabel || c.level === 'low'
  return (
    <span className={`conf conf-${c.level}`}
          title={`${c.label} · rating is accurate to about ±${uncertainty(rd)}`}>
      <span className="conf-bars" aria-hidden="true"><i /><i /><i /></span>
      {label && <span className="conf-label">{c.label}</span>}
    </span>
  )
}
