import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import { useAsync } from '../useAsync.js'
import { flag } from '../flags.js'
import PageHeader from '../components/PageHeader.jsx'
import CupTimeline from '../components/CupTimeline.jsx'
import { SkeletonList } from '../components/Skeleton.jsx'
import { EmptyState, ErrorState } from '../components/Empty.jsx'

const CUPS = [
  { key: 'thomas', label: 'Thomas Cup', sub: "Men's team · 3 MS + 2 MD" },
  { key: 'uber', label: 'Uber Cup', sub: "Women's team · 3 WS + 2 WD" },
  { key: 'sudirman', label: 'Sudirman Cup', sub: 'Mixed team · MS/WS/MD/WD/XD' },
]

// Discipline colours (validated categorical slots 1–5) — used for the power
// composition bar and the roster labels.
const DISC = { MS: '#2a78d6', WS: '#008300', MD: '#e87ba4', WD: '#eda100', XD: '#1baf7a' }
const DISC_ORDER = ['MS', 'WS', 'MD', 'WD', 'XD']
const bySlot = (a, b) =>
  DISC_ORDER.indexOf(a.event) - DISC_ORDER.indexOf(b.event) || b.rating - a.rating

// One nation: rank · flag · power, a composition bar (length = power vs the
// leader, segments = each slot's rating by discipline), and the roster.
function NationCard({ row, rank, maxPower }) {
  const slots = [...row.contributors].sort(bySlot)
  return (
    <div className="nat">
      <div className="nat-top">
        <span className={`medal ${rank <= 3 ? `m${rank}` : ''}`}>{rank}</span>
        <span className="nat-id">
          <span className="fl">{flag(row.country)}</span><b>{row.country}</b>
        </span>
        <span className="nat-power">
          <b>{row.power.toLocaleString()}</b><small>power</small>
        </span>
      </div>
      <div className="np-track" title="Bar length = power vs the leader">
        <div className="np-bar" style={{ width: `${(row.power / maxPower) * 100}%` }}>
          {slots.map((c, i) => (
            <span key={i} className="np-seg" style={{ flex: c.rating, background: DISC[c.event] }}
                  title={`${c.event} · ${c.rating}`} />
          ))}
        </div>
      </div>
      <div className="nat-roster">
        {slots.map((c, i) => (
          <div key={i} className="nat-slot">
            <span className="nat-disc" style={{ background: `${DISC[c.event]}22` }}>{c.event}</span>
            <span className="nat-players">
              {c.players.map((p, j) => (
                <span key={p.player_id}>
                  {j > 0 ? ' / ' : ''}
                  <Link to={`/players/${p.player_id}`}>{p.name_display}</Link>
                </span>
              ))}
            </span>
            <span className="nat-rating">{c.rating}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Cups() {
  const [cup, setCup] = useState('thomas')
  const { data, error, loading, reload } = useAsync(() => api.cup(cup), [cup])
  const meta = CUPS.find((c) => c.key === cup)

  return (
    <div>
      <PageHeader
        kicker="National Team Power"
        title="Cup Power"
        subtitle={
          <>Which country could field the strongest team <strong>right now</strong> —
          summed rating of each nation's top active players/pairs. Retired players
          (idle &gt; 1 year) don't count.</>
        }
      />

      <div className="tabs">
        {CUPS.map((c) => (
          <button key={c.key}
            className={`tab ${c.key === cup ? 'active' : ''}`}
            onClick={() => setCup(c.key)}>
            {c.label.split(' ')[0]}
            <span className="tab-label">{c.label.split(' ')[1]}</span>
          </button>
        ))}
      </div>
      <p className="muted small" style={{ marginTop: 8 }}>{meta.sub}</p>

      <h2>📈 Dominance over time</h2>
      <CupTimeline cup={cup} />

      <h2 style={{ marginTop: 24 }}>Current standings</h2>
      {loading && <SkeletonList rows={6} />}
      {error && <ErrorState error={error} onRetry={reload} what="the standings" />}
      {data && data.results.length > 0 && (
        <>
          <div className="disc-legend">
            {DISC_ORDER.map((d) => (
              <span key={d}><span className="dot" style={{ background: DISC[d] }} />{d}</span>
            ))}
          </div>
          <div className="nat-list">
            {data.results.slice(0, 24).map((row, i) => (
              <NationCard key={row.country} row={row} rank={i + 1}
                          maxPower={data.results[0].power} />
            ))}
          </div>
        </>
      )}
      {data && data.results.length === 0 && (
        <EmptyState icon="🏳️" title="No full teams"
          hint="No country currently has enough active players/pairs to field a complete team." />
      )}
    </div>
  )
}
