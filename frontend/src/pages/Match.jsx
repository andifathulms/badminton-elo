import { Link, useParams } from 'react-router-dom'
import { api } from '../api.js'
import { useAsync } from '../useAsync.js'

export default function Match() {
  const { id } = useParams()
  const { data: m, error, loading } = useAsync(() => api.match(id), [id])

  if (loading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">Could not load match: {error.message}</p>

  const side = (n) => m.lineup.filter((l) => l.side === n).map((l) => l.player)
  const won = (n) => (m.winner_side === n ? 'winner' : '')
  const elo = m.elo || {}
  const eloTag = (pid) => {
    const d = elo[pid]
    if (d == null) return null
    return (
      <span className={`elo ${d >= 0 ? 'pos' : 'neg'}`}>
        {d >= 0 ? '+' : ''}
        {d.toFixed(1)}
      </span>
    )
  }

  return (
    <div>
      <Link to="/" className="back">← Leaderboard</Link>
      <div className="match-head">
        <span className="pill">{m.event}</span>
        <span className="pill ghost">{m.round_name}</span>
        {m.score_status !== 'Normal' && (
          <span className="pill warn">{m.score_status}</span>
        )}
      </div>
      <h1 className="tournament">{m.tournament?.name}</h1>
      <div className="meta">
        {m.tournament?.category_name && <span>{m.tournament.category_name}</span>}
        {m.match_time_utc && <span>{new Date(m.match_time_utc).toUTCString()}</span>}
        {m.scoring_format && <span>Format: {m.scoring_format}</span>}
      </div>

      <div className="scorecard">
        <div className={`team ${won(1)}`}>
          <div className="players">
            {side(1).map((p) => (
              <Link key={p.player_id} to={`/players/${p.player_id}`}>
                {p.name_display} <span className="country">{p.country_code}</span>
                {eloTag(p.player_id)}
              </Link>
            ))}
          </div>
        </div>

        <table className="games">
          <tbody>
            <tr>
              {m.games.map((g) => (
                <td key={g.game_no} className={g.side1_points > g.side2_points ? 'hi' : ''}>
                  {g.side1_points}
                </td>
              ))}
            </tr>
            <tr>
              {m.games.map((g) => (
                <td key={g.game_no} className={g.side2_points > g.side1_points ? 'hi' : ''}>
                  {g.side2_points}
                </td>
              ))}
            </tr>
          </tbody>
        </table>

        <div className={`team ${won(2)}`}>
          <div className="players">
            {side(2).map((p) => (
              <Link key={p.player_id} to={`/players/${p.player_id}`}>
                {p.name_display} <span className="country">{p.country_code}</span>
                {eloTag(p.player_id)}
              </Link>
            ))}
          </div>
        </div>
      </div>

      {m.rating_excluded && (
        <p className="muted">This match is excluded from rating (walkover/no-play).</p>
      )}
    </div>
  )
}
