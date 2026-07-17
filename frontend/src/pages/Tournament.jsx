import { Link, useParams } from 'react-router-dom'
import { api, EVENTS } from '../api.js'
import { useAsync } from '../useAsync.js'

const eventLabel = (code) => EVENTS.find((e) => e.code === code)?.label || code

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

      <h2>Draws</h2>
      <table className="board compact">
        <thead>
          <tr><th>Event</th><th>Stage</th><th className="num">Size</th></tr>
        </thead>
        <tbody>
          {t.draws.map((d, i) => (
            <tr key={`${d.event}-${d.draw_value}-${i}`}>
              <td className="strong">{d.event}</td>
              <td className="muted">{d.stage}</td>
              <td className="num muted">{d.size ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
