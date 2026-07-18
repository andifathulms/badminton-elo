import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, EVENTS } from '../api.js'
import { useAsync } from '../useAsync.js'

const eventLabel = (code) => EVENTS.find((e) => e.code === code)?.label || code
const names = (players) => players.map((p) => p.name_display).join(' / ') || '—'

function MatchList({ id, events }) {
  const eventCodes = events.map((e) => e.event)
  const [event, setEvent] = useState(eventCodes[0] || 'MS')
  const [round, setRound] = useState('All')
  const { data, error, loading } = useAsync(
    () => api.tournamentMatches(id, { event, limit: 300 }),
    [id, event],
  )
  // Distinct rounds present, ordered by the bracket (round_order).
  const rounds = data
    ? [...new Map(data.results.map((m) => [m.round_name, m.round_order])).entries()]
        .sort((a, b) => a[1] - b[1])
        .map(([name]) => name)
    : []
  const shown = data
    ? data.results.filter((m) => round === 'All' || m.round_name === round)
    : []

  return (
    <>
      <div className="tabs">
        {events.map((e) => (
          <button key={e.event}
            className={`tab ${e.event === event ? 'active' : ''}`}
            onClick={() => { setEvent(e.event); setRound('All') }}>
            {e.event}
            <span className="tab-label">{e.n}</span>
          </button>
        ))}
      </div>
      {rounds.length > 1 && (
        <div className="roundtabs">
          <button className={`rtab ${round === 'All' ? 'active' : ''}`}
                  onClick={() => setRound('All')}>All</button>
          {rounds.map((r) => (
            <button key={r} className={`rtab ${round === r ? 'active' : ''}`}
                    onClick={() => setRound(r)}>{r}</button>
          ))}
        </div>
      )}
      {loading && <p className="muted">Loading…</p>}
      {error && <p className="error">Could not load matches.</p>}
      {data && (
        <table className="board compact">
          <tbody>
            {shown.map((m) => (
              <tr key={m.match_id}>
                <td className="muted small">{m.round_name}</td>
                <td className={m.winner_side === 1 ? 'strong' : ''}>{names(m.side1)}</td>
                <td className="score-cell">
                  {m.score.map((g, i) => (
                    <span key={i}>{g[0]}-{g[1]} </span>
                  ))}
                </td>
                <td className={m.winner_side === 2 ? 'strong' : ''}>{names(m.side2)}</td>
                <td className="num">
                  <Link to={`/matches/${m.match_id}`} className="muted small">view →</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}

export default function Tournament() {
  const { id } = useParams()
  const { data: t, error, loading } = useAsync(() => api.tournament(id), [id])

  if (loading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">Could not load tournament: {error.message}</p>

  return (
    <div>
      <Link to="/tournaments" className="back">← Tournaments</Link>
      <h1>{t.name}</h1>
      <div className="meta">
        {t.category_name && <span>{t.category_name}</span>}
        {t.venue_name && <span>{t.venue_name}</span>}
        <span>{t.start_date} → {t.end_date}</span>
        {t.prize_money && <span>${Number(t.prize_money).toLocaleString()}</span>}
        <span>{t.match_count} matches</span>
      </div>

      {t.finals.length > 0 && (
        <>
          <h2>Champions</h2>
          <table className="board compact">
            <tbody>
              {t.finals.map((f) => (
                <tr key={f.match_id}>
                  <td className="strong">{eventLabel(f.event)}</td>
                  <td>
                    {f.champions.map((p, i) => (
                      <span key={p.player_id}>
                        {i > 0 ? ' / ' : ''}
                        <Link to={`/players/${p.player_id}`}>{p.name_display}</Link>
                      </span>
                    ))}
                    {f.champions.length === 0 && <span className="muted">—</span>}
                  </td>
                  <td className="num">
                    <Link to={`/matches/${f.match_id}`} className="muted small">
                      final →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {t.events?.length > 0 && (
        <>
          <h2>Matches</h2>
          <MatchList id={id} events={t.events} />
        </>
      )}
    </div>
  )
}
