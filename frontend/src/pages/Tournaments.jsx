import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import { useAsync } from '../useAsync.js'
import Select from '../components/Select.jsx'
import Pager from '../components/Pager.jsx'
import PageHeader from '../components/PageHeader.jsx'
import { SkeletonList } from '../components/Skeleton.jsx'
import { EmptyState, ErrorState } from '../components/Empty.jsx'

const YEARS = Array.from({ length: 45 }, (_, i) => 2026 - i)
const YEAR_OPTS = [{ value: '', label: 'All years' }, ...YEARS.map((y) => ({ value: y, label: String(y) }))]
const PAGE = 40
const shortTier = (s) => (s || '').replace('HSBC BWF World Tour ', '').replace('BWF ', '')

function isOngoing(t) {
  if (!t.start_date) return false
  const today = new Date().toISOString().slice(0, 10)
  const end = t.end_date || t.start_date
  return t.start_date <= today && today <= end
}

function dates(t) {
  if (!t.start_date) return '—'
  return t.start_date + (t.end_date && t.end_date !== t.start_date ? ` → ${t.end_date.slice(5)}` : '')
}

function TournamentCard({ t }) {
  const initials = shortTier(t.category_name).split(' ').map((w) => w[0]).join('').slice(0, 3)
  return (
    <Link to={`/tournaments/${t.tournament_id}`}
          className={`tcard ${t.match_count ? '' : 'nodata'}`}>
      <div className="tcard-logo">
        {t.logo_url
          ? <img src={t.logo_url} alt="" loading="lazy" />
          : <span className="tcard-logo-ph">{initials || '🏸'}</span>}
      </div>
      <div className="tcard-body">
        <div className="tcard-name">{t.name}{isOngoing(t) && <span className="badge-live">● Live</span>}</div>
        <div className="tcard-meta">
          {dates(t)}{t.venue_name ? ` · ${t.venue_name}` : ''}
        </div>
      </div>
      <div className="tcard-count">
        {t.match_count ? <span className="metric">{t.match_count}</span>
          : <span className="nodata-dot">0</span>}
      </div>
    </Link>
  )
}

// Grouped, prestige-ordered overview for one year: collapsible sections
// (Multi-sport, Team events, World Tour, Development), each split into tier
// sub-groups holding a grid of tournament cards. A card with 0 matches has no
// draw data yet — the gap-spotter.
function MasterView({ year }) {
  const { data, error, loading, reload } = useAsync(() => api.tournamentMaster(year), [year])
  const [collapsed, setCollapsed] = useState({})
  if (loading) return <SkeletonList rows={8} />
  if (error) return <ErrorState error={error} onRetry={reload} what="tournaments" />
  if (!data?.results?.length) return (
    <EmptyState icon="🗓" title={`No tournaments for ${year}`}
      hint="Nothing has been ingested for this year yet." />
  )

  // section (group) -> tier (category_name) -> rows, preserving prestige order
  const sections = []
  for (const t of data.results) {
    let sec = sections[sections.length - 1]
    if (!sec || sec.group !== t.group) { sec = { group: t.group, tiers: [] }; sections.push(sec) }
    let tier = sec.tiers[sec.tiers.length - 1]
    if (!tier || tier.tier !== t.category_name) {
      tier = { tier: t.category_name, rows: [] }; sec.tiers.push(tier)
    }
    tier.rows.push(t)
  }
  const withData = data.results.filter((t) => t.match_count > 0).length

  return (
    <div>
      <p className="muted small" style={{ margin: '0 0 14px' }}>
        <strong>{year}</strong> — {data.count} tournaments, {withData} with match data.
        Cards with <span className="nodata-dot">0</span> have no draw ingested yet.
      </p>
      {sections.map((s) => {
        const n = s.tiers.reduce((a, t) => a + t.rows.length, 0)
        const isCollapsed = collapsed[s.group]
        return (
          <section key={s.group} className="master-section">
            <button className={`master-head ${isCollapsed ? 'collapsed' : ''}`}
                    aria-expanded={!isCollapsed}
                    onClick={() => setCollapsed((c) => ({ ...c, [s.group]: !c[s.group] }))}>
              <span className="master-head-title">{s.group}</span>
              <span className="master-head-count">{n}</span>
              <span className={`caret ${isCollapsed ? '' : 'open'}`}>▸</span>
            </button>
            {!isCollapsed && s.tiers.map((tier) => (
              <div key={tier.tier} className="tier-block">
                <div className="tier-sub">{shortTier(tier.tier) || '—'}
                  <span className="muted small"> · {tier.rows.length}</span></div>
                <div className="tcard-grid">
                  {tier.rows.map((t) => <TournamentCard key={t.tournament_id} t={t} />)}
                </div>
              </div>
            ))}
          </section>
        )
      })}
    </div>
  )
}

function FlatList({ year, tier }) {
  const [page, setPage] = useState(0)
  useEffect(() => setPage(0), [year, tier])
  const { data, error, loading, reload } = useAsync(
    () => api.tournaments({ year, tier, limit: PAGE, offset: page * PAGE }),
    [year, tier, page])
  if (loading) return <SkeletonList rows={10} />
  if (error) return <ErrorState error={error} onRetry={reload} what="tournaments" />
  if (!data) return null
  return (
    <>
      <div className="table-scroll">
      <table className="board">
        <thead>
          <tr><th>Tournament</th><th>Tier</th><th className="num">Dates</th><th className="num">Matches</th></tr>
        </thead>
        <tbody>
          {data.results.map((t) => (
            <tr key={t.tournament_id}>
              <td>
                <Link to={`/tournaments/${t.tournament_id}`}>{t.name}</Link>
                {isOngoing(t) && <span className="badge-live">● Live</span>}
              </td>
              <td className="muted small">{shortTier(t.category_name)}</td>
              <td className="num muted small nowrap">{dates(t)}</td>
              <td className="num muted">{t.match_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      {data.results.length > 0
        ? <Pager page={page} setPage={setPage} count={data.count} pageSize={PAGE} unit="tournaments" />
        : <EmptyState icon="🗓" title="No tournaments match"
            hint="Try a different year or tier filter." />}
    </>
  )
}

export default function Tournaments() {
  const [year, setYear] = useState('')
  const [tier, setTier] = useState('')
  const { data: tiers } = useAsync(() => api.tournamentTiers(), [])
  const tierOpts = [
    { value: '', label: 'All tiers' },
    ...(tiers || []).map((t) => ({ value: t.tier, label: `${shortTier(t.tier)} (${t.count})` })),
  ]
  // The master (grouped-by-prestige) view kicks in when a year is picked and no
  // tier filter is applied; otherwise the flat paginated list.
  const master = year && !tier

  return (
    <div>
      <PageHeader kicker="Tournament Master · 1983–now" title="Tournaments">
        <Select label="Tier" value={tier} onChange={setTier} options={tierOpts} />
        <Select label="Year" value={year} onChange={setYear} options={YEAR_OPTS} />
      </PageHeader>
      {!year && !tier && (
        <p className="muted small" style={{ marginTop: -6 }}>
          Pick a <strong>year</strong> to see every tournament ranked by prestige
          (Olympics &amp; championships on top) — a master view to spot gaps.
        </p>
      )}
      {master ? <MasterView year={year} /> : <FlatList year={year} tier={tier} />}
    </div>
  )
}
