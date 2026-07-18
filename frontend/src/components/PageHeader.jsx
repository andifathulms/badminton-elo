// Shared page header: a court-green card with white text used at the top of
// every page, so the whole app reads as one system. Optional `children` render
// on the right (filters, controls).
export default function PageHeader({ kicker, title, subtitle, children }) {
  return (
    <header className="page-hero">
      <div className="page-hero-text">
        {kicker && <div className="kicker">{kicker}</div>}
        <h1>{title}</h1>
        {subtitle && <p className="page-hero-sub">{subtitle}</p>}
      </div>
      {children && <div className="page-hero-aside">{children}</div>}
    </header>
  )
}
