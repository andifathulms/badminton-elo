import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, EVENTS } from '../api.js'
import { useAsync } from '../useAsync.js'
import Avatar from '../components/Avatar.jsx'
import { flag } from '../flags.js'

const nameOf = (players) => players.map((p) => p.name_display).join(' / ')

// Panel wrapper with a title and an optional "view all" link.
function Panel({ title, to, linkText, children }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>{title}</h2>
        {to && <Link to={to} className="view-all">{linkText || 'View all'} →</Link>}
      </div>
      {children}
    </section>
  )
}

function ReigningChamps() {
  const { data } = useAsync(
    () => Promise.all(
      EVENTS.map((e) =>
        api.leaderboard(e.code, { limit: 1, minMatches: 5 })
          .then((d) => ({ event: e, row: d.results[0] })),
      ),
    ),
    [],
  )
  if (!data) return <div className="champ-grid loading" />
  return (
    <div className="champ-grid">
      {data.filter((d) => d.row).map(({ event, row }) => (
        <Link key={event.code} to={`/players/${row.player.player_id}`} className="champ-card">
          <div className="champ-badge">{event.code}</div>
          <Avatar player={row.player} size="lg" />
          <div className="champ-name">{row.player.name_display}</div>
          <div className="champ-sub">
            <span className="fl">{flag(row.player.country_code)}</span>
            {row.player.country_code}
          </div>
          <div className="champ-rating">{row.rating.toFixed(0)}</div>
          <div className="champ-label">{event.label}</div>
        </Link>
      ))}
    </div>
  )
}

function MiniBoard() {
  const [event, setEvent] = useState('MS')
  const { data, loading } = useAsync(
    () => api.leaderboard(event, { limit: 5, minMatches: 5 }),
    [event],
  )
  return (
    <Panel title="Top of the table" to="/rankings" linkText="Full rankings">
      <div className="mini-tabs">
        {EVENTS.map((e) => (
          <button key={e.code}
            className={`mini-tab ${e.code === event ? 'active' : ''}`}
            onClick={() => setEvent(e.code)}>{e.code}</button>
        ))}
      </div>
      {loading && <p className="muted small">Loading…</p>}
      {data && (
        <ol className="mini-list">
          {data.results.map((row, i) => (
            <li key={row.player.player_id}>
              <span className={`medal sm ${i < 3 ? `m${i + 1}` : ''}`}>{i + 1}</span>
              <Link to={`/players/${row.player.player_id}`} className="pcell">
                <Avatar player={row.player} size="sm" />
                <span className="pname">{row.player.name_display}</span>
              </Link>
              <span className="fl">{flag(row.player.country_code)}</span>
              <span className="mini-rating">{row.rating.toFixed(0)}</span>
            </li>
          ))}
        </ol>
      )}
    </Panel>
  )
}

function RecentTournaments() {
  const { data, loading } = useAsync(() => api.tournaments({ limit: 6 }), [])
  return (
    <Panel title="Recent tournaments" to="/tournaments">
      {loading && <p className="muted small">Loading…</p>}
      {data && (
        <ul className="recent-list">
          {data.results.map((t) => (
            <li key={t.tournament_id}>
              <Link to={`/tournaments/${t.tournament_id}`}>
                <span className="rt-name">{t.name}</span>
                <span className="rt-meta">
                  {(t.category_name || '').replace('HSBC BWF World Tour ', '')}
                  {' · '}{t.start_date}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}

function BiggestUpsets() {
  const { data, loading } = useAsync(
    () => api.analytics('upsets', { minMatches: 3, limit: 5 }),
    [],
  )
  return (
    <Panel title="⚡ Biggest upsets" to="/insights" linkText="More insights">
      {loading && <p className="muted small">Loading…</p>}
      {data && (
        <ul className="upset-list">
          {data.results.map((row, i) => (
            <li key={`${row.player.player_id}-${row.tournament.tournament_id}`}>
              <span className="up-delta pos">+{row.best_delta.toFixed(0)}</span>
              <span className="up-body">
                <Link to={`/players/${row.player.player_id}`} className="up-name">
                  {row.player.name_display}
                  {row.partner && ` / ${row.partner.name_display}`}
                </Link>
                <span className="up-sub">
                  beat {nameOf(row.beat || []) || '—'}
                  {row.best_round && ` · ${row.best_round}`}
                </span>
              </span>
              <span className="pill ghost">{row.event}</span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}

export default function Dashboard() {
  const { data: events } = useAsync(() => api.events(), [])
  const { data: tcount } = useAsync(() => api.tournaments({ limit: 1 }), [])
  const totalRated = events ? events.reduce((a, e) => a + e.rated_players, 0) : null

  return (
    <div className="dashboard">
      <section className="dash-hero">
        <div className="kicker">Badminton Elo · BWF</div>
        <h1>Every rally, quantified.</h1>
        <p className="page-sub">
          A skill-rating system built from two decades of BWF results. Ratings
          move on who you beat — not points earned — using Glicko-2 with paired
          doubles strength.
        </p>
        <div className="stat-chips">
          <span className="chip"><b>{totalRated ? totalRated.toLocaleString() : '—'}</b> rated players</span>
          <span className="chip"><b>{tcount ? tcount.count.toLocaleString() : '—'}</b> tournaments</span>
          <span className="chip"><b>5</b> disciplines</span>
        </div>
      </section>

      <Panel title="Reigning world #1s">
        <ReigningChamps />
      </Panel>

      <div className="dash-grid">
        <MiniBoard />
        <RecentTournaments />
      </div>

      <BiggestUpsets />
    </div>
  )
}
