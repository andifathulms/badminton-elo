import { Link, useParams } from 'react-router-dom'
import { api, EVENTS } from '../api.js'
import { useAsync } from '../useAsync.js'
import { flag } from '../flags.js'
import Avatar from '../components/Avatar.jsx'
import CourtLines from '../components/CourtLines.jsx'
import MatchStats from '../components/MatchStats.jsx'
import { Delta } from '../components/Chips.jsx'
import { ErrorState } from '../components/Empty.jsx'
import { MatchSkeleton } from '../components/Skeleton.jsx'
import { fmtDay } from '../dates.js'

const ROUND = { F: 'Final', Final: 'Final', SF: 'Semi-final', QF: 'Quarter-final' }
const label = (code) => EVENTS.find((e) => e.code === code)?.label || code
const FORMAT = { '3x21': 'best of 3 to 21', '5x11': 'best of 5 to 11', '3x15': 'best of 3 to 15' }

export default function Match() {
  const { id } = useParams()
  const { data: m, error, loading, reload } = useAsync(() => api.match(id), [id])

  if (loading) return <MatchSkeleton />
  if (error) return <ErrorState error={error} onRetry={reload} what="this match" />

  const side = (n) => m.lineup.filter((l) => l.side === n).map((l) => l.player)
  const teamElo = m.team_elo || {}
  const isDoubles = side(1).length > 1
  const round = ROUND[m.round_name] || m.round_name
  const isFinal = round === 'Final'
  const abnormal = m.score_status && m.score_status !== 'Normal'
  const lastName = (ps) => ps.map((p) => p.name_display.split(' ').filter((w) => w === w.toUpperCase() && w.length > 1)[0] || p.name_display.split(' ').pop()).join(' / ')

  const Side = ({ n }) => {
    const ps = side(n)
    const win = m.winner_side === n
    const e = teamElo[n]
    return (
      <div className={`sb-side s${n} ${win ? 'win' : 'lose'}`}>
        <span className="pair-av">{ps.map((p) => <Avatar key={p.player_id} player={p} size={isDoubles ? 46 : 60} onDeep />)}</span>
        <div className="sb-who">
          {win && <span className="win-tag">{isFinal ? 'Champion' : 'Winner'}</span>}
          {ps.map((p) => (
            <Link key={p.player_id} to={`/players/${p.player_id}`} className="sb-nm">{p.name_display}</Link>
          ))}
          <span className="sb-sub">{flag(ps[0]?.country_code)} {ps[0]?.country_code}{e ? ` · rated ${e.before}` : ''}</span>
        </div>
      </div>
    )
  }

  return (
    <div className="match-page">
      <div className="crumb">
        {m.tournament && <><Link to={`/tournaments/${m.tournament.tournament_id}`}>{m.tournament.name}</Link><span className="sep">/</span></>}
        <span>{label(m.event)}</span><span className="sep">/</span><span>{round}</span>
      </div>

      <section className="sb arena">
        <CourtLines />
        <div className="sb-top">
          <span><b>{round}</b> · {label(m.event)}{m.tournament ? ` · ${m.tournament.name}` : ''}</span>
          <span>
            {m.match_time_utc ? fmtDay(m.match_time_utc, true) : ''}
            {m.duration_min ? ` · ${m.duration_min} min` : ''}
            {m.scoring_format ? ` · ${FORMAT[m.scoring_format] || m.scoring_format}` : ''}
          </span>
        </div>
        <div className="sb-grid">
          <Side n={1} />
          <div className="sb-games">
            {abnormal && <span className="sb-status">{m.score_status}</span>}
            <div className="games">
              {m.games.map((g) => (
                <div key={g.game_no} className="game">
                  <span>G{g.game_no}</span>
                  <b className={g.side1_points > g.side2_points ? 'w' : ''}>{g.side1_points}</b>
                  <b className={g.side2_points > g.side1_points ? 'w' : ''}>{g.side2_points}</b>
                </div>
              ))}
            </div>
          </div>
          <Side n={2} />
        </div>
      </section>

      {m.rating_excluded && (
        <p className="muted">This match is excluded from ratings (walkover or no play).</p>
      )}

      {Object.keys(teamElo).length > 0 && (
        <div className="impact">
          {[2, 1].sort((a, b) => (m.winner_side === a ? -1 : m.winner_side === b ? 1 : 0)).map((n) => {
            const e = teamElo[n]
            if (!e) return null
            return (
              <div key={n} className="imp card">
                <span className="imp-l">Rating impact · {side(n).map((p) => p.name_display).join(' / ')}{isDoubles ? ' (pair average)' : ''}</span>
                <div className="imp-row">
                  <span className="num-display muted">{e.before}</span>
                  <span className="imp-arr">→</span>
                  <span className="num-display">{e.after}</span>
                  <Delta value={e.delta} />
                </div>
              </div>
            )
          })}
          <p className="muted small imp-note">
            Ratings are from the start of the tournament, so each result is scored against pre-event
            strength. The change is what this match contributed.
          </p>
        </div>
      )}

      <MatchStats matchId={id} names={[lastName(side(1)), lastName(side(2))]} />
    </div>
  )
}
