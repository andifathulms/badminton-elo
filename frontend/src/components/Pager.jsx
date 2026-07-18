// Generic offset pager. Shows "from–to of N" with Prev/Next.
export default function Pager({ page, setPage, count, pageSize = 20, unit = '' }) {
  const pages = Math.ceil((count || 0) / pageSize)
  if (pages <= 1) return null
  const from = page * pageSize + 1
  const to = Math.min((page + 1) * pageSize, count)
  return (
    <div className="pager">
      <button className="pgbtn" disabled={page <= 0} onClick={() => setPage(page - 1)}>
        ← Prev
      </button>
      <span className="muted small">
        {from.toLocaleString()}–{to.toLocaleString()} of {count.toLocaleString()}
        {unit ? ` ${unit}` : ''}
      </span>
      <button className="pgbtn" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>
        Next →
      </button>
    </div>
  )
}
