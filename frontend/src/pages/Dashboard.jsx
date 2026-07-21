import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, EVENTS } from '../api.js'
import { useAsync } from '../useAsync.js'
import Avatar from '../components/Avatar.jsx'
import { flag } from '../flags.js'

const DOUBLES = new Set(['MD', 'WD', 'XD'])
const isDoubles = (e) => DOUBLES.has(e)

// A player or a pair, rendered as avatar(s) + name(s), linking to the right
// detail page. `players` is a 1- or 2-element array of brief player objects.
function Entity({ players, event, size = 'sm', rating }) {
  const list = (players || []).filter(Boolean)
  if (list.length === 0) return <span className="muted">—</span>
  const pair = list.length > 1
  const to = pair
    ? `/pairs/${event}/${list[0].player_id}/${list[1].player_id}`
    : `/players/${list[0].player_id}`
  const cc = list[0].country_code
  return (
    <Link to={to} className="ent">
      <span className={pair ? 'pair-av' : ''}>
        {list.map((p) => <Avatar key={p.player_id} player={p} size={size} />)}
      </span>
      <span className="ent-meta">
        <span className="ent-name">{list.map((p) => p.name_display).join(' / ')}</span>
        <span className="ent-sub">
          <span className="fl">{flag(cc)}</span>{cc}
          {rating != null && (
            <span className="ent-rating" title="Rating before this match">· {rating}</span>
          )}
        </span>
      </span>
    </Link>
  )
}

// Format an oriented games array ([[a,b],…]) as "21-15 21-18".
const fmtScore = (games) =>
  (games || []).map(([a, b]) => `${a}-${b}`).join('  ')

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
  if (!data) return <div className="champ-grid loading" />
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
      {loading && <p className="muted small">Loading…</p>}
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
    () => api.analytics('upsets', { minMatches: 3, limit: 8 }),
    [],
  )
  return (
    <Panel title="⚡ Biggest upsets" to="/insights" linkText="More insights" wide>
      {loading && <p className="muted small">Loading…</p>}
      {data && (
        <div className="table-scroll">
          <table className="board upset-table">
            <thead>
              <tr>
                <th className="num" title="Elo gained from this win">Gained</th>
                <th>Winner</th>
                <th>Opponent</th>
                <th>Score</th>
                <th>Tournament</th>
                <th className="rnd">Round</th>
                <th className="cat">Cat</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((row) => {
                const winners = [row.player, row.partner].filter(Boolean)
                const abnormal =
                  row.best_score_status && row.best_score_status !== 'Normal'
                return (
                  <tr key={`${row.player.player_id}-${row.tournament.tournament_id}`}>
                    <td className="num">
                      <span className="up-delta pos">+{row.best_delta.toFixed(0)}</span>
                    </td>
                    <td>
                      <Entity players={winners} event={row.event}
                        rating={row.winner_rating_before} />
                    </td>
                    <td>
                      <Entity players={row.beat} event={row.event}
                        rating={row.opponent_rating_before} />
                    </td>
                    <td className="score-cell">
                      {abnormal
                        ? <span className="pill warn tiny">{row.best_score_status}</span>
                        : <span className="score-mono">{fmtScore(row.best_score)}</span>}
                    </td>
                    <td className="tour-cell">
                      <Link to={`/tournaments/${row.tournament.tournament_id}`}
                        className="tour-link">{row.tournament.name}</Link>
                    </td>
                    <td className="rnd muted">{row.best_round || '—'}</td>
                    <td className="cat"><span className="pill ghost">{row.event}</span></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
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
