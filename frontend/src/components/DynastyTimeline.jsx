// Reign timeline: one horizontal bar spanning all years, split into segments —
// each an unbroken run where a single nation was #1 in the discipline. Segment
// width is proportional to the reign's length; colour is per country. A stable
// hash keeps a country the same colour across renders and disciplines.
import { flag } from '../flags.js'

function countryColor(cc) {
  let h = 0
  for (let i = 0; i < cc.length; i++) h = (h * 31 + cc.charCodeAt(i)) % 360
  return `hsl(${h} 52% 42%)`
}

export default function DynastyTimeline({ reigns, timeline }) {
  if (!reigns || reigns.length === 0) return <p className="muted">Not enough data.</p>
  // Chronological (reigns come sorted by span); rebuild in year order for the bar.
  const chrono = [...reigns].sort((a, b) => a.start - b.start)
  const first = chrono[0].start
  const last = chrono[chrono.length - 1].end
  const total = last - first + 1

  return (
    <div className="dynasty">
      <div className="dyn-bar">
        {chrono.map((r, i) => {
          const w = (r.span / total) * 100
          return (
            <div key={i} className="dyn-seg"
                 style={{ width: `${w}%`, background: countryColor(r.country) }}
                 title={`${r.country} ${r.start}–${r.end} (${r.span} yr${r.span > 1 ? 's' : ''})`}>
              {w > 6 && <span className="dyn-seg-label">{r.country}</span>}
            </div>
          )
        })}
      </div>
      <div className="dyn-axis">
        <span>{first}</span>
        <span>{Math.round((first + last) / 2)}</span>
        <span>{last}</span>
      </div>
    </div>
  )
}
