import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, EVENTS } from '../api.js'
import { useAsync } from '../useAsync.js'
import { flag } from '../flags.js'
import { SkeletonList, TournamentSkeleton } from '../components/Skeleton.jsx'
import { ErrorState } from '../components/Empty.jsx'
import Avatar from '../components/Avatar.jsx'
import Icon from '../components/Icon.jsx'
import Tier from '../components/Tier.jsx'
import { Delta, Ev } from '../components/Chips.jsx'
import { fmtRange, isLive } from '../dates.js'

const eventLabel = (code) => EVENTS.find((e) => e.code === code)?.label || code

// Fixed discipline order for a tournament's champions + match tabs (the API
// returns them by match count; we want the conventional MS WS MD WD XD).
const EVENT_ORDER = ['MS', 'WS', 'MD', 'WD', 'XD']
const eventRank = (code) => {
  const i = EVENT_ORDER.indexOf(code)
  return i === -1 ? 99 : i
}

const ROUND_LABEL = { QF: 'Quarter-finals', SF: 'Semi-finals', F: 'Final' }
const roundLabel = (r) => ROUND_LABEL[r] || r


function EloTag({ e }) {
  if (!e) return null
  return <Delta value={e.delta} />
}

// One side of a match as three fixed grid cells (name · flag · elo), so rows
// stay symmetric even when a player has no flag. Returns a fragment (no wrapper)
// so the cells sit directly in the row grid; order mirrors on side 2.
function Side({ players, winner, elo, side }) {
  const cc = players[0]?.country_code
  const name = (
    <span className={`mrow-name s${side} ${winner ? 'win' : ''}`}>
      {players.map((p) => (
        <Link key={p.player_id} to={`/players/${p.player_id}`} className="mname">
          {p.name_display}
        </Link>
      ))}
    </span>
  )
  const fl = <span className="mrow-flag">{cc ? flag(cc) : ''}</span>
  const eloCell = <span className={`mrow-elo s${side}`}><EloTag e={elo} /></span>
  return side === 1
    ? <>{name}{fl}{eloCell}</>
    : <>{eloCell}{fl}{name}</>
}

// Net rating change across the event: gainers to the right, losers to the left.
function Movers({ movers, event }) {
  const m = movers?.[event]
  if (!m || (!m.gainers.length && !m.losers.length)) return null
  const rows = [...m.gainers, ...m.losers]
  const mx = Math.max(1, ...rows.map((r) => Math.abs(r.net_delta)))
  return (
    <section className="card t-panel">
      <div className="t-panel-h"><h3>Rating movers</h3><span className="muted small">net change this event</span></div>
      <div className="mv-list">
        {rows.map((r, i) => {
          const up = r.net_delta >= 0
          return (
            <div key={i} className="mv">
              <Link to={`/players/${r.player.player_id}`} className="mv-nm">
                <span className="fl">{flag(r.player.country_code)}</span>
                {r.player.name_display}{r.partner && ` / ${r.partner.name_display}`}
              </Link>
              <span className="mv-tr">
                <i className={up ? 'up' : 'dn'} style={{ width: `${(Math.abs(r.net_delta) / mx) * 50}%` }}>
                  {up ? '+' : '−'}{Math.abs(r.net_delta).toFixed(0)}
                </i>
              </span>
            </div>
          )
        })}
      </div>
    </section>
  )
}

// Quarter-finals → final as a compact bracket, ordered so each match feeds
// the one beside it.
const ids = (m) => [...m.side1, ...m.side2].map((p) => p.player_id)
const isFinal = (r) => r === 'F' || r === 'Final'
function Bracket({ matches }) {
  const fin = matches.filter((m) => isFinal(m.round_name))
  const sf = matches.filter((m) => m.round_name === 'SF')
  const qf = matches.filter((m) => m.round_name === 'QF')
  if (!fin.length || !sf.length) return null
  const F = fin[0]
  const sideIds = (side) => side.map((p) => p.player_id)
  const has = (m, pids) => ids(m).some((x) => pids.includes(x))
  const sfs = [...sf].sort((a) => (has(a, sideIds(F.side1)) ? -1 : 1))
  const qfs = []
  sfs.forEach((s) => [s.side1, s.side2].forEach((side) => {
    const q = qf.find((m) => has(m, sideIds(side)) && !qfs.includes(m))
    if (q) qfs.push(q)
  }))
  const Box = ({ m }) => {
    const abnormal = m.score_status && m.score_status !== 'Normal'
    const row = (side, n) => (
      <Link to={`/matches/${m.match_id}`} className={m.winner_side === n ? 'w' : 'l'}>
        <span className="bm-nm"><span className="fl">{flag(side[0]?.country_code)}</span>{side.map((p) => p.name_display).join(' / ')}</span>
        <span className="bm-g">{abnormal && n === 1 ? <span className="pill warn tiny">{m.score_status}</span> : (m.score || []).map((g, i) => <span key={i}>{g[n - 1]}</span>)}</span>
      </Link>
    )
    return <div className="bm">{row(m.side1, 1)}{row(m.side2, 2)}</div>
  }
  return (
    <section className="card t-panel">
      <div className="t-panel-h"><h3>Final rounds</h3></div>
      <div className={`bracket cols-${qfs.length ? 3 : 2}`}>
        {qfs.length > 0 && <div className="bcol"><span className="bh">Quarter-finals</span>{qfs.map((m) => <Box key={m.match_id} m={m} />)}</div>}
        <div className="bcol"><span className="bh">Semi-finals</span>{sfs.map((m) => <Box key={m.match_id} m={m} />)}</div>
        <div className="bcol"><span className="bh">Final</span><Box m={F} /></div>
      </div>
    </section>
  )
}

function MatchList({ id, events, movers }) {
  const [event, setEvent] = useState(events[0]?.event || 'MS')
  const [round, setRound] = useState(null)
  const { data, error, loading, reload } = useAsync(
    () => api.tournamentMatches(id, { event, limit: 300 }),
    [id, event],
  )
  const rounds = data
    ? [...new Map(data.results.map((m) => [m.round_name, m.round_order])).entries()]
        .sort((a, b) => a[1] - b[1])
        .map(([name]) => name)
    : []
  // Default to the earliest round (no "All" tab); fall back if the chosen round
  // isn't in this discipline.
  const activeRound = round && rounds.includes(round) ? round : rounds[0]
  const shown = data ? data.results.filter((m) => m.round_name === activeRound) : []

  return (
    <>
      <div className="t-tabs">
        <div className="tabs" role="tablist" aria-label="Discipline">
          {events.map((e) => (
            <button key={e.event} role="tab" aria-selected={e.event === event}
              className={`tab ${e.event === event ? 'active' : ''}`}
              onClick={() => { setEvent(e.event); setRound(null) }}>
              {e.event}
              <span className="tab-label">{e.n} matches</span>
            </button>
          ))}
        </div>
      </div>

      <div className="t-grid">
        {data && <Bracket matches={data.results} />}
        <Movers movers={movers} event={event} />
      </div>

      <div className="sec-head" style={{ marginTop: 22 }}><h2>All matches · {eventLabel(event)}</h2></div>

      {rounds.length > 1 && (
        <div className="roundtabs">
          {rounds.map((r) => (
            <button key={r} className={`rtab ${activeRound === r ? 'active' : ''}`}
                    onClick={() => setRound(r)}>{r}</button>
          ))}
        </div>
      )}
      {loading && <SkeletonList rows={8} />}
      {error && <ErrorState error={error} onRetry={reload} what="matches" />}
      {data && (
        <div className="mlist card">
          {shown.map((m) => {
            const te = m.team_elo || {}
            return (
              <div key={m.match_id} className="mrow">
                <span className="mrow-round">
                  {m.round_name}
                  {m.score_status !== 'Normal' && (
                    <span className="pill warn tiny">{m.score_status}</span>
                  )}
                </span>
                <Side players={m.side1} winner={m.winner_side === 1}
                      elo={te['1']} side={1} />
                <span className="mrow-score">
                  <GameScore matchId={m.match_id} score={m.score}
                             status={m.score_status} />
                </span>
                <Side players={m.side2} winner={m.winner_side === 2}
                      elo={te['2']} side={2} />
              </div>
            )
          })}
        </div>
      )}
    </>
  )
}

// Stacked player links (one per line), aligned toward the centre by side.
function SideNames({ players, side, winner }) {
  return (
    <span className={`mrow-name s${side} ${winner ? 'win' : ''}`}>
      {players.map((p) => (
        <Link key={p.player_id} to={`/players/${p.player_id}`} className="mname">
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

// One rubber inside a tie, laid out on the shared tie grid so the score column
// lines up with the tie header's country score. Winner shown by bold + tint.
// order · discipline · name1 · elo1 · score · elo2 · name2 (no per-row flags).
function Rubber({ r }) {
  return (
    <div className="rubber tie-grid">
      <span className="rubber-ord">{r.order}</span>
      <span className="rubber-disc">{r.discipline}</span>
      <SideNames players={r.side1} side={1} winner={r.winner_side === 1} />
      <span className="mrow-elo s1"><EloTag e={r.elo1 != null ? { delta: r.elo1 } : null} /></span>
      <span className="mrow-score">
        <GameScore matchId={r.match_id} score={r.score} status={r.score_status} />
      </span>
      <span className="mrow-elo s2"><EloTag e={r.elo2 != null ? { delta: r.elo2 } : null} /></span>
      <SideNames players={r.side2} side={2} winner={r.winner_side === 2} />
    </div>
  )
}

// One nation-vs-nation tie: header (country score, aligned to the rubber grid)
// + its rubbers.
function Tie({ tie }) {
  const c1win = tie.winner_country === tie.country1
  const c2win = tie.winner_country === tie.country2
  return (
    <div className="tie-card">
      <div className="tie-head tie-grid">
        <span /><span />
        <span className={`tie-team s1 ${c1win ? 'win' : ''}`}>
          <span className="fl">{flag(tie.country1)}</span>{tie.country1}
        </span>
        <span />
        <span className="tie-score">{tie.score1}<span className="dash">–</span>{tie.score2}</span>
        <span />
        <span className={`tie-team s2 ${c2win ? 'win' : ''}`}>
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
        <Icon name={open ? 'arrowDown' : 'arrowRight'} size={13} className="caret" />
        <span className="cup-section-title">{title}</span>
        {sub && <span className="cup-section-sub">{sub}</span>}
      </button>
      {open && <div className="cup-section-body">{children}</div>}
    </section>
  )
}

const tieCount = (n) => `${n} ${n === 1 ? 'tie' : 'ties'}`

function TeamCup({ id }) {
  const { data, error, loading, reload } = useAsync(() => api.tournamentTies(id), [id])
  if (loading) return <SkeletonList rows={8} />
  if (error) return <ErrorState error={error} onRetry={reload} what="the ties" />

  const groups = data.rounds.filter((r) => /^group/i.test(r.round_name))
  const knockout = data.rounds.filter((r) => !/^group/i.test(r.round_name))

  return (
    <div className="teamcup">
      {data.champion && (
        <div className="cup-champion">
          <span className="cup-trophy"><Icon name="trophy" size={24} /></span>
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
              {rd.ties.map((tie, i) => <Tie key={i} tie={tie} />)}
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
  const { data: t, error, loading, reload } = useAsync(() => api.tournament(id), [id])
  const [logoFailed, setLogoFailed] = useState(false)

  if (loading) return <TournamentSkeleton />
  if (error) return <ErrorState error={error} onRetry={reload} what="this tournament" />

  // Present champions + match tabs in the conventional discipline order.
  const finals = [...(t.finals || [])].sort((a, b) => eventRank(a.event) - eventRank(b.event))
  const events = [...(t.events || [])].sort((a, b) => eventRank(a.event) - eventRank(b.event))

  const logo = !logoFailed && t.logo_url && !/placeholder/i.test(t.logo_url) ? t.logo_url : null
  return (
    <div className="tournament-page">
      <div className="crumb">
        <Link to="/tournaments">Tournaments</Link><span className="sep">/</span>
        <Link to={`/tournaments?year=${(t.start_date || '').slice(0, 4)}`}>{(t.start_date || '').slice(0, 4)}</Link>
      </div>
      <header className="t-head">
        <span className="t-emblem">{logo ? <img src={logo} alt="" onError={() => setLogoFailed(true)} /> : <Icon name="trophy" size={30} />}</span>
        <div className="t-id">
          <div className="t-chips">
            {t.category_name && <Tier category={t.category_name} />}
            {isLive(t) && <span className="live">LIVE</span>}
          </div>
          <h1>{t.name}</h1>
          <div className="t-meta">
            {t.venue_name && <span><Icon name="pin" size={14} /> {t.venue_name}</span>}
            {t.start_date && <span><Icon name="calendar" size={14} /> {fmtRange(t.start_date, t.end_date, true)}</span>}
            {t.prize_money && <span><Icon name="coin" size={14} /> ${Number(t.prize_money).toLocaleString()}</span>}
            <span>{t.match_count} matches{events.length ? ` · ${events.length} disciplines` : ''}</span>
          </div>
        </div>
      </header>

      {t.is_team_cup ? (
        <TeamCup id={id} />
      ) : (
        <>
          {finals.length > 0 && (
            <section>
              <div className="sec-head"><h2>Champions</h2></div>
              <div className="champs">
                {finals.map((f) => (
                  <Link key={f.match_id} to={`/matches/${f.match_id}`} className="champ card">
                    <Ev code={f.event} />
                    <span className="pair-av">{f.champions.map((p) => <Avatar key={p.player_id} player={p} size={40} />)}</span>
                    <span className="champ-nm">{f.champions.map((p) => p.name_display).join(' / ') || '—'}</span>
                    <span className="champ-lab">{f.champions[0] ? `${flag(f.champions[0].country_code)} ${f.champions[0].country_code} · ` : ''}{eventLabel(f.event)}</span>
                  </Link>
                ))}
              </div>
            </section>
          )}

          {events.length > 0 && <MatchList id={id} events={events} movers={t.movers} />}
        </>
      )}
    </div>
  )
}
