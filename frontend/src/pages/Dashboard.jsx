import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, EVENTS } from '../api.js'
import { useAsync } from '../useAsync.js'
import Avatar from '../components/Avatar.jsx'
import Entity from '../components/Entity.jsx'
import UpsetsTable from '../components/UpsetsTable.jsx'
import { SkeletonList, SkeletonCards } from '../components/Skeleton.jsx'
import { flag } from '../flags.js'

const DOUBLES = new Set(['MD', 'WD', 'XD'])
const isDoubles = (e) => DOUBLES.has(e)

// Panel wrapper with a title and an optional "view all" link.
function Panel({ title, to, linkText, wide, children }) {
  return (
    <section className={`panel${wide ? ' panel-wide' : ''}`}>
      <div className="panel-head">
        <h2>{title}</h2>
        {to && <Link to={to} className="view-all">{linkText || 'View all'} →</Link>}
      </div>
      {children}
    </section>
  )
}

// Reigning #1 for one discipline: a single player (singles) or a pair (doubles).
function champOf(event) {
  if (isDoubles(event.code)) {
    return api.pairs(event.code, { limit: 1, minMatches: 5 }).then((d) => {
      const p = d.results[0]
      if (!p) return { event, players: null, rating: null }
      return {
        event,
        players: [p.player1, p.player2],
        rating: p.rating,
        to: `/pairs/${event.code}/${p.player1.player_id}/${p.player2.player_id}`,
      }
    })
  }
  return api.leaderboard(event.code, { limit: 1, minMatches: 5 }).then((d) => {
    const row = d.results[0]
    if (!row) return { event, players: null, rating: null }
    return {
      event,
      players: [row.player],
      rating: row.rating,
      to: `/players/${row.player.player_id}`,
    }
  })
}

function ReigningChamps() {
  const { data } = useAsync(() => Promise.all(EVENTS.map(champOf)), [])
  if (!data) return <SkeletonCards count={5} />
  return (
    <div className="champ-grid">
      {data.filter((d) => d.players).map(({ event, players, rating, to }) => {
        const pair = players.length > 1
        const cc = players[0].country_code
        return (
          <Link key={event.code} to={to} className="champ-card">
            <div className="champ-badge">{event.code}</div>
            <span className={pair ? 'champ-av pair-av' : 'champ-av'}>
              {players.map((p) => <Avatar key={p.player_id} player={p} size="lg" />)}
            </span>
            <div className="champ-name">
              {pair
                ? players.map((p) => p.name_display).join(' / ')
                : players[0].name_display}
            </div>
            <div className="champ-sub">
              <span className="fl">{flag(cc)}</span>{cc}
            </div>
            <div className="champ-rating">{rating.toFixed(0)}</div>
            <div className="champ-label">{event.label}</div>
          </Link>
        )
      })}
    </div>
  )
}

function MiniBoard() {
  const [event, setEvent] = useState('MS')
  const doubles = isDoubles(event)
  const { data, loading } = useAsync(
    () =>
      doubles
        ? api.pairs(event, { limit: 5, minMatches: 5 })
        : api.leaderboard(event, { limit: 5, minMatches: 5 }),
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
      {loading && <SkeletonList rows={5} />}
      {data && (
        <ol className="mini-list">
          {data.results.map((row, i) => {
            // Derive the shape from the row, not the selected event: while a
            // tab switch is loading, `data` still holds the previous event's
            // rows for one render, so trusting `doubles` here would crash.
            const players = row.player1 ? [row.player1, row.player2] : [row.player]
            const key = players.map((p) => p.player_id).join('-')
            return (
              <li key={key}>
                <span className={`medal sm ${i < 3 ? `m${i + 1}` : ''}`}>{i + 1}</span>
                <Entity players={players} event={event} />
                <span className="mini-rating">{row.rating.toFixed(0)}</span>
              </li>
            )
          })}
        </ol>
      )}
      {data && data.results.length === 0 && <p className="muted small">No entries yet.</p>}
    </Panel>
  )
}

function RecentTournaments() {
  const { data, loading } = useAsync(() => api.tournaments({ limit: 6 }), [])
  return (
    <Panel title="Recent tournaments" to="/tournaments">
      {loading && <SkeletonList rows={5} />}
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
    () => api.analytics('upsets', { minMatches: 3, limit: 8 }),
    [],
  )
  return (
    <Panel title="⚡ Biggest upsets" to="/insights" linkText="More insights" wide>
      {loading && <SkeletonList rows={6} />}
      {data && <UpsetsTable rows={data.results} />}
    </Panel>
  )
}

export default function Dashboard() {
  const { data: events } = useAsync(() => api.events(), [])
  const { data: tcount } = useAsync(() => api.tournaments({ limit: 1 }), [])
  const { data: calib } = useAsync(() => api.calibration('ALL'), [])
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
          {calib?.accuracy != null && (
            <Link to="/insights" className="chip chip-link"
                  title={`The higher-rated side wins ${(calib.accuracy * 100).toFixed(1)}% of the time; predicted vs actual agree within ${(calib.calibration_error * 100).toFixed(1)}%. See the reliability diagram.`}>
              <b>{(calib.accuracy * 100).toFixed(0)}%</b> predictions correct ✓
            </Link>
          )}
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
