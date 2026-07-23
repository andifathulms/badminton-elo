// Lightweight loading placeholders that echo the real layout, so pages feel
// instant instead of flashing "Loading…". Theme-aware (uses surface tokens).

export function Skeleton({ w = '100%', h = 14, r = 8, style }) {
  return <span className="skeleton" style={{ width: w, height: h, borderRadius: r, display: 'block', ...style }} />
}

// A stand-in for a ranked list / table body: avatar + two text lines + a metric.
export function SkeletonList({ rows = 8 }) {
  return (
    <div className="sk-list" aria-hidden="true">
      {Array.from({ length: rows }).map((_, i) => (
        <div className="sk-row" key={i}>
          <span className="skeleton sk-rank" />
          <span className="skeleton sk-avatar" />
          <span className="sk-lines">
            <Skeleton w="52%" h={12} />
            <Skeleton w="30%" h={10} />
          </span>
          <span className="skeleton sk-metric" />
        </div>
      ))}
    </div>
  )
}

// A stand-in for a hero header (green banner) plus a block of content below.
export function MatchSkeleton() {
  return (
    <div aria-hidden="true">
      <div className="sk-hero"><Skeleton w="42%" h={24} style={{ background: 'rgba(255,255,255,.25)' }} /></div>
      <div className="sk-panel" style={{ marginTop: 18 }}>
        <Skeleton w="100%" h={90} r={12} />
      </div>
      <SkeletonList rows={4} />
    </div>
  )
}

// A stand-in for the tournament detail page (hero + tabs + match rows).
export function TournamentSkeleton() {
  return (
    <div aria-hidden="true">
      <div className="sk-hero"><Skeleton w="52%" h={26} style={{ background: 'rgba(255,255,255,.25)' }} /></div>
      <div style={{ display: 'flex', gap: 8, margin: '18px 0' }}>
        {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} w={66} h={44} r={10} />)}
      </div>
      <SkeletonList rows={6} />
    </div>
  )
}

// A stand-in for the dashboard's reigning-#1 cards.
export function SkeletonCards({ count = 5 }) {
  return (
    <div className="champ-grid" aria-hidden="true">
      {Array.from({ length: count }).map((_, i) => (
        <div className="sk-card" key={i}>
          <span className="skeleton" style={{ width: 64, height: 64, borderRadius: 20 }} />
          <Skeleton w="70%" h={12} />
          <Skeleton w="40%" h={20} />
        </div>
      ))}
    </div>
  )
}
