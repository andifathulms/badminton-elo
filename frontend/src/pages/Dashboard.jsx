import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, EVENTS } from '../api.js'
import { useAsync } from '../useAsync.js'
import Avatar from '../components/Avatar.jsx'
import Entity from '../components/Entity.jsx'
import Sparkline from '../components/Sparkline.jsx'
import Tier from '../components/Tier.jsx'
import Icon from '../components/Icon.jsx'
import CourtLines from '../components/CourtLines.jsx'
import { Ev, Move } from '../components/Chips.jsx'
import { Skeleton, SkeletonList } from '../components/Skeleton.jsx'
import CountUp from '../components/CountUp.jsx'
import { flag } from '../flags.js'
import { fmtRange, isLive, today } from '../dates.js'
import { homeData } from '../featured.js'

const DOUBLES = new Set(['MD', 'WD', 'XD'])
const isDoubles = (e) => DOUBLES.has(e)
const names = (ps) => ps.map((p) => p.name_display).join(' / ')

function SectionHead({ title, to, linkText, children }) {
  return (
    <div className="sec-head">
      <h2>{title}</h2>
      {children}
      {to && <Link to={to} className="view-all">{linkText || 'View all'} <Icon name="arrowRight" size={13} /></Link>}
    </div>
  )
}

const ORDER = ['MS', 'WS', 'MD', 'WD', 'XD']

function Hero({ home }) {
  const events = home?.events
  const tcount = home?.tournaments
  const calib = home?.calibration
  const major = home?.major
  const totalRated = events ? events.reduce((a, e) => a + e.rated_players, 0) : null
  const liveCount = tcount ? tcount.results.filter(isLive).length : 0
  const finals = major ? [...(major.finals || [])].sort((a, b) => ORDER.indexOf(a.event) - ORDER.indexOf(b.event)) : []
  return (
    <section className="home-hero arena">
      <CourtLines />
      <div className="hh-copy">
        <div className="hh-kick">
          {liveCount > 0 && <span className="live">LIVE</span>}
          <span>{liveCount > 0 ? `${liveCount} events in progress` : 'Ratings from every BWF result'}</span>
        </div>
        <h1>Every rally,<br />quantified.</h1>
        <p>
          Skill ratings for every BWF player, built from {calib?.n ? calib.n.toLocaleString() : 'hundreds of thousands of'} matches.
          Ratings move on who you beat, not on points earned.
        </p>
        <div className="hh-stats">
          <div><b>{totalRated ? <CountUp value={totalRated} /> : '—'}</b><span>rated players</span></div>
          <div><b>{tcount ? <CountUp value={tcount.count} /> : '—'}</b><span>tournaments</span></div>
          {calib?.accuracy != null && (
            <Link to="/insights?lens=calibration" title="How often the higher-rated side wins">
              <b><CountUp value={calib.accuracy * 100} format={(n) => `${n.toFixed(1)}%`} /></b>
              <span>results called right</span>
            </Link>
          )}
          <div><b>5</b><span>disciplines</span></div>
        </div>
      </div>
      <div className="hh-feature glass">
        {major ? (
          <>
            <Link to={`/tournaments/${major.tournament_id}`} className="gt">
              <b>{major.name.replace(/^(HSBC |BWF |TotalEnergies )/, '')}</b>
              <span>{major.venue_name ? `${major.venue_name.split(',')[0]} · ` : ''}{fmtRange(major.start_date, major.end_date)}</span>
            </Link>
            <div className="gt-sub">Champions</div>
            {finals.map((f) => (
              <Link key={f.event} to={`/matches/${f.match_id}`} className="crow">
                <Ev code={f.event} />
                <span className="pair-av">{f.champions.map((p) => <Avatar key={p.player_id} player={p} size={26} onDeep />)}</span>
                <span className="nm">{names(f.champions)} <span className="fl">{flag(f.champions[0].country_code)}</span></span>
              </Link>
            ))}
          </>
        ) : (
          <div className="hh-sk">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} h={i ? 26 : 18} w={i ? '100%' : '60%'} style={{ background: 'rgba(255,255,255,.08)' }} />)}</div>
        )}
      </div>
    </section>
  )
}

// Reigning No. 1 + the gap to No. 2, per discipline (from the home payload's
// top-2 board for that discipline).
function no1Of(event, d) {
  const [a, b] = d?.results || []
  if (!a) return { event, players: null }
  const pair = !!a.player1
  return {
    event,
    players: pair ? [a.player1, a.player2] : [a.player],
    rating: a.rating,
    lead: b ? a.rating - b.rating : null,
    form: a.form,
    together: a.matches_together,
    to: pair ? `/pairs/${event.code}/${a.player1.player_id}/${a.player2.player_id}` : `/players/${a.player.player_id}`,
  }
}

function WorldNo1s({ home }) {
  const data = home ? EVENTS.map((e) => no1Of(e, home.no1s[e.code])) : null
  if (!data) {
    return <div className="no1-grid">{EVENTS.map((e) => <div key={e.code} className="no1 card"><Skeleton h={150} /></div>)}</div>
  }
  const maxLead = Math.max(1, ...data.map((d) => d.lead || 0))
  return (
    <div className="no1-grid">
      {data.filter((d) => d.players).map((d) => (
        <Link key={d.event.code} to={d.to} className="no1 card">
          <div className="no1-hd"><Ev code={d.event.code} /><span>{d.event.label}</span></div>
          <span className="pair-av">{d.players.map((p) => <Avatar key={p.player_id} player={p} size={42} />)}</span>
          <div className="no1-nm">
            {names(d.players)}
            <span className="no1-cc">{flag(d.players[0].country_code)} {d.players[0].country_code}</span>
          </div>
          <div className="no1-rt">
            <span className="num-display">{Math.round(d.rating).toLocaleString()}</span>
            {d.form?.length > 1
              ? <Sparkline values={d.form} width={64} height={26} />
              : d.together ? <span className="no1-tog">{d.together} matches<br />together</span> : null}
          </div>
          {d.lead != null && (
            <div className="lead" title="Rating gap to the No. 2">
              <span><b>+{Math.round(d.lead)}</b> ahead of No. 2</span>
              <span className="lead-bar"><i style={{ width: `${Math.max(4, (d.lead / maxLead) * 100)}%` }} /></span>
            </div>
          )}
        </Link>
      ))}
    </div>
  )
}

function MiniBoard({ initial }) {
  const [event, setEvent] = useState('MS')
  const doubles = isDoubles(event)
  // The MS board arrives with the home payload (null until it lands); other
  // tabs load on demand.
  const { data } = useAsync(
    () => (event === 'MS' ? Promise.resolve(initial ?? null)
      : doubles ? api.pairs(event, { limit: 6, minMatches: 5 }) : api.leaderboard(event, { limit: 6, minMatches: 5 })),
    [event, initial],
  )
  const label = EVENTS.find((e) => e.code === event)?.label
  return (
    <section className="panel">
      <SectionHead title={label} to={`/rankings?event=${event}`} linkText="Full rankings">
        <div className="segmented sm" role="tablist" aria-label="Discipline">
          {EVENTS.map((e) => (
            <button key={e.code} role="tab" aria-selected={e.code === event}
              className={`seg ${e.code === event ? 'active' : ''}`} onClick={() => setEvent(e.code)}>{e.code}</button>
          ))}
        </div>
      </SectionHead>
      {!data && <SkeletonList rows={6} />}
      {data && (
        <ol className="rank-rows">
          {data.results.map((row, i) => {
            // Derive the shape from the row: while a tab switch loads, `data`
            // still holds the previous event's rows for one render.
            const players = row.player1 ? [row.player1, row.player2] : [row.player]
            return (
              <li key={players.map((p) => p.player_id).join('-')}>
                <span className={`medal sm ${i < 3 ? `m${i + 1}` : ''}`}>{i + 1}</span>
                <Entity players={players} event={event} sub={row.win_pct != null ? `${Math.round(row.win_pct)}% wins` : null} />
                {row.form ? <Sparkline values={row.form} width={92} height={26} className="hide-sm" /> : <span />}
                <span className="rr-rating num-display">{Math.round(row.rating).toLocaleString()}</span>
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}

function ThisWeek({ home }) {
  const data = home?.tournaments
  const loading = !home
  return (
    <section className="panel">
      <SectionHead title="This week" to="/tournaments" linkText="Calendar" />
      {loading && <SkeletonList rows={6} />}
      {data && (
        <ul className="week-rows">
          {data.results.slice(0, 7).map((t) => {
            const live = isLive(t)
            return (
              <li key={t.tournament_id}>
                <Link to={`/tournaments/${t.tournament_id}`}>
                  <span className="wk-name">{t.name}</span>
                  <span className="wk-when">{live ? <span className="live">LIVE</span> : fmtRange(t.start_date, t.end_date)}</span>
                  <span className="wk-meta"><Tier category={t.category_name} />
                    <span>{live && t.end_date === today() ? 'Finals today · ' : ''}{t.match_count} matches</span></span>
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

function Upsets({ home }) {
  const navigate = useNavigate()
  const data = home?.upsets
  return (
    <section>
      <SectionHead title="Giant-killings" to="/insights?lens=upsets" linkText="All upsets" />
      <div className="upset-cards">
        {!data && Array.from({ length: 3 }).map((_, i) => <div key={i} className="card upc"><Skeleton h={120} /></div>)}
        {data?.results.map((u) => {
          const w = [u.player, u.partner].filter(Boolean)
          const gap = u.opponent_rating_before - u.winner_rating_before
          const mx = Math.max(u.opponent_rating_before, u.winner_rating_before)
          return (
            <button key={`${u.player.player_id}-${u.best_match}`} className="card upc"
              onClick={() => u.best_match && navigate(`/matches/${u.best_match}`)}>
              <div className="upc-top"><Ev code={u.event} /><span className="upc-gap num-display">+{Math.round(gap)}</span></div>
              <div className="upc-who"><b>{names(w)}</b> {flag(w[0].country_code)} beat <b>{names(u.beat)}</b> {flag(u.beat[0]?.country_code)}</div>
              <div className="vs-bars">
                <div><span className="b"><i style={{ width: `${(u.winner_rating_before / mx) * 100}%` }}>Winner</i></span><span className="mono">{u.winner_rating_before}</span></div>
                <div><span className="b lo"><i style={{ width: `${(u.opponent_rating_before / mx) * 100}%` }}>Favourite</i></span><span className="mono">{u.opponent_rating_before}</span></div>
              </div>
              <div className="upc-foot">{u.tournament.name} · {u.best_round}{u.best_score ? ` · ${u.best_score.map((g) => g.join('–')).join(', ')}` : ''}</div>
            </button>
          )
        })}
      </div>
    </section>
  )
}

export default function Dashboard() {
  // One request for the whole page (it used to be ~18).
  const { data: home } = useAsync(homeData, [])
  return (
    <div className="dashboard">
      <Hero home={home} />
      <section>
        <SectionHead title="World No. 1s" to="/rankings" linkText="All rankings" />
        <WorldNo1s home={home} />
      </section>
      <div className="dash-grid">
        <MiniBoard initial={home?.board} />
        <ThisWeek home={home} />
      </div>
      <Upsets home={home} />
    </div>
  )
}
