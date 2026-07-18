import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api.js'
import { useAsync } from '../useAsync.js'
import RatingChart from '../components/RatingChart.jsx'
import MatchHistory from '../components/MatchHistory.jsx'
import StyleCard from '../components/StyleCard.jsx'
import Avatar from '../components/Avatar.jsx'

export default function Player() {
  const { id } = useParams()
  const { data: player, error, loading } = useAsync(() => api.player(id), [id])
  const [event, setEvent] = useState(null)

  const activeEvent = event || player?.ratings?.[0]?.event
  const history = useAsync(
    () => (activeEvent ? api.playerHistory(id, activeEvent) : Promise.resolve([])),
    [id, activeEvent],
  )

  if (loading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">Could not load player: {error.message}</p>

  const wins = player.records?.reduce((a, r) => a + r.wins, 0) || 0
  const losses = player.records?.reduce((a, r) => a + r.losses, 0) || 0
  const totalMatches = wins + losses
  const winPct = totalMatches ? Math.round((100 * wins) / totalMatches) : 0
  const top = player.ratings?.[0]

  return (
    <div>
      <Link to="/rankings" className="back">← Rankings</Link>

      <div className="profile">
        <Avatar player={player} size="lg" />
        <div className="pinfo">
          <h1>
            {player.name_display}
            <span className="country-badge">{player.country_code}</span>
          </h1>
          <div className="meta">
            {player.plays && <span>🏸 Plays {player.plays}</span>}
            {player.height_cm && <span>📏 {player.height_cm} cm</span>}
            {player.dob && <span>🎂 {player.dob}</span>}
            {totalMatches > 0 && (
              <span>📊 {wins}–{losses} career ({winPct}%)</span>
            )}
          </div>
        </div>
      </div>

      <div className="statgrid">
        {top && (
          <div className="statcard">
            <div className="k">{top.event} Rating</div>
            <div className="v">{top.rating.toFixed(0)}</div>
            <div className="sub">mu {top.mu.toFixed(0)} · rd {top.rd.toFixed(0)}</div>
          </div>
        )}
        {top?.peak_mu != null && (
          <div className="statcard">
            <div className="k">Peak {top.event}</div>
            <div className="v">{top.peak_mu.toFixed(0)}</div>
            <div className="sub">{top.peak_utc ? top.peak_utc.slice(0, 7) : '—'}</div>
          </div>
        )}
        <div className="statcard">
          <div className="k">Career W–L</div>
          <div className="v">{wins}–{losses}</div>
          <div className="sub">{winPct}% win rate</div>
        </div>
        <div className="statcard">
          <div className="k">Matches</div>
          <div className="v">{totalMatches}</div>
          <div className="sub">{player.ratings?.length || 0} disciplines</div>
        </div>
      </div>

      {player.records?.length > 1 && (
        <div className="records">
          {player.records.map((r) => (
            <span key={r.event} className="record-pill">
              <b>{r.event}</b> {r.wins}–{r.losses}
              <span className="muted small">
                {' '}
                {r.matches ? Math.round((100 * r.wins) / r.matches) : 0}%
              </span>
            </span>
          ))}
        </div>
      )}

      <h2>Ratings by discipline</h2>
      <table className="board compact">
        <thead>
          <tr>
            <th>Event</th>
            <th className="num">Rating</th>
            <th className="num">mu</th>
            <th className="num">rd</th>
            <th className="num">Peak</th>
            <th className="num">Matches</th>
          </tr>
        </thead>
        <tbody>
          {player.ratings.map((r) => (
            <tr
              key={r.event}
              className={r.event === activeEvent ? 'selected' : ''}
              onClick={() => setEvent(r.event)}
            >
              <td className="strong">{r.event}</td>
              <td className="num strong">{r.rating.toFixed(1)}</td>
              <td className="num">{r.mu.toFixed(0)}</td>
              <td className="num muted">{r.rd.toFixed(0)}</td>
              <td className="num">
                {r.peak_mu != null ? r.peak_mu.toFixed(0) : '—'}
                {r.peak_utc && (
                  <span className="muted small"> ’{r.peak_utc.slice(2, 4)}</span>
                )}
              </td>
              <td className="num muted">{r.matches_played}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {player.ratings.length === 0 && (
        <p className="muted">No ratings yet for this player.</p>
      )}

      <StyleCard playerId={id} />

      {activeEvent && (
        <>
          <h2>{activeEvent} rating over time</h2>
          {history.loading && <p className="muted">Loading history…</p>}
          {history.data && <RatingChart points={history.data} />}

          <h2>{activeEvent} match history</h2>
          <MatchHistory playerId={id} event={activeEvent} />
        </>
      )}
    </div>
  )
}
