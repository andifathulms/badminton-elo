import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, EVENTS } from '../api.js'
import { useAsync } from '../useAsync.js'
import { flag } from '../flags.js'

const eventLabel = (code) => EVENTS.find((e) => e.code === code)?.label || code
const shortTier = (s) => (s || '').replace('HSBC BWF World Tour ', '').replace('BWF ', '')

const ROUND_LABEL = { QF: 'Quarter-finals', SF: 'Semi-finals', F: 'Final' }
const roundLabel = (r) => ROUND_LABEL[r] || r

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

// One side of a match: flag + player links (stacked for pairs), winner shown by
// bold + a subtle tint, with the side's ELO change.
function Side({ players, winner, elo, align }) {
  return (
    <div className={`mside ${align} ${winner ? 'win' : ''}`}>
      <span className="fl">{flag(players[0]?.country_code)}</span>
      <span className="mside-players">
        {players.map((p) => (
          <Link key={p.player_id} to={`/players/${p.player_id}`} className="mname">
            {p.name_display}
          </Link>
        ))}
      </span>
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
                    <GameScore matchId={m.match_id} score={m.score}
                               status={m.score_status} />
                  </td>
                  <td className="side-cell">
                    <Side players={m.side2} winner={m.winner_side === 2}
                          elo={te['2']} align="l" />
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

// Stacked player links: one name per line, each links to its player page.
function SidePlayers({ players }) {
  return (
    <span className="rubber-players">
      {players.map((p) => (
        <Link key={p.player_id} to={`/players/${p.player_id}`} className="rubber-pname">
          {p.name_display}
        </Link>
      ))}
    </span>
  )
}

// The score, linking to the match; the winning point of each game is bold.
function GameScore({ matchId, score, status }) {
  const inner = status && status !== 'Normal'
    ? <span className="pill warn tiny">{status}</span>
    : (score || []).map(([a, b], i) => (
        <span key={i} className="game">
          <span className={a > b ? 'gp win' : 'gp'}>{a}</span>
          <span className="gp-sep">-</span>
          <span className={b > a ? 'gp win' : 'gp'}>{b}</span>
        </span>
      ))
  return (
    <Link to={`/matches/${matchId}`} className="score-link">{inner}</Link>
  )
}

// One rubber inside a tie: order · discipline · side1 · score · side2.
// Winner is shown by bold + a subtle highlight (no check mark).
function Rubber({ r }) {
  return (
    <div className="rubber">
      <span className="rubber-ord">{r.order}</span>
      <span className="rubber-disc">{r.discipline}</span>
      <span className={`rubber-side r ${r.winner_side === 1 ? 'win' : ''}`}>
        <SidePlayers players={r.side1} />
      </span>
      <GameScore matchId={r.match_id} score={r.score} status={r.score_status} />
      <span className={`rubber-side l ${r.winner_side === 2 ? 'win' : ''}`}>
        <SidePlayers players={r.side2} />
      </span>
    </div>
  )
}

// One nation-vs-nation tie: header (country score) + its rubbers.
function Tie({ tie }) {
  const c1win = tie.winner_country === tie.country1
  const c2win = tie.winner_country === tie.country2
  return (
    <div className="tie-card">
      <div className="tie-head">
        <span className={`tie-team r ${c1win ? 'win' : ''}`}>
          <span className="fl">{flag(tie.country1)}</span>{tie.country1}
        </span>
        <span className="tie-score">{tie.score1}<span className="dash">–</span>{tie.score2}</span>
        <span className={`tie-team l ${c2win ? 'win' : ''}`}>
          {tie.country2}<span className="fl">{flag(tie.country2)}</span>
        </span>
      </div>
      <div className="rubbers">
        {tie.rubbers.map((r) => <Rubber key={r.match_id} r={r} />)}
      </div>
    </div>
  )
}

// A collapsible section with a header that toggles its body.
function Collapsible({ title, sub, defaultOpen = true, children }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <section className={`cup-section ${open ? 'open' : ''}`}>
      <button className="cup-section-head" onClick={() => setOpen(!open)}>
        <span className="caret">{open ? '▾' : '▸'}</span>
        <span className="cup-section-title">{title}</span>
        {sub && <span className="cup-section-sub">{sub}</span>}
      </button>
      {open && <div className="cup-section-body">{children}</div>}
    </section>
  )
}

const tieCount = (n) => `${n} ${n === 1 ? 'tie' : 'ties'}`

function TeamCup({ id }) {
  const { data, error, loading } = useAsync(() => api.tournamentTies(id), [id])
  if (loading) return <p className="muted">Loading ties…</p>
  if (error) return <p className="error">Could not load ties: {error.message}</p>

  const groups = data.rounds.filter((r) => /^group/i.test(r.round_name))
  const knockout = data.rounds.filter((r) => !/^group/i.test(r.round_name))

  return (
    <div className="teamcup">
      {data.champion && (
        <div className="cup-champion">
          <span className="cup-trophy">🏆</span>
          <span className="fl big">{flag(data.champion)}</span>
          <span className="cup-champion-name">{data.champion}</span>
          <span className="cup-champion-label">Champions</span>
        </div>
      )}

      {groups.length > 0 && (
        <>
          <h2>Group Stage</h2>
          {/* Groups are the longest part — collapsed by default. */}
          {groups.map((rd) => (
            <Collapsible key={rd.round_name} title={rd.round_name}
              sub={tieCount(rd.ties.length)} defaultOpen={false}>
              <div className="group-ties">
                {rd.ties.map((tie, i) => <Tie key={i} tie={tie} />)}
              </div>
            </Collapsible>
          ))}
        </>
      )}

      {knockout.length > 0 && <h2>Knockout</h2>}
      {knockout.map((rd) => (
        <Collapsible key={rd.round_name} title={roundLabel(rd.round_name)}
          sub={tieCount(rd.ties.length)} defaultOpen>
          {rd.ties.map((tie, i) => <Tie key={i} tie={tie} />)}
        </Collapsible>
      ))}
    </div>
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

      {t.is_team_cup ? (
        <TeamCup id={id} />
      ) : (
        <>
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
        </>
      )}
    </div>
  )
}
