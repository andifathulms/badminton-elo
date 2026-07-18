import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, EVENTS } from '../api.js'
import { useAsync } from '../useAsync.js'
import Avatar from '../components/Avatar.jsx'
import Select from '../components/Select.jsx'

const isDoubles = (e) => e === 'MD' || e === 'WD' || e === 'XD'
const PAGE = 20
const CAP = 200

function Medal({ n }) {
  return <span className={`medal ${n <= 3 ? `m${n}` : ''}`}>{n}</span>
}

const eventLabel = (code) => EVENTS.find((e) => e.code === code)?.label || code

function Pager({ page, setPage, count }) {
  const shown = Math.min((page + 1) * PAGE, CAP)
  const maxPage = Math.min(Math.ceil(count / PAGE), CAP / PAGE) - 1
  if (maxPage <= 0) return null
  return (
    <div className="pager">
      <button className="pgbtn" disabled={page <= 0} onClick={() => setPage(page - 1)}>
        ← Prev
      </button>
      <span className="muted small">Top {shown} · page {page + 1} / {maxPage + 1}</span>
      <button className="pgbtn" disabled={page >= maxPage} onClick={() => setPage(page + 1)}>
        Next →
      </button>
    </div>
  )
}

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
      <div className="page-head">
        <div className="kicker">BWF World Rankings · Elo</div>
        <h1 className="page-title">{eventLabel(event)}</h1>
        <p className="page-sub">
          Skill ratings computed from head-to-head tournament results — not points
          earned. Players ranked by a conservative Glicko-2 score.
        </p>
      </div>

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

        <div className="segmented">
          <button className={ranking === 'current' ? 'seg active' : 'seg'}
                  onClick={() => setRanking('current')}>Current</button>
          <button className={ranking === 'peak' ? 'seg active' : 'seg'}
                  onClick={() => setRanking('peak')}>All-time peak</button>
        </div>

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
        <PairsBoard key={`${event}-${ranking}`} event={event} ranking={ranking} />
      ) : (
        <IndividualBoard
          key={`${event}-${ranking}-${order}-${gender}`}
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
  const [page, setPage] = useState(0)
  const { data, error, loading } = useAsync(
    () =>
      api.leaderboard(event, {
        order, ranking, gender, minMatches: 5, limit: PAGE, offset: page * PAGE,
      }),
    [event, ranking, order, gender, page],
  )

  return (
    <>
      {!isPeak && (
        <div className="toolbar">
          <span className="muted small">Ranked by mu − 2·rd (conservative)</span>
          <Select
            label="Sort"
            value={order}
            onChange={setOrder}
            options={[
              { value: 'rating', label: 'Rating (mu − 2·rd)' },
              { value: 'mu', label: 'Skill (mu)' },
            ]}
          />
        </div>
      )}
      {loading && <p className="muted">Loading…</p>}
      {error && <p className="error">Could not load: {error.message}</p>}
      {data && (
        <table className="board">
          <thead>
            <tr>
              <th className="rank">#</th><th>Player</th>
              <th className="num">{isPeak ? 'Peak' : 'Rating'}</th>
              <th className="num">{isPeak ? 'When' : 'mu'}</th>
              <th className="num">rd</th>
              <th className="num">Matches</th>
            </tr>
          </thead>
          <tbody>
            {data.results.map((row, i) => {
              const rank = page * PAGE + i + 1
              return (
              <tr key={row.player.player_id}>
                <td className="rank"><Medal n={rank} /></td>
                <td>
                  <Link to={`/players/${row.player.player_id}`} className="pcell">
                    <Avatar player={row.player} />
                    <span className="pmeta">
                      <span className="pname">{row.player.name_display}</span>
                      <span className="psub">{row.player.country_code}</span>
                    </span>
                  </Link>
                </td>
                <td className="num"><span className="metric">
                  {isPeak ? row.peak_mu.toFixed(0) : row.rating.toFixed(1)}
                </span></td>
                <td className="num muted">
                  {isPeak ? (row.peak_utc ? row.peak_utc.slice(0, 7) : '—') : row.mu.toFixed(0)}
                </td>
                <td className="num muted">{(isPeak ? row.peak_rd : row.rd).toFixed(0)}</td>
                <td className="num muted">{row.matches_played}</td>
              </tr>
              )
            })}
          </tbody>
        </table>
      )}
      {data && <Pager page={page} setPage={setPage} count={data.count} />}
      {data && data.results.length === 0 && <p className="muted">No players.</p>}
    </>
  )
}

function PairsBoard({ event, ranking }) {
  const isPeak = ranking === 'peak'
  const [page, setPage] = useState(0)
  const { data, error, loading } = useAsync(
    () => api.pairs(event, { minMatches: 5, ranking, limit: PAGE, offset: page * PAGE }),
    [event, ranking, page],
  )
  if (loading) return <p className="muted">Loading pairs…</p>
  if (error) return <p className="error">Could not load pairs: {error.message}</p>
  return (
    <>
      <table className="board">
        <thead>
          <tr>
            <th className="rank">#</th><th>Pair</th>
            <th className="num">{isPeak ? 'Peak' : 'Rating'}</th>
            <th className="num">Together</th>
            <th className="num">Win%</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {data.results.map((row, i) => {
            const to = `/pairs/${event}/${row.player1.player_id}/${row.player2.player_id}`
            const rank = page * PAGE + i + 1
            return (
              <tr key={`${row.player1.player_id}-${row.player2.player_id}`}>
                <td className="rank"><Medal n={rank} /></td>
                <td>
                  <Link to={to} className="pcell">
                    <span className="pair-av">
                      <Avatar player={row.player1} size="sm" />
                      <Avatar player={row.player2} size="sm" />
                    </span>
                    <span className="pmeta">
                      <span className="pname">
                        {row.player1.name_display} / {row.player2.name_display}
                      </span>
                      <span className="psub">
                        {row.player1.country_code}
                        {row.player2.country_code !== row.player1.country_code
                          ? ` / ${row.player2.country_code}` : ''}
                      </span>
                    </span>
                  </Link>
                </td>
                <td className="num"><span className="metric">
                  {isPeak
                    ? row.peak_rating != null ? row.peak_rating.toFixed(0) : '—'
                    : row.rating.toFixed(1)}
                </span></td>
                <td className="num muted">{row.matches_together}</td>
                <td className="num strong">{row.win_pct != null ? `${row.win_pct}%` : '—'}</td>
                <td className="num"><Link to={to} className="muted small">view →</Link></td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <Pager page={page} setPage={setPage} count={data.count} />
      {data.results.length === 0 && <p className="muted">No pairs.</p>}
    </>
  )
}
