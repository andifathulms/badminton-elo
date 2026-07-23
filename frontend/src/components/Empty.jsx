// Consistent empty and error states — a centered icon + message, so "nothing
// here" and "something broke" read as intentional design rather than bare text.

export function EmptyState({ icon = '🔍', title = 'Nothing here yet', hint }) {
  return (
    <div className="empty">
      <div className="empty-icon" aria-hidden="true">{icon}</div>
      <div className="empty-title">{title}</div>
      {hint && <p className="empty-hint">{hint}</p>}
    </div>
  )
}

export function ErrorState({ error, onRetry, what = 'this' }) {
  return (
    <div className="empty">
      <div className="empty-icon" aria-hidden="true">⚠️</div>
      <div className="empty-title">Couldn’t load {what}</div>
      <p className="empty-hint">{error?.message || 'Something went wrong.'}</p>
      {onRetry && (
        <button className="pgbtn" onClick={onRetry}>Try again</button>
      )}
    </div>
  )
}
