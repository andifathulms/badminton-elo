// Shared page header: a quiet title block (no banner) so content starts above
// the fold. `kicker` is a breadcrumb-style eyebrow; `children` render on the
// right (filters, controls).
export default function PageHeader({ kicker, title, subtitle, children }) {
  return (
    <header className="phead">
      <div className="phead-text">
        {kicker && <div className="kicker">{kicker}</div>}
        <h1>{title}</h1>
        {subtitle && <p className="phead-sub">{subtitle}</p>}
      </div>
      {children && <div className="phead-aside">{children}</div>}
    </header>
  )
}
