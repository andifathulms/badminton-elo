import Icon from './Icon.jsx'

// Consistent empty and error states — a centred icon + message, so "nothing
// here" and "something broke" read as intentional design rather than bare text.
// `icon` is an Icon name (see Icon.jsx).
export function EmptyState({ icon = 'search', title = 'Nothing here yet', hint, children }) {
  return (
    <div className="empty">
      <div className="empty-icon" aria-hidden="true"><Icon name={icon} size={22} /></div>
      <div className="empty-title">{title}</div>
      {hint && <p className="empty-hint">{hint}</p>}
      {children}
    </div>
  )
}

export function ErrorState({ error, onRetry, what = 'this' }) {
  return (
    <div className="empty">
      <div className="empty-icon err" aria-hidden="true"><Icon name="info" size={22} /></div>
      <div className="empty-title">Couldn’t load {what}</div>
      <p className="empty-hint">{error?.message || 'Something went wrong.'} Check your connection and try again.</p>
      {onRetry && (
        <button className="pgbtn" onClick={onRetry}>Try again</button>
      )}
    </div>
  )
}
