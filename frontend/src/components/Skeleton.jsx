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
