import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, EVENTS } from '../api.js'
import { useAsync } from '../useAsync.js'
import { flag } from '../flags.js'

const eventLabel = (code) => EVENTS.find((e) => e.code === code)?.label || code
const names = (players) => players.map((p) => p.name_display).join(' / ') || '—'
const shortTier = (s) => (s || '').replace('HSBC BWF World Tour ', '').replace('BWF ', '')

function isOngoing(t) {
  if (!t.start_date) return false
  const today = new Date().toISOString().slice(0, 10)
  return t.start_date <= today && today <= (t.end_date || t.start_date)
}

function EloTag({ e }) {
  if (!e) return null
  return (
    <span className={`elo-chip ${e.delta >= 0 ? 'pos' : 'neg'}`}>
      {e.delta >= 0 ? '+' : ''}{e.delta.toFixed(1)}
    </span>
  )
}

// One side of a match: flag + names, winner marked, with its ELO change.
function Side({ players, winner, elo, align }) {
  return (
    <div className={`mside ${align} ${winner ? 'win' : ''}`}>
      {winner && <span className="trophy">✓</span>}
      <span className="fl">{flag(players[0]?.country_code)}</span>
      <span className="mnames">{names(players)}</span>
      <EloTag e={elo} />
    </div>
  )
}

function Movers({ movers, event }) {
  const m = movers?.[event]
  if (!m || (!m.gainers.length && !m.losers.length)) return null
  const Row = ({ r, sign }) => (
    <div className="mover-row">
      <span className={`mover-delta ${sign}`}>
        {r.net_delta >= 0 ? '+' : ''}{r.net_delta.toFixed(0)}
      </span>
      <Link to={`/players/${r.player.player_id}`} className="mover-name">
        {r.player.name_display}{r.partner && ` / ${r.partner.name_display}`}
      </Link>
    </div>
  )
  return (
    <div className="movers">
      <div className="mover-col">
        <div className="mover-head pos">▲ Biggest gainers</div>
        {m.gainers.length ? m.gainers.map((r, i) => <Row key={i} r={r} sign="pos" />)
          : <p className="muted small">—</p>}
      </div>
      <div className="mover-col">
        <div className="mover-head neg">▼ Biggest losses</div>
        {m.losers.length ? m.losers.map((r, i) => <Row key={i} r={r} sign="neg" />)
          : <p className="muted small">—</p>}
      </div>
    </div>
  )
}

function MatchList({ id, events, movers }) {
  const [event, setEvent] = useState(events[0]?.event || 'MS')
  const [round, setRound] = useState('All')
  const { data, error, loading } = useAsync(
    () => api.tournamentMatches(id, { event, limit: 300 }),
    [id, event],
  )
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

      <Movers movers={movers} event={event} />

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
        <table className="board compact matchtable">
          <tbody>
            {shown.map((m) => {
              const te = m.team_elo || {}
              return (
                <tr key={m.match_id}>
                  <td className="rnd">
                    {m.round_name}
                    {m.score_status !== 'Normal' && (
                      <span className="pill warn tiny">{m.score_status}</span>
                    )}
                  </td>
                  <td className="side-cell">
                    <Side players={m.side1} winner={m.winner_side === 1}
                          elo={te['1']} align="r" />
                  </td>
                  <td className="score-cell mid">
                    {m.score.map((g, i) => (
                      <span key={i}>{g[0]}-{g[1]}{' '}</span>
                    ))}
                  </td>
                  <td className="side-cell">
                    <Side players={m.side2} winner={m.winner_side === 2}
                          elo={te['2']} align="l" />
                  </td>
                  <td className="num">
                    <Link to={`/matches/${m.match_id}`} className="muted small">view →</Link>
                  </td>
                </tr>
              )
            })}
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
      <header className="page-hero">
        <div className="page-hero-text">
          <div className="match-head">
            {t.category_name && <span className="pill">{shortTier(t.category_name)}</span>}
            {isOngoing(t) && <span className="badge-live">● Live</span>}
          </div>
          <h1>{t.name}</h1>
          <div className="meta">
            {t.venue_name && <span>📍 {t.venue_name}</span>}
            <span>🗓 {t.start_date} → {t.end_date}</span>
            {t.prize_money && <span>💰 ${Number(t.prize_money).toLocaleString()}</span>}
            <span>🏸 {t.match_count} matches</span>
          </div>
        </div>
      </header>

      {t.finals.length > 0 && (
        <>
          <h2>🏆 Champions</h2>
          <div className="champ-list">
            {t.finals.map((f) => (
              <div key={f.match_id} className="champ-row">
                <span className="champ-ev">{eventLabel(f.event)}</span>
                <span className="champ-who">
                  {f.champions.map((p, i) => (
                    <span key={p.player_id}>
                      {i > 0 ? ' / ' : ''}
                      <span className="fl">{flag(p.country_code)}</span>{' '}
                      <Link to={`/players/${p.player_id}`}>{p.name_display}</Link>
                    </span>
                  ))}
                  {f.champions.length === 0 && <span className="muted">—</span>}
                </span>
                <Link to={`/matches/${f.match_id}`} className="muted small">final →</Link>
              </div>
            ))}
          </div>
        </>
      )}

      {t.events?.length > 0 && (
        <>
          <h2>Matches</h2>
          <MatchList id={id} events={t.events} movers={t.movers} />
        </>
      )}
    </div>
  )
}
