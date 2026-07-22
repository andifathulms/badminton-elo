import { Link, useParams } from 'react-router-dom'
import { api } from '../api.js'
import { useAsync } from '../useAsync.js'
import { flag } from '../flags.js'
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
  // `mirror` reverses the flow so the elo sits on the inner (centre) side.
  const teamEloTag = (side, mirror) => {
    const e = teamElo[side]
    if (e == null) return null
    return (
      <div className={`sc-elo ${mirror ? 'rev' : ''}`}>
        <span className="muted small">{isDoubles ? 'pair ' : ''}{e.before}→{e.after}</span>
        <span className={`elo ${e.delta >= 0 ? 'pos' : 'neg'}`}>
          {e.delta >= 0 ? '+' : ''}
          {e.delta.toFixed(1)}
        </span>
      </div>
    )
  }
  // A team's players, flag on the inner (centre-facing) side.
  const players = (n, mirror) => (
    <div className="sc-players">
      {side(n).map((p) => (
        <Link key={p.player_id} to={`/players/${p.player_id}`}
              className={`sc-pname ${mirror ? 'rev' : ''}`}>
          <span className="nm">{p.name_display}</span>
          <span className="fl">{flag(p.country_code)}</span>
        </Link>
      ))}
    </div>
  )

  return (
    <div>
      <Link to="/rankings" className="back">← Rankings</Link>
      <header className="page-hero">
        <div className="page-hero-text">
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
        </div>
      </header>

      <div className="scorecard">
        <div className={`sc-team r ${won(1)}`}>
          {players(1, false)}
          {teamEloTag(1, false)}
        </div>

        <div className="sc-games">
          {m.games.map((g) => (
            <div key={g.game_no} className="sc-game">
              <span className={`sc-pts ${g.side1_points > g.side2_points ? 'win' : ''}`}>
                {g.side1_points}
              </span>
              <span className={`sc-pts ${g.side2_points > g.side1_points ? 'win' : ''}`}>
                {g.side2_points}
              </span>
            </div>
          ))}
        </div>

        <div className={`sc-team l ${won(2)}`}>
          {players(2, true)}
          {teamEloTag(2, true)}
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
