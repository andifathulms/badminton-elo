import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api.js'
import { useAsync } from '../useAsync.js'
import Pager from '../components/Pager.jsx'
import Avatar from '../components/Avatar.jsx'
import { flag } from '../flags.js'

const names = (players) => players.map((p) => p.name_display).join(' / ') || '—'
const PAGE = 20

export default function PairDetail() {
  const { event, p1, p2 } = useParams()
  const navigate = useNavigate()
  const [page, setPage] = useState(0)
  useEffect(() => setPage(0), [event, p1, p2])
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
      <header className="profile">
        <span className="pair-av">
          <Avatar player={data.player1} size="lg" />
          <Avatar player={data.player2} size="lg" />
        </span>
        <div className="pinfo">
          <h1>
            <Link to={`/players/${data.player1.player_id}`}>{data.player1.name_display}</Link>
            {' / '}
            <Link to={`/players/${data.player2.player_id}`}>{data.player2.name_display}</Link>
            <span className="country-badge">{event}</span>
          </h1>
          <div className="meta">
            <span>{flag(data.player1.country_code)} {data.player1.country_code}</span>
            <span>{flag(data.player2.country_code)} {data.player2.country_code}</span>
          </div>
        </div>
      </header>
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
        <>
        <table className="board compact matchlist">
          <tbody>
            {data.matches.slice(page * PAGE, page * PAGE + PAGE).map((m) => {
              const ourSide = m.side1.some(
                (p) => String(p.player_id) === String(data.player1.player_id),
              )
                ? 1
                : 2
              const won = m.winner_side === ourSide
              const opp = ourSide === 1 ? m.side2 : m.side1
              // Orient the scoreline to the pair (side 1 of the row is "us").
              const score = ourSide === 2 ? m.score.map(([a, b]) => [b, a]) : m.score
              return (
                <tr
                  key={m.match_id}
                  className="clickable"
                  onClick={() => navigate(`/matches/${m.match_id}`)}
                >
                  <td>
                    <span className={`wl ${won ? 'w' : 'l'}`}>{won ? 'W' : 'L'}</span>
                  </td>
                  <td className="link">
                    <span className="fl">{flag(opp[0]?.country_code)}</span> {names(opp)}
                  </td>
                  <td className="score-cell">
                    {score.map((g, i) => (
                      <span key={i} className={g[0] > g[1] ? 'hi' : ''}>{g[0]}-{g[1]} </span>
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
        <Pager page={page} setPage={setPage} count={data.matches.length}
               pageSize={PAGE} unit="matches" />
        </>
      )}
    </div>
  )
}
