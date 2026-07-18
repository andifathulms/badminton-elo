import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api.js'
import { useAsync } from '../useAsync.js'

const names = (players) => players.map((p) => p.name_display).join(' / ') || '—'

export default function PairDetail() {
  const { event, p1, p2 } = useParams()
  const navigate = useNavigate()
  const { data, error, loading } = useAsync(
    () => api.pairDetail(event, p1, p2),
    [event, p1, p2],
  )

  if (loading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">Could not load pair: {error.message}</p>

  const pair = data.pair
  const winPct = data.matches_together
    ? Math.round((100 * data.wins) / data.matches_together)
    : 0

  return (
    <div>
      <Link to="/rankings" className="back">← Rankings</Link>
      <h1 className="player-name">
        <Link to={`/players/${data.player1.player_id}`}>{data.player1.name_display}</Link>
        {' / '}
        <Link to={`/players/${data.player2.player_id}`}>{data.player2.name_display}</Link>
        <span className="country-badge">{event}</span>
      </h1>
      <div className="records">
        {pair && (
          <span className="record-pill">
            <b>Rating</b> {pair.rating.toFixed(1)}
            {pair.peak_rating != null && (
              <span className="muted small"> · peak {pair.peak_rating.toFixed(0)}</span>
            )}
          </span>
        )}
        <span className="record-pill">
          <b>Together</b> {data.wins}–{data.losses}
          <span className="muted small"> {winPct}%</span>
        </span>
        <span className="record-pill">
          <b>{data.matches_together}</b> matches
        </span>
      </div>

      <h2>Matches together</h2>
      {data.matches.length === 0 ? (
        <p className="muted">No matches found.</p>
      ) : (
        <table className="board compact matchlist">
          <tbody>
            {data.matches.map((m) => {
              const ourSide = m.side1.some(
                (p) => String(p.player_id) === String(data.player1.player_id),
              )
                ? 1
                : 2
              const won = m.winner_side === ourSide
              const opp = ourSide === 1 ? m.side2 : m.side1
              return (
                <tr
                  key={m.match_id}
                  className="clickable"
                  onClick={() => navigate(`/matches/${m.match_id}`)}
                >
                  <td>
                    <span className={`wl ${won ? 'w' : 'l'}`}>{won ? 'W' : 'L'}</span>
                  </td>
                  <td className="link">{names(opp)}</td>
                  <td className="score-cell">
                    {m.score.map((g, i) => (
                      <span key={i}>{g[0]}-{g[1]} </span>
                    ))}
                  </td>
                  <td className="muted small">{m.round_name}</td>
                  <td className="num muted small">
                    {m.match_time_utc ? m.match_time_utc.slice(0, 10) : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
