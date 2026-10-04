import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api.js'
import { useAsync } from '../useAsync.js'
import Select from '../components/Select.jsx'
import Pager from '../components/Pager.jsx'
import PageHeader from '../components/PageHeader.jsx'
import { SkeletonList } from '../components/Skeleton.jsx'
import { EmptyState, ErrorState } from '../components/Empty.jsx'
import Tier from '../components/Tier.jsx'
import Icon from '../components/Icon.jsx'
import { fmtRange, isLive } from '../dates.js'

const YEARS = Array.from({ length: 45 }, (_, i) => 2026 - i)
const YEAR_OPTS = [{ value: '', label: 'All years' }, ...YEARS.map((y) => ({ value: y, label: String(y) }))]
const PAGE = 40
const shortTier = (s) => (s || '').replace('HSBC BWF World Tour ', '').replace('BWF ', '')

const isOngoing = isLive
const dates = (t) => (t.start_date ? fmtRange(t.start_date, t.end_date) : '—')
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function TournamentCard({ t }) {
  const initials = shortTier(t.category_name).split(' ').map((w) => w[0]).join('').slice(0, 3)
  return (
    <Link to={`/tournaments/${t.tournament_id}`}
          className={`tcard ${t.match_count ? '' : 'nodata'}`}>
      <div className="tcard-logo">
        {t.logo_url && !/placeholder/i.test(t.logo_url)
          ? <img src={t.logo_url} alt="" loading="lazy" onError={(e) => { e.currentTarget.style.display = 'none' }} />
          : <span className="tcard-logo-ph">{initials || <Icon name="trophy" size={18} />}</span>}
      </div>
      <div className="tcard-body">
        <div className="tcard-name">{t.name}</div>
        <div className="tcard-meta">
          {isOngoing(t) && <span className="live">LIVE</span>} {dates(t)}{t.venue_name ? ` · ${t.venue_name}` : ''}
        </div>
      </div>
      <div className="tcard-count">
        {t.match_count ? <span className="mono muted">{t.match_count}</span>
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
    <EmptyState icon="calendar" title={`No tournaments for ${year}`}
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
              <span className="master-head-title">{s.group.replace(/^[^\p{L}\p{N}]+/u, '')}</span>
              <span className="master-head-count">{n}</span>
              <span className={`caret ${isCollapsed ? '' : 'open'}`}><Icon name="arrowRight" size={13} /></span>
            </button>
            {!isCollapsed && s.tiers.map((tier) => (
              <div key={tier.tier} className="tier-block">
                <div className="tier-sub"><Tier category={tier.tier} title={tier.tier} />
                  <span>{shortTier(tier.tier) || '—'} · {tier.rows.length}</span></div>
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

function FlatList({ year, tier, q }) {
  const [page, setPage] = useState(0)
  useEffect(() => setPage(0), [year, tier, q])
  const { data, error, loading, reload } = useAsync(
    () => api.tournaments({ year, tier, q, limit: PAGE, offset: page * PAGE }),
    [year, tier, q, page])
  if (loading) return <SkeletonList rows={10} />
  if (error) return <ErrorState error={error} onRetry={reload} what="tournaments" />
  if (!data) return null
  if (!data.results.length) {
    return <EmptyState icon="calendar" title="No tournaments match" hint="Try a different year, tier or search." />
  }
  // Group consecutive rows by start month — a calendar you can scan.
  const groups = []
  for (const t of data.results) {
    const key = (t.start_date || '').slice(0, 7)
    let g = groups[groups.length - 1]
    if (!g || g.key !== key) { g = { key, rows: [] }; groups.push(g) }
    g.rows.push(t)
  }
  return (
    <>
      {groups.map((g) => (
        <section key={g.key || 'none'} className="cal-month">
          <h3 className="cal-h">{g.key ? `${MONTHS[+g.key.slice(5, 7) - 1]} ${g.key.slice(0, 4)}` : 'Undated'}</h3>
          <div className="cal-list card">
            {g.rows.map((t) => (
              <Link key={t.tournament_id} to={`/tournaments/${t.tournament_id}`} className="cal-row">
                <span className={`cal-date ${isOngoing(t) ? 'live-d' : ''}`}>
                  <b>{t.start_date ? +t.start_date.slice(8, 10) : '–'}</b>
                  <span>{t.start_date ? MON[+t.start_date.slice(5, 7) - 1] : ''}</span>
                </span>
                <span className="cal-main">
                  <span className="cal-nm">{t.name}</span>
                  <span className="cal-sub">
                    {isOngoing(t) && <span className="live">LIVE</span>}
                    <span>{dates(t)}</span>{t.venue_name && <span>· {t.venue_name}</span>}
                  </span>
                </span>
                <Tier category={t.category_name} />
                <span className="cal-n mono">{t.match_count} <span>matches</span></span>
              </Link>
            ))}
          </div>
        </section>
      ))}
      <Pager page={page} setPage={setPage} count={data.count} pageSize={PAGE} unit="tournaments" />
    </>
  )
}

export default function Tournaments() {
  const [params, setParams] = useSearchParams()
  const year = params.get('year') || ''
  const tier = params.get('tier') || ''
  const q = params.get('q') || ''
  const [draft, setDraft] = useState(q)
  useEffect(() => setDraft(q), [q])
  const set = (k, v) => {
    const next = Object.fromEntries(params.entries())
    if (v) next[k] = v; else delete next[k]
    setParams(next)
  }
  // Debounced search into the URL.
  useEffect(() => {
    if (draft === q) return
    const t = setTimeout(() => set('q', draft.trim()), 300)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft])
  const { data: tiers } = useAsync(() => api.tournamentTiers(), [])
  const tierOpts = [
    { value: '', label: 'All tiers' },
    ...(tiers || []).map((t) => ({ value: t.tier, label: `${shortTier(t.tier)} (${t.count})` })),
  ]
  // The master (grouped-by-prestige) view kicks in when a year is picked and no
  // tier filter or search is applied; otherwise the month-grouped calendar.
  const master = year && !tier && !q

  return (
    <div>
      <PageHeader kicker="Tournaments · 1983 to now" title="Tournaments"
        subtitle={master ? 'Every tournament of the year, grouped by prestige. Cards marked 0 have no results collected yet.' : 'Every collected event, newest first. Pick a year for the full season by prestige.'}>
        <label className="t-search">
          <Icon name="search" size={15} />
          <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Find a tournament" aria-label="Find a tournament" />
        </label>
        <Select label="Tier" value={tier} onChange={(v) => set('tier', v)} options={tierOpts} />
        <Select label="Year" value={year} onChange={(v) => set('year', String(v || ''))} options={YEAR_OPTS} />
      </PageHeader>
      {master ? <MasterView year={year} /> : <FlatList year={year} tier={tier} q={q} />}
    </div>
  )
}
