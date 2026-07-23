import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, EVENTS } from '../api.js'
import { useAsync } from '../useAsync.js'
import { flag } from '../flags.js'
import Avatar from '../components/Avatar.jsx'
import PageHeader from '../components/PageHeader.jsx'

const DOUBLES = new Set(['MD', 'WD', 'XD'])
const capFor = (event) => (DOUBLES.has(event) ? 2 : 1)

// Search box that calls onPick(player) when a result is chosen.
function SearchPicker({ label, onPick }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const box = useRef(null)

  async function onChange(e) {
    const v = e.target.value
    setQ(v)
    if (v.trim().length < 2) return setResults([])
    try {
      setResults((await api.searchPlayers(v.trim())).results)
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

  return (
    <div className="search h2h-search" ref={box}>
      <input value={q} onChange={onChange} placeholder={label} aria-label={label} />
      {results.length > 0 && (
        <ul className="search-results">
          {results.map((p) => (
            <li key={p.player_id}>
              <button onClick={() => { onPick(p); setQ(''); setResults([]) }}>
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
  )
}

// One side of the matchup: up to `cap` players, shown as chips with an add box.
function SidePanel({ label, players, cap, onAdd, onRemove }) {
  return (
    <div className={`h2h-slot side${players.length ? ' chosen' : ''}`}>
      {players.map((p) => (
        <div className="h2h-chip" key={p.player_id}>
          <Avatar player={p} size="md" />
          <div className="h2h-slot-meta">
            <div className="pname">{p.name_display}</div>
            <div className="muted small"><span className="fl">{flag(p.country_code)}</span> {p.country_code}</div>
          </div>
          <button className="chip-x" onClick={() => onRemove(p.player_id)} aria-label="Remove">×</button>
        </div>
      ))}
      {players.length < cap && (
        <SearchPicker
          label={players.length ? 'Add partner…' : label}
          onPick={onAdd}
        />
      )}
    </div>
  )
}

function ProbBar({ prob, name1, name2 }) {
  if (prob == null) {
    return (
      <p className="muted">
        One side isn’t fully rated in this discipline — the win probability needs a
        current rating for every selected player.
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
          <span className="muted small">{name1}</span>
        </div>
        <div className="prob-vs muted">win probability</div>
        <div className={`prob-head right ${!fav ? 'fav' : ''}`}>
          <span className="prob-pct">{pct2}%</span>
          <span className="muted small">{name2}</span>
        </div>
      </div>
      <div className="prob-track">
        <div className="prob-fill p1" style={{ width: `${pct1}%` }} />
        <div className="prob-fill p2" style={{ width: `${pct2}%` }} />
      </div>
    </div>
  )
}

const sideName = (players) => players.map((p) => p.name_display).join(' / ')

function Matchup({ event, side1, side2 }) {
  const ids1 = side1.map((p) => p.player_id)
  const ids2 = side2.map((p) => p.player_id)
  const { data, error, loading } = useAsync(
    () => api.h2h(event, ids1, ids2),
    [event, ids1.join(','), ids2.join(',')],
  )
  if (loading) return <p className="muted">Loading matchup…</p>
  if (error) return <p className="error">Could not load: {error.message}</p>

  const rec = data.record
  const n1 = sideName(side1)
  const n2 = sideName(side2)
  return (
    <div className="h2h-result">
      <ProbBar prob={data.win_prob} name1={n1} name2={n2} />

      <div className="statgrid h2h-stats">
        <div className="statcard">
          <div className="k">Head-to-head</div>
          <div className="v">{rec.p1_wins}–{rec.p2_wins}</div>
          <div className="sub">{rec.meetings} meeting{rec.meetings === 1 ? '' : 's'}</div>
        </div>
        <div className="statcard">
          <div className="k">{n1}</div>
          <div className="v">{data.side1.rating ? data.side1.rating.rating.toFixed(0) : '—'}</div>
          <div className="sub muted small">
            {data.side1.rating ? `mu ${data.side1.rating.mu.toFixed(0)}` : 'unrated'}
          </div>
        </div>
        <div className="statcard">
          <div className="k">{n2}</div>
          <div className="v">{data.side2.rating ? data.side2.rating.rating.toFixed(0) : '—'}</div>
          <div className="sub muted small">
            {data.side2.rating ? `mu ${data.side2.rating.mu.toFixed(0)}` : 'unrated'}
          </div>
        </div>
      </div>

      <h2>Past meetings</h2>
      {rec.meetings === 0 ? (
        <p className="muted">
          {DOUBLES.has(event)
            ? 'This exact pairing has never met in ' + event + '.'
            : 'These two have never met in ' + event + '.'}
        </p>
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
                    <Link to={`/tournaments/${m.tournament.tournament_id}`}>{m.tournament.name}</Link>
                  ) : '—'}
                </td>
                <td className="muted small">{m.round_name}</td>
                <td>
                  {m.p1_won == null ? (
                    <span className="muted small">{m.score_status}</span>
                  ) : (
                    <span className={`wl ${m.p1_won ? 'w' : 'l'}`}>{m.p1_won ? 'W' : 'L'}</span>
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
  const [side1, setSide1] = useState([])
  const [side2, setSide2] = useState([])
  const [event, setEvent] = useState(
    EVENTS.some((e) => e.code === params.get('event')) ? params.get('event') : 'MS',
  )
  const cap = capFor(event)

  // Deep link: /h2h?event=E&s1=id,id&s2=id,id (or p1/p2 for a single player).
  useEffect(() => {
    async function load(keys, set) {
      for (const k of keys) {
        const raw = params.get(k)
        if (raw) {
          const ids = raw.split(',').filter(Boolean)
          const ps = await Promise.all(ids.map((id) => api.player(id).catch(() => null)))
          set(ps.filter(Boolean))
          return
        }
      }
    }
    load(['s1', 'p1'], setSide1)
    load(['s2', 'p2'], setSide2)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Dropping to singles trims each side back to one player.
  useEffect(() => {
    setSide1((s) => s.slice(0, cap))
    setSide2((s) => s.slice(0, cap))
  }, [cap])

  const addTo = (setter) => (p) =>
    setter((s) => (s.some((x) => x.player_id === p.player_id) ? s : [...s, p].slice(0, cap)))
  const removeFrom = (setter) => (id) => setter((s) => s.filter((x) => x.player_id !== id))

  const ready = side1.length === cap && side2.length === cap
  const overlap = side1.some((a) => side2.some((b) => b.player_id === a.player_id))

  return (
    <div>
      <PageHeader
        kicker="Predictor"
        title="Head-to-Head"
        subtitle="Pick two players — or two pairs for doubles — to see a Glicko-2 win probability, the all-time record, and every past meeting. The prediction uses each player's current rating in the chosen discipline."
      />

      <div className="toolbar">
        <div className="segmented">
          {EVENTS.map((e) => (
            <button key={e.code}
              className={event === e.code ? 'seg active' : 'seg'}
              onClick={() => setEvent(e.code)}>{e.code}</button>
          ))}
        </div>
        {DOUBLES.has(event) && (
          <span className="muted small">Pick a pair (2 players) per side.</span>
        )}
      </div>

      <div className="h2h-picker">
        <SidePanel label={cap > 1 ? 'Search side 1…' : 'Search player 1…'}
                   players={side1} cap={cap}
                   onAdd={addTo(setSide1)} onRemove={removeFrom(setSide1)} />
        <div className="h2h-vs">vs</div>
        <SidePanel label={cap > 1 ? 'Search side 2…' : 'Search player 2…'}
                   players={side2} cap={cap}
                   onAdd={addTo(setSide2)} onRemove={removeFrom(setSide2)} />
      </div>

      {overlap ? (
        <p className="muted">A player can’t be on both sides.</p>
      ) : ready ? (
        <Matchup event={event} side1={side1} side2={side2} />
      ) : (
        <p className="muted">
          {DOUBLES.has(event)
            ? 'Choose a pair on each side to compare.'
            : 'Choose two players above to compare.'}
        </p>
      )}
    </div>
  )
}
