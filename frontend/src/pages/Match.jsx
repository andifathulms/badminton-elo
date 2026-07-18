import { Link, useParams } from 'react-router-dom'
import { api } from '../api.js'
import { useAsync } from '../useAsync.js'
import MatchStats from '../components/MatchStats.jsx'

export default function Match() {
  const { id } = useParams()
  const { data: m, error, loading } = useAsync(() => api.match(id), [id])

  if (loading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">Could not load match: {error.message}</p>

  const side = (n) => m.lineup.filter((l) => l.side === n).map((l) => l.player)
  const won = (n) => (m.winner_side === n ? 'winner' : '')
  const teamElo = m.team_elo || {}
  const hasElo = Object.keys(teamElo).length > 0
  const isDoubles = m.lineup.filter((l) => l.side === 1).length > 1
  const teamEloTag = (side) => {
    const e = teamElo[side]
    if (e == null) return null
    return (
      <div className="team-elo">
        <span className="muted small">{isDoubles ? 'pair ' : ''}{e.before}→{e.after}</span>
        <span className={`elo ${e.delta >= 0 ? 'pos' : 'neg'}`}>
          {e.delta >= 0 ? '+' : ''}
          {e.delta.toFixed(1)}
        </span>
      </div>
    )
  }

  return (
    <div>
      <Link to="/rankings" className="back">← Rankings</Link>
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
              </Link>
            ))}
          </div>
          {teamEloTag(1)}
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
              </Link>
            ))}
          </div>
          {teamEloTag(2)}
        </div>
      </div>

      {hasElo && (
        <p className="muted small elo-note">
          Ratings are each {isDoubles ? 'pair' : 'player'}'s rating at the{' '}
          <strong>start of this tournament</strong> (the system is
          tournament-locked, so the result is scored against pre-tournament
          strength — not a figure inflated by earlier rounds).
          {isDoubles && ' The pair figure is the mean of the two members.'} The ±
          is the ELO this match contributed.
        </p>
      )}

      {m.rating_excluded && (
        <p className="muted">This match is excluded from rating (walkover/no-play).</p>
      )}

      <h2>Match statistics</h2>
      <MatchStats matchId={id} />
    </div>
  )
}
