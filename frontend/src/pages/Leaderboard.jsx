import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, EVENTS } from '../api.js'
import { useAsync } from '../useAsync.js'

const isDoubles = (e) => e === 'MD' || e === 'WD' || e === 'XD'

export default function Leaderboard() {
  const [event, setEvent] = useState('MS')
  const [mode, setMode] = useState('individual') // individual | pairs
  const [order, setOrder] = useState('rating')
  const [ranking, setRanking] = useState('current') // current | peak
  const [gender, setGender] = useState('') // '' | M | F  (XD only)

  const doubles = isDoubles(event)
  const showPairs = doubles && mode === 'pairs'

  return (
    <div>
      <div className="tabs">
        {EVENTS.map((e) => (
          <button
            key={e.code}
            className={`tab ${e.code === event ? 'active' : ''}`}
            onClick={() => {
              setEvent(e.code)
              setMode('individual')
              setGender('')
            }}
          >
            {e.code}
            <span className="tab-label">{e.label}</span>
          </button>
        ))}
      </div>

      <div className="toolbar wrap">
        {doubles && (
          <div className="segmented">
            <button className={mode === 'individual' ? 'seg active' : 'seg'}
                    onClick={() => setMode('individual')}>Individual</button>
            <button className={mode === 'pairs' ? 'seg active' : 'seg'}
                    onClick={() => setMode('pairs')}>Pairs</button>
          </div>
        )}

        {!showPairs && (
          <div className="segmented">
            <button className={ranking === 'current' ? 'seg active' : 'seg'}
                    onClick={() => setRanking('current')}>Current</button>
            <button className={ranking === 'peak' ? 'seg active' : 'seg'}
                    onClick={() => setRanking('peak')}>All-time peak</button>
          </div>
        )}

        {event === 'XD' && mode === 'individual' && (
          <div className="segmented">
            <button className={gender === '' ? 'seg active' : 'seg'}
                    onClick={() => setGender('')}>All</button>
            <button className={gender === 'M' ? 'seg active' : 'seg'}
                    onClick={() => setGender('M')}>Men</button>
            <button className={gender === 'F' ? 'seg active' : 'seg'}
                    onClick={() => setGender('F')}>Women</button>
          </div>
        )}
      </div>

      {showPairs ? (
        <PairsBoard event={event} />
      ) : (
        <IndividualBoard
          event={event}
          ranking={ranking}
          order={order}
          setOrder={setOrder}
          gender={gender}
        />
      )}
    </div>
  )
}

function IndividualBoard({ event, ranking, order, setOrder, gender }) {
  const isPeak = ranking === 'peak'
  const { data, error, loading } = useAsync(
    () => api.leaderboard(event, { order, ranking, gender, minMatches: 5, limit: 50 }),
    [event, ranking, order, gender],
  )

  return (
    <>
      {!isPeak && (
        <div className="toolbar">
          <span className="muted small">Ranked by mu − 2·rd (conservative)</span>
          <label className="order">
            Sort:&nbsp;
            <select value={order} onChange={(e) => setOrder(e.target.value)}>
              <option value="rating">Rating (mu − 2·rd)</option>
              <option value="mu">Skill (mu)</option>
            </select>
          </label>
        </div>
      )}
      {loading && <p className="muted">Loading…</p>}
      {error && <p className="error">Could not load: {error.message}</p>}
      {data && (
        <table className="board">
          <thead>
            <tr>
              <th>#</th><th>Player</th><th></th>
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
                  {isPeak ? (row.peak_utc ? row.peak_utc.slice(0, 7) : '—') : row.mu.toFixed(0)}
                </td>
                <td className="num muted">{(isPeak ? row.peak_rd : row.rd).toFixed(0)}</td>
                <td className="num muted">{row.matches_played}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data && data.results.length === 0 && <p className="muted">No players.</p>}
    </>
  )
}

function PairsBoard({ event }) {
  const { data, error, loading } = useAsync(
    () => api.pairs(event, { minMatches: 5, limit: 50 }),
    [event],
  )
  if (loading) return <p className="muted">Loading pairs…</p>
  if (error) return <p className="error">Could not load pairs: {error.message}</p>
  return (
    <table className="board">
      <thead>
        <tr>
          <th>#</th><th>Pair</th>
          <th className="num">Rating</th>
          <th className="num">Together</th>
          <th className="num">Win%</th>
        </tr>
      </thead>
      <tbody>
        {data.results.map((row, i) => (
          <tr key={`${row.player1.player_id}-${row.player2.player_id}`}>
            <td className="rank">{i + 1}</td>
            <td>
              <Link to={`/players/${row.player1.player_id}`}>{row.player1.name_display}</Link>
              {' / '}
              <Link to={`/players/${row.player2.player_id}`}>{row.player2.name_display}</Link>
              <div className="muted small">
                {row.player1.country_code}
                {row.player2.country_code !== row.player1.country_code
                  ? ` / ${row.player2.country_code}`
                  : ''}
              </div>
            </td>
            <td className="num strong">{row.rating.toFixed(1)}</td>
            <td className="num muted">{row.matches_together}</td>
            <td className="num">{row.win_pct != null ? `${row.win_pct}%` : '—'}</td>
          </tr>
        ))}
      </tbody>
      {data.results.length === 0 && (
        <tbody><tr><td colSpan="5" className="muted">No pairs.</td></tr></tbody>
      )}
    </table>
  )
}
