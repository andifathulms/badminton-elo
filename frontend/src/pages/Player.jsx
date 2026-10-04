import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, EVENTS } from '../api.js'
import { useAsync } from '../useAsync.js'
import RatingChart from '../components/RatingChart.jsx'
import MatchHistory from '../components/MatchHistory.jsx'
import StyleCard from '../components/StyleCard.jsx'
import Avatar from '../components/Avatar.jsx'
import Confidence from '../components/Confidence.jsx'
import Icon from '../components/Icon.jsx'
import CourtLines from '../components/CourtLines.jsx'
import { Ev } from '../components/Chips.jsx'
import { Skeleton } from '../components/Skeleton.jsx'
import { ErrorState } from '../components/Empty.jsx'
import { confidence, uncertainty } from '../confidence.js'
import { nationColors } from '../nations.js'
import { flag } from '../flags.js'
import { fmtMonth, today } from '../dates.js'

const label = (code) => EVENTS.find((e) => e.code === code)?.label || code
const fmt = (n) => Math.round(n).toLocaleString()

function age(dob) {
  if (!dob) return null
  const t = today()
  const a = +t.slice(0, 4) - +dob.slice(0, 4) - (t.slice(5) < dob.slice(5, 10) ? 1 : 0)
  return a > 5 && a < 90 ? a : null
}

// Prize money arrives as text ("$1,234,567" or "1234567"); show it as dollars.
function prize(v) {
  if (!v) return null
  const n = Number(String(v).replace(/[^0-9.]/g, ''))
  return n > 0 ? `$${Math.round(n).toLocaleString()}` : null
}

// Diagonal flag-colour stripes fading in from the right of the hero.
function stripes(cc) {
  const c = nationColors(cc)
  const n = c.length
  const start = 50
  const seg = (100 - start) / n
  return `linear-gradient(100deg, transparent ${start}%, ${c.map((x, i) =>
    `color-mix(in srgb, ${x} 34%, transparent) ${start + i * seg}% ${start + (i + 1) * seg}%`).join(', ')})`
}

function PlayerSkeleton() {
  return (
    <div aria-hidden="true">
      <div className="sk-hero" style={{ height: 180 }} />
      <div className="kpis card" style={{ marginTop: 14 }}>{[0, 1, 2, 3].map((i) => <div key={i} className="kpi"><Skeleton h={44} /></div>)}</div>
      <Skeleton h={260} r={12} style={{ marginTop: 14 }} />
    </div>
  )
}

export default function Player() {
  const { id } = useParams()
  const { data: player, error, loading, reload } = useAsync(() => api.player(id), [id])
  const [event, setEvent] = useState(null)

  const ratings = player?.ratings || []
  // Default to the discipline the player is ranked best in, else the strongest.
  const ranked = ratings.filter((r) => r.rank).sort((a, b) => a.rank - b.rank)
  const activeEvent = event || ranked[0]?.event || ratings[0]?.event
  const history = useAsync(
    () => (activeEvent ? api.playerHistory(id, activeEvent) : Promise.resolve([])),
    [id, activeEvent],
  )

  if (loading) return <PlayerSkeleton />
  if (error) return <ErrorState error={error} onRetry={reload} what="this player" />

  const records = player.records || []
  const wins = records.reduce((a, r) => a + r.wins, 0)
  const losses = records.reduce((a, r) => a + r.losses, 0)
  const total = wins + losses
  const winPct = total ? Math.round((100 * wins) / total) : 0
  const cur = ratings.find((r) => r.event === activeEvent)
  const rec = (ev) => records.find((r) => r.event === ev)
  const years = age(player.dob)
  const hand = player.plays === 'L' ? 'Left' : player.plays === 'R' ? 'Right' : null
  const rankLabel = cur?.rank
    ? (cur.rank === 1 ? `World No. 1 · ${cur.event}` : `No. ${cur.rank} · ${label(cur.event)}`)
    : null

  return (
    <div className="player-page">
      <div className="crumb">
        <Link to={`/rankings${activeEvent && activeEvent !== 'MS' ? `?event=${activeEvent}` : ''}`}>Rankings</Link>
        <span className="sep">/</span><span>{label(activeEvent)}</span>
        <span className="sep">/</span><span>{player.name_display}</span>
      </div>

      <section className="pl-hero arena" style={{ '--stripes': stripes(player.country_code) }}>
        <CourtLines />
        <Avatar player={player} size={92} onDeep />
        <div className="pl-id">
          <h1>{player.name_display}</h1>
          <div className="pl-meta">
            <span>{flag(player.country_code)} <b>{player.country_code}</b></span>
            {years && <span>Age <b>{years}</b></span>}
            {player.height_cm ? <span>Height <b>{player.height_cm} cm</b></span> : null}
            {hand && <span>Plays <b>{hand}-handed</b></span>}
            {player.current_residence
              ? <span>Lives in <b>{player.current_residence}</b></span>
              : player.birth_place ? <span>Born in <b>{player.birth_place}</b></span> : null}
            {prize(player.prize_money) && <span>Prize money <b>{prize(player.prize_money)}</b></span>}
          </div>
          <div className="pl-acts">
            {cur && (
              <Link className="btn primary" to={`/h2h?p1=${player.player_id}&event=${activeEvent}`}>
                <Icon name="swords" size={15} /> Compare head-to-head
              </Link>
            )}
            <a className="btn ghost" href="#matches">Match history</a>
          </div>
        </div>
        {cur && (
          <div className="pl-rating">
            {rankLabel && <span className={`pl-rank ${cur.rank === 1 ? 'gold' : ''}`}>{cur.rank === 1 && '★ '}{rankLabel}</span>}
            <span className="num-display">{fmt(cur.rating)}</span>
            <span className="pl-sk">skill {fmt(cur.mu)} ± {uncertainty(cur.rd)}</span>
          </div>
        )}
      </section>

      <div className="kpis card">
        <div className="kpi"><span className="k">Career</span><span className="v num-display">{wins}–{losses}</span><span className="s">{winPct}% wins across {records.length} discipline{records.length === 1 ? '' : 's'}</span></div>
        {cur?.peak_mu != null && (
          <div className="kpi"><span className="k">Peak · {cur.event}</span><span className="v num-display">{fmt(cur.peak_mu)}</span><span className="s">{fmtMonth(cur.peak_utc)}{cur.peak_mu - cur.mu < 1 ? ' · right now' : ''}</span></div>
        )}
        {cur && (
          <div className="kpi"><span className="k">{cur.event} record</span><span className="v num-display">{rec(cur.event) ? `${rec(cur.event).wins}–${rec(cur.event).losses}` : '—'}</span><span className="s">{cur.matches_played} rated matches</span></div>
        )}
        {cur && (
          <div className="kpi"><span className="k">Certainty</span><span className="v kpi-cert"><Confidence rd={cur.rd} /> {confidence(cur.rd).label}</span><span className="s">accurate to about ±{uncertainty(cur.rd)}</span></div>
        )}
      </div>

      {ratings.length > 1 && (
        <div className="disc-cards" role="tablist" aria-label="Discipline">
          {ratings.map((r) => {
            const rr = rec(r.event)
            return (
              <button key={r.event} role="tab" aria-selected={r.event === activeEvent}
                className={`disc-card card ${r.event === activeEvent ? 'on' : ''}`} onClick={() => setEvent(r.event)}>
                <span className="dc-top"><Ev code={r.event} />{r.rank ? <span className="dc-rank">No. {r.rank}</span> : <Confidence rd={r.rd} />}</span>
                <span className="num-display dc-r">{fmt(r.rating)}</span>
                <span className="dc-s">{rr ? `${rr.wins}–${rr.losses}` : `${r.matches_played} matches`}</span>
              </button>
            )
          })}
        </div>
      )}
      {ratings.length === 0 && <p className="muted">No ratings yet for this player.</p>}

      {activeEvent && (
        <>
          <div className="sec-head"><h2>Rating journey · {label(activeEvent)}</h2></div>
          {history.loading && <Skeleton h={300} r={12} />}
          {history.data && <RatingChart points={history.data} />}

          <div className="sec-head" id="matches"><h2>Matches · {label(activeEvent)}</h2></div>
          <MatchHistory playerId={id} event={activeEvent} />
        </>
      )}

      <StyleCard playerId={id} />
    </div>
  )
}
