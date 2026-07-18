import { api } from '../api.js'
import { useAsync } from '../useAsync.js'

const EVENT_LABEL = { MS: "Men's S", WS: "Women's S", MD: "Men's D", WD: "Women's D", XD: 'Mixed D' }

// "Playing style" — average rallies per match & average match length, per
// discipline. Reveals who grinds out long rallies vs who ends points fast.
// Pass `partner` to scope it to one pairing's matches.
export default function StyleCard({ playerId, partner, title = 'Playing style' }) {
  const { data, loading, error } = useAsync(
    () => api.playerStyle(playerId, partner), [playerId, partner])

  if (loading) return <p className="muted small">Loading style…</p>
  if (error || !data?.style?.length) return null

  return (
    <div className="style-card">
      <div className="style-head">
        <h2 style={{ margin: 0 }}>{title}</h2>
        <span className="muted small">avg per Normal match with rally data</span>
      </div>
      <div className="style-grid">
        {data.style.map((s) => (
          <div key={s.event} className="style-cell">
            <div className="style-event">{EVENT_LABEL[s.event] || s.event}</div>
            <div className="style-nums">
              <div><b>{s.avg_rallies}</b><span> rallies</span></div>
              <div><b>{s.avg_duration}</b><span> min</span></div>
            </div>
            <div className="muted small">{s.matches} match{s.matches === 1 ? '' : 'es'}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
