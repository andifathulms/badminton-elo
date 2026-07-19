import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import { useAsync } from '../useAsync.js'
import Select from '../components/Select.jsx'
import Pager from '../components/Pager.jsx'
import PageHeader from '../components/PageHeader.jsx'

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

// Grouped, prestige-ordered overview for one year — multi-sport & championships
// on top, then team cups, World Tour, development. Lets you eyeball what's
// missing (a row with 0 matches = no draw data ingested yet).
function MasterView({ year }) {
  const { data, error, loading } = useAsync(() => api.tournamentMaster(year), [year])
  if (loading) return <p className="muted">Loading {year}…</p>
  if (error) return <p className="error">Could not load: {error.message}</p>
  if (!data?.results?.length) return <p className="muted">No tournaments for {year}.</p>

  // group consecutive rows by their section label (already prestige-sorted)
  const sections = []
  for (const t of data.results) {
    if (!sections.length || sections[sections.length - 1].group !== t.group)
      sections.push({ group: t.group, rows: [] })
    sections[sections.length - 1].rows.push(t)
  }
  const withData = data.results.filter((t) => t.match_count > 0).length

  return (
    <div>
      <p className="muted small" style={{ margin: '0 0 14px' }}>
        <strong>{year}</strong> — {data.count} tournaments, {withData} with match data.
        Rows with <span className="nodata-dot">0</span> matches have no draw ingested yet.
      </p>
      {sections.map((s) => (
        <div key={s.group} className="master-section">
          <h3 className="master-head">{s.group} <span className="muted small">· {s.rows.length}</span></h3>
          <table className="board compact">
            <tbody>
              {s.rows.map((t) => (
                <tr key={t.tournament_id} className={t.match_count ? '' : 'nodata'}>
                  <td className="tier-cell"><span className="tier-tag">{shortTier(t.category_name) || '—'}</span></td>
                  <td>
                    <Link to={`/tournaments/${t.tournament_id}`}>{t.name}</Link>
                    {isOngoing(t) && <span className="badge-live">● Live</span>}
                    {t.venue_name && <span className="muted small"> · {t.venue_name}</span>}
                  </td>
                  <td className="num muted small nowrap">{dates(t)}</td>
                  <td className="num">
                    {t.match_count
                      ? <span className="metric">{t.match_count}</span>
                      : <span className="nodata-dot">0</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  )
}

function FlatList({ year, tier }) {
  const [page, setPage] = useState(0)
  useEffect(() => setPage(0), [year, tier])
  const { data, error, loading } = useAsync(
    () => api.tournaments({ year, tier, limit: PAGE, offset: page * PAGE }),
    [year, tier, page])
  if (loading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">Could not load: {error.message}</p>
  if (!data) return null
  return (
    <>
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
      <Pager page={page} setPage={setPage} count={data.count} pageSize={PAGE} unit="tournaments" />
      {data.results.length === 0 && <p className="muted">No tournaments match.</p>}
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
