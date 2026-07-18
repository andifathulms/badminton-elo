import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'
import { useAsync } from '../useAsync.js'
import Pager from './Pager.jsx'

const names = (players) =>
  players.map((p) => p.name_display).join(' / ') || '—'
const PAGE = 20

export default function MatchHistory({ playerId, event }) {
  const navigate = useNavigate()
  const [page, setPage] = useState(0)
  useEffect(() => setPage(0), [playerId, event])
  const { data, error, loading } = useAsync(
    () => api.playerMatches(playerId, { event, limit: PAGE, offset: page * PAGE }),
    [playerId, event, page],
  )

  if (loading) return <p className="muted">Loading matches…</p>
  if (error) return <p className="error">Could not load matches: {error.message}</p>
  if (!data.results.length) return <p className="muted">No matches.</p>

  return (
    <>
    <table className="board compact matchlist">
      <thead>
        <tr>
          <th></th>
          <th>Opponent</th>
          <th>Score</th>
          <th className="num">ELO</th>
          <th>Round</th>
          <th>Tournament</th>
          <th className="num">Date</th>
        </tr>
      </thead>
      <tbody>
        {data.results.map((m) => (
          <tr
            key={m.match_id}
            className="clickable"
            onClick={() => navigate(`/matches/${m.match_id}`)}
          >
            <td>
              <span className={`wl ${m.won ? 'w' : 'l'}`}>{m.won ? 'W' : 'L'}</span>
            </td>
            <td>
              <span className="link">{names(m.opponents)}</span>
              {m.partners.length > 0 && (
                <div className="muted small">w/ {names(m.partners)}</div>
              )}
            </td>
            <td className="score-cell">
              {m.score.map((g, i) => (
                <span key={i} className={g[0] > g[1] ? 'hi' : ''}>
                  {g[0]}-{g[1]}{' '}
                </span>
              ))}
              {m.score_status !== 'Normal' && (
                <span className="muted small">({m.score_status})</span>
              )}
            </td>
            <td className="num">
              {m.elo == null ? (
                <span className="muted">—</span>
              ) : (
                <>
                  <span className={m.elo.delta >= 0 ? 'pos' : 'neg'}>
                    {m.elo.delta >= 0 ? '+' : ''}
                    {m.elo.delta.toFixed(1)}
                  </span>
                  <div className="muted small">{m.elo.before}→{m.elo.after}</div>
                </>
              )}
            </td>
            <td className="muted small">{m.round_name}</td>
            <td className="muted small">{m.tournament?.name}</td>
            <td className="num muted small">
              {m.match_time_utc ? m.match_time_utc.slice(0, 10) : '—'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
    <Pager page={page} setPage={setPage} count={data.count} pageSize={PAGE} unit="matches" />
    </>
  )
}
