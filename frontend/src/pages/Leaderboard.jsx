import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, EVENTS } from '../api.js'
import { useAsync } from '../useAsync.js'

export default function Leaderboard() {
  const [event, setEvent] = useState('MS')
  const [order, setOrder] = useState('rating')
  const [ranking, setRanking] = useState('current')
  const { data, error, loading } = useAsync(
    () => api.leaderboard(event, { order, ranking, minMatches: 5, limit: 50 }),
    [event, order, ranking],
  )
  const isPeak = ranking === 'peak'

  return (
    <div>
      <div className="tabs">
        {EVENTS.map((e) => (
          <button
            key={e.code}
            className={`tab ${e.code === event ? 'active' : ''}`}
            onClick={() => setEvent(e.code)}
          >
            {e.code}
            <span className="tab-label">{e.label}</span>
          </button>
        ))}
      </div>

      <div className="toolbar">
        <div className="segmented">
          <button
            className={!isPeak ? 'seg active' : 'seg'}
            onClick={() => setRanking('current')}
          >
            Current
          </button>
          <button
            className={isPeak ? 'seg active' : 'seg'}
            onClick={() => setRanking('peak')}
          >
            All-time peak
          </button>
        </div>
        {!isPeak && (
          <label className="order">
            Sort:&nbsp;
            <select value={order} onChange={(ev) => setOrder(ev.target.value)}>
              <option value="rating">Rating (mu − 2·rd)</option>
              <option value="mu">Skill (mu)</option>
            </select>
          </label>
        )}
      </div>

      {loading && <p className="muted">Loading…</p>}
      {error && <p className="error">Could not load leaderboard: {error.message}</p>}
      {data && (
        <table className="board">
          <thead>
            <tr>
              <th>#</th>
              <th>Player</th>
              <th></th>
              <th className="num">{isPeak ? 'Peak' : 'Rating'}</th>
              <th className="num">{isPeak ? 'when' : 'mu'}</th>
              <th className="num">rd</th>
              <th className="num">M</th>
            </tr>
          </thead>
          <tbody>
            {data.results.map((row, i) => (
              <tr key={row.player.player_id}>
                <td className="rank">{i + 1}</td>
                <td>
                  <Link to={`/players/${row.player.player_id}`}>
                    {row.player.name_display}
                  </Link>
                </td>
                <td className="country">{row.player.country_code}</td>
                <td className="num strong">
                  {isPeak ? row.peak_mu.toFixed(0) : row.rating.toFixed(1)}
                </td>
                <td className="num muted">
                  {isPeak
                    ? row.peak_utc
                      ? row.peak_utc.slice(0, 7)
                      : '—'
                    : row.mu.toFixed(0)}
                </td>
                <td className="num muted">
                  {isPeak ? row.peak_rd.toFixed(0) : row.rd.toFixed(0)}
                </td>
                <td className="num muted">{row.matches_played}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data && data.results.length === 0 && (
        <p className="muted">No rated players yet — run <code>manage.py rate</code>.</p>
      )}
    </div>
  )
}
