import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, EVENTS } from '../api.js'
import { useAsync } from '../useAsync.js'
import { flag } from '../flags.js'
import Avatar from '../components/Avatar.jsx'
import PageHeader from '../components/PageHeader.jsx'

// Pick one player via the search endpoint. Shows the chosen player as a chip
// with a clear button; typing again re-opens the results.
function PlayerPicker({ label, value, onPick, onClear }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const box = useRef(null)

  async function onChange(e) {
    const v = e.target.value
    setQ(v)
    if (v.trim().length < 2) return setResults([])
    try {
      const data = await api.searchPlayers(v.trim())
      setResults(data.results)
    } catch {
      setResults([])
    }
  }

  useEffect(() => {
    function away(e) {
      if (box.current && !box.current.contains(e.target)) setResults([])
    }
    document.addEventListener('click', away)
    return () => document.removeEventListener('click', away)
  }, [])

  if (value) {
    return (
      <div className="h2h-slot chosen">
        <Avatar player={value} size="lg" />
        <div className="h2h-slot-meta">
          <div className="pname">{value.name_display}</div>
          <div className="muted small">
            <span className="fl">{flag(value.country_code)}</span> {value.country_code}
          </div>
        </div>
        <button className="chip-x" onClick={onClear} aria-label="Clear">×</button>
      </div>
    )
  }

  return (
    <div className="h2h-slot" ref={box}>
      <div className="search h2h-search">
        <input
          value={q}
          onChange={onChange}
          placeholder={label}
          aria-label={label}
        />
        {results.length > 0 && (
          <ul className="search-results">
            {results.map((p) => (
              <li key={p.player_id}>
                <button
                  onClick={() => {
                    onPick(p)
                    setQ('')
                    setResults([])
                  }}
                >
                  <Avatar player={p} size="sm" />
                  <span className="pmeta">
                    <span className="pname">{p.name_display}</span>{' '}
                    <span className="flag">{p.country_code}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

function ProbBar({ prob, p1, p2 }) {
  if (prob == null) {
    return (
      <p className="muted">
        No rating for one of these players in this discipline — pick another event.
      </p>
    )
  }
  const pct1 = Math.round(prob * 100)
  const pct2 = 100 - pct1
  const fav = pct1 >= pct2
  return (
    <div className="prob">
      <div className="prob-heads">
        <div className={`prob-head ${fav ? 'fav' : ''}`}>
          <span className="prob-pct">{pct1}%</span>
          <span className="muted small">{p1.name_display}</span>
        </div>
        <div className="prob-vs muted">win probability</div>
        <div className={`prob-head right ${!fav ? 'fav' : ''}`}>
          <span className="prob-pct">{pct2}%</span>
          <span className="muted small">{p2.name_display}</span>
        </div>
      </div>
      <div className="prob-track">
        <div className="prob-fill p1" style={{ width: `${pct1}%` }} />
        <div className="prob-fill p2" style={{ width: `${pct2}%` }} />
      </div>
    </div>
  )
}

function RatingLine({ r }) {
  if (!r) return <span className="muted small">unrated</span>
  return (
    <span className="muted small">
      {r.rating.toFixed(0)} <span className="muted">· mu {r.mu.toFixed(0)} · {r.matches_played} matches</span>
    </span>
  )
}

function Matchup({ p1, p2, event }) {
  const { data, error, loading } = useAsync(
    () => api.h2h(event, p1.player_id, p2.player_id),
    [event, p1.player_id, p2.player_id],
  )
  if (loading) return <p className="muted">Loading matchup…</p>
  if (error) return <p className="error">Could not load: {error.message}</p>

  const rec = data.record
  return (
    <div className="h2h-result">
      <ProbBar prob={data.win_prob} p1={p1} p2={p2} />

      <div className="statgrid h2h-stats">
        <div className="statcard">
          <div className="k">Head-to-head</div>
          <div className="v">{rec.p1_wins}–{rec.p2_wins}</div>
          <div className="sub">{rec.meetings} meeting{rec.meetings === 1 ? '' : 's'}</div>
        </div>
        <div className="statcard">
          <div className="k">{p1.name_display}</div>
          <div className="v">{data.player1.rating ? data.player1.rating.rating.toFixed(0) : '—'}</div>
          <div className="sub"><RatingLine r={data.player1.rating} /></div>
        </div>
        <div className="statcard">
          <div className="k">{p2.name_display}</div>
          <div className="v">{data.player2.rating ? data.player2.rating.rating.toFixed(0) : '—'}</div>
          <div className="sub"><RatingLine r={data.player2.rating} /></div>
        </div>
      </div>

      <h2>Past meetings</h2>
      {rec.meetings === 0 ? (
        <p className="muted">These two have never met in {event}.</p>
      ) : (
        <table className="board">
          <thead>
            <tr>
              <th>Date</th>
              <th>Tournament</th>
              <th>Round</th>
              <th>Result</th>
              <th className="score-cell">Score</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data.meetings.map((m) => (
              <tr key={m.match_id}>
                <td className="muted small">
                  {m.match_time_utc ? m.match_time_utc.slice(0, 10) : '—'}
                </td>
                <td className="muted small">
                  {m.tournament ? (
                    <Link to={`/tournaments/${m.tournament.tournament_id}`}>
                      {m.tournament.name}
                    </Link>
                  ) : '—'}
                </td>
                <td className="muted small">{m.round_name}</td>
                <td>
                  {m.p1_won == null ? (
                    <span className="muted small">{m.score_status}</span>
                  ) : (
                    <span className={`wl ${m.p1_won ? 'w' : 'l'}`}>
                      {m.p1_won ? 'W' : 'L'}
                    </span>
                  )}
                </td>
                <td className="score-cell">
                  {m.score.map((g, i) => <span key={i}>{g[0]}-{g[1]} </span>)}
                  {m.score_status !== 'Normal' && (
                    <span className="muted small">({m.score_status})</span>
                  )}
                </td>
                <td><Link to={`/matches/${m.match_id}`} className="muted small">view →</Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default function H2H() {
  const [params] = useSearchParams()
  const [p1, setP1] = useState(null)
  const [p2, setP2] = useState(null)
  const [event, setEvent] = useState(
    EVENTS.some((e) => e.code === params.get('event')) ? params.get('event') : 'MS',
  )

  // Deep link: /h2h?p1=<id>&p2=<id>&event=<E> (e.g. from a player profile).
  // Runs once on mount to seed the pickers from the URL.
  useEffect(() => {
    for (const [key, set] of [['p1', setP1], ['p2', setP2]]) {
      const id = params.get(key)
      if (id) api.player(id).then(set).catch(() => {})
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div>
      <PageHeader
        kicker="Predictor"
        title="Head-to-Head"
        subtitle="Pick two players to see a Glicko-2 win probability, their all-time record, and every past meeting. The prediction uses each player's current rating in the chosen discipline."
      />

      <div className="h2h-picker">
        <PlayerPicker label="Search player 1…" value={p1}
                      onPick={setP1} onClear={() => setP1(null)} />
        <div className="h2h-vs">vs</div>
        <PlayerPicker label="Search player 2…" value={p2}
                      onPick={setP2} onClear={() => setP2(null)} />
      </div>

      <div className="toolbar">
        <div className="segmented">
          {EVENTS.map((e) => (
            <button key={e.code}
              className={event === e.code ? 'seg active' : 'seg'}
              onClick={() => setEvent(e.code)}>{e.code}</button>
          ))}
        </div>
      </div>

      {p1 && p2 ? (
        p1.player_id === p2.player_id ? (
          <p className="muted">Pick two different players.</p>
        ) : (
          <Matchup p1={p1} p2={p2} event={event} />
        )
      ) : (
        <p className="muted">Choose two players above to compare.</p>
      )}
    </div>
  )
}
