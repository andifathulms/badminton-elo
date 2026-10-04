import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, EVENTS } from '../api.js'
import { useAsync } from '../useAsync.js'
import { flag } from '../flags.js'
import Avatar from '../components/Avatar.jsx'
import Icon from '../components/Icon.jsx'
import Confidence from '../components/Confidence.jsx'
import { ScoreChips, WL } from '../components/Chips.jsx'
import { Skeleton } from '../components/Skeleton.jsx'
import { ErrorState } from '../components/Empty.jsx'
import { confidence, uncertainty } from '../confidence.js'
import { fmtDay } from '../dates.js'
import { latestMajor } from '../featured.js'

const DOUBLES = new Set(['MD', 'WD', 'XD'])
const capFor = (event) => (DOUBLES.has(event) ? 2 : 1)
const sideName = (players) => players.map((p) => p.name_display).join(' / ')
const fmt = (n) => Math.round(n).toLocaleString()

// Search box that calls onPick(player) when a result is chosen.
function SearchPicker({ label, onPick }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const box = useRef(null)
  const seq = useRef(0)

  async function onChange(e) {
    const v = e.target.value
    setQ(v)
    if (v.trim().length < 2) { seq.current++; return setResults([]) }
    const mine = ++seq.current
    try {
      const r = (await api.searchPlayers(v.trim())).results
      if (mine === seq.current) setResults(r)
    } catch {
      if (mine === seq.current) setResults([])
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
    <div className="h2h-search" ref={box}>
      <Icon name="search" size={15} />
      <input value={q} onChange={onChange} placeholder={label} aria-label={label} />
      {results.length > 0 && (
        <ul className="search-results">
          {results.map((p) => (
            <li key={p.player_id}>
              <button onClick={() => { onPick(p); setQ(''); setResults([]) }}>
                <Avatar player={p} size="sm" />
                <span className="pmeta">
                  <span className="pname">{p.name_display}</span>
                  <span className="flag">{flag(p.country_code)} {p.country_code}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// One side of the matchup: up to `cap` players as chips, plus a search box.
function SidePanel({ label, players, cap, onAdd, onRemove }) {
  return (
    <div className={`h2h-slot card${players.length ? ' chosen' : ''}`}>
      {players.map((p) => (
        <div className="h2h-chip" key={p.player_id}>
          <Avatar player={p} size={38} />
          <Link to={`/players/${p.player_id}`} className="h2h-slot-meta">
            <span className="pname">{p.name_display}</span>
            <span className="muted small">{flag(p.country_code)} {p.country_code}</span>
          </Link>
          <button className="chip-x" onClick={() => onRemove(p.player_id)} aria-label={`Remove ${p.name_display}`}>
            <Icon name="x" size={13} />
          </button>
        </div>
      ))}
      {players.length < cap && <SearchPicker label={players.length ? 'Add partner…' : label} onPick={onAdd} />}
    </div>
  )
}

function Matchup({ event, side1, side2 }) {
  const ids1 = side1.map((p) => p.player_id)
  const ids2 = side2.map((p) => p.player_id)
  const { data, error, loading, reload } = useAsync(
    () => api.h2h(event, ids1, ids2),
    [event, ids1.join(','), ids2.join(',')],
  )
  if (loading) return <Skeleton h={220} r={14} />
  if (error) return <ErrorState error={error} onRetry={reload} what="this matchup" />

  const rec = data.record
  const r1 = data.side1.rating
  const r2 = data.side2.rating
  const lowConf = r1 && r2 && (confidence(r1.rd).level === 'low' || confidence(r2.rd).level === 'low')
  const p1 = data.win_prob != null ? Math.round(data.win_prob * 100) : null
  const Tape = ({ label, a, b, higher = true, fmtv = (x) => x }) => {
    const better1 = a != null && b != null && (higher ? a > b : a < b)
    const better2 = a != null && b != null && (higher ? b > a : b < a)
    return (
      <div className="tape-row">
        <span className={better1 ? 'better' : ''}>{a != null ? fmtv(a) : '—'}</span>
        <span className="tape-l">{label}</span>
        <span className={better2 ? 'better' : ''}>{b != null ? fmtv(b) : '—'}</span>
      </div>
    )
  }

  return (
    <div className="h2h-result">
      <section className="prob card">
        {p1 == null ? (
          <p className="muted">One side isn’t rated in this discipline yet, so there’s no prediction. The record below still applies.</p>
        ) : (
          <>
            <div className="prob-ends">
              <div className={`pe ${p1 >= 50 ? 'fav' : ''}`}>
                <span className="pair-av">{side1.map((p) => <Avatar key={p.player_id} player={p} size={30} />)}</span>
                <span className="pe-nm">{sideName(side1)}</span>
                <span className="num-display">{p1}%</span>
              </div>
              <div className={`pe r ${p1 < 50 ? 'fav' : ''}`}>
                <span className="pair-av">{side2.map((p) => <Avatar key={p.player_id} player={p} size={30} />)}</span>
                <span className="pe-nm">{sideName(side2)}</span>
                <span className="num-display">{100 - p1}%</span>
              </div>
            </div>
            <div className="pbar" role="img" aria-label={`${p1}% to ${100 - p1}%`}>
              <i className={p1 >= 50 ? 'fav' : ''} style={{ width: `${p1}%` }} /><i className={p1 < 50 ? 'fav' : ''} style={{ width: `${100 - p1}%` }} />
            </div>
            <div className="prob-foot">
              <span>Chance to win the next meeting, from current ratings</span>
              {r1 && r2 && <span>Rating gap {fmt(Math.abs(r1.rating - r2.rating))} points</span>}
            </div>
            {lowConf && (
              <p className="prob-warn"><Icon name="info" size={14} /> One side’s rating is still provisional, so treat this as a rough guide.</p>
            )}
          </>
        )}
      </section>

      <div className="h2h-grid">
        <section className="card t-panel">
          <div className="t-panel-h"><h3>Tale of the tape</h3></div>
          <div className="tape">
            <div className="tape-row head"><span>{sideName(side1)}</span><span /><span>{sideName(side2)}</span></div>
            <Tape label="Rating" a={r1?.rating} b={r2?.rating} fmtv={fmt} />
            <Tape label="Skill" a={r1?.mu} b={r2?.mu} fmtv={fmt} />
            <Tape label="± certainty" a={r1 ? uncertainty(r1.rd) : null} b={r2 ? uncertainty(r2.rd) : null} higher={false} />
            <Tape label="Meetings won" a={rec.p1_wins} b={rec.p2_wins} />
            <div className="tape-row"><span>{r1 && <Confidence rd={r1.rd} showLabel />}</span><span className="tape-l">Certainty</span><span>{r2 && <Confidence rd={r2.rd} showLabel />}</span></div>
          </div>
        </section>
        <section className="card t-panel">
          <div className="t-panel-h"><h3>Every meeting</h3><span className="mono muted">{rec.p1_wins}–{rec.p2_wins}</span></div>
          {rec.meetings === 0 ? (
            <p className="muted">{DOUBLES.has(event) ? 'This exact pairing has never met' : 'These two have never met'} in {event}.</p>
          ) : (
            <div className="meets">
              {data.meetings.map((m) => (
                <Link key={m.match_id} to={`/matches/${m.match_id}`} className="meet">
                  {m.p1_won == null ? <span className="wl l">–</span> : <WL won={m.p1_won} />}
                  <span className="meet-t">
                    <b>{m.round_name ? `${m.round_name} · ` : ''}{m.tournament?.name}</b>
                    <span>{m.match_time_utc ? fmtDay(m.match_time_utc, true) : ''}{m.p1_won != null ? ` · ${m.p1_won ? sideName(side1) : sideName(side2)} won` : ''}</span>
                  </span>
                  {m.score_status !== 'Normal' ? <span className="pill warn tiny">{m.score_status}</span> : <ScoreChips games={m.score} />}
                </Link>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}

export default function H2H() {
  const [params, setParams] = useSearchParams()
  const [side1, setSide1] = useState([])
  const [side2, setSide2] = useState([])
  const [featured, setFeatured] = useState(null)
  const [event, setEvent] = useState(
    EVENTS.some((e) => e.code === params.get('event')) ? params.get('event') : 'MS',
  )
  const cap = capFor(event)

  // Deep link: /h2h?event=E&s1=id,id&s2=id,id (or p1/p2). With nothing chosen,
  // open on the latest major's final in this discipline instead of a blank page.
  useEffect(() => {
    let alive = true
    async function idsToPlayers(raw) {
      const ids = (raw || '').split(',').filter(Boolean)
      const ps = await Promise.all(ids.map((id) => api.player(id).catch(() => null)))
      return ps.filter(Boolean)
    }
    async function init() {
      const s1 = await idsToPlayers(params.get('s1') || params.get('p1'))
      const s2 = await idsToPlayers(params.get('s2') || params.get('p2'))
      if (!alive) return
      if (s1.length || s2.length) { setSide1(s1); setSide2(s2); return }
      try {
        const major = await latestMajor()
        const fin = major?.finals?.find((f) => f.event === event)
        if (!fin) return
        const m = await api.match(fin.match_id)
        if (!alive) return
        const sideOf = (n) => m.lineup.filter((l) => l.side === n).map((l) => l.player)
        const win = m.winner_side || 1
        setSide1(sideOf(win))
        setSide2(sideOf(win === 1 ? 2 : 1))
        setFeatured(`${major.name} final`)
      } catch { /* leave the pickers empty */ }
    }
    init()
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Dropping to singles trims each side back to one player.
  useEffect(() => {
    setSide1((s) => s.slice(0, cap))
    setSide2((s) => s.slice(0, cap))
  }, [cap])

  // Keep the matchup in the URL so it can be shared.
  useEffect(() => {
    const next = { event }
    if (side1.length) next.s1 = side1.map((p) => p.player_id).join(',')
    if (side2.length) next.s2 = side2.map((p) => p.player_id).join(',')
    setParams(next, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [event, side1, side2])

  const addTo = (setter) => (p) => {
    setFeatured(null)
    setter((s) => (s.some((x) => x.player_id === p.player_id) ? s : [...s, p].slice(0, cap)))
  }
  const removeFrom = (setter) => (id) => { setFeatured(null); setter((s) => s.filter((x) => x.player_id !== id)) }
  const swap = () => { setSide1(side2); setSide2(side1) }

  const ready = side1.length === cap && side2.length === cap
  const overlap = side1.some((a) => side2.some((b) => b.player_id === a.player_id))

  return (
    <div className="h2h-page">
      <header className="phead">
        <div className="phead-text">
          <div className="crumb"><span>Head-to-Head</span>{featured && <><span className="sep">/</span><span>Featured: {featured}</span></>}</div>
          <h1>Who wins next time?</h1>
          <p className="phead-sub">Pick two players, or two pairs for doubles. The prediction uses each side’s current rating in the chosen discipline.</p>
        </div>
        <div className="phead-aside">
          <div className="tabs" role="tablist" aria-label="Discipline">
            {EVENTS.map((e) => (
              <button key={e.code} role="tab" aria-selected={event === e.code}
                className={`tab ${event === e.code ? 'active' : ''}`} onClick={() => setEvent(e.code)}>{e.code}</button>
            ))}
          </div>
        </div>
      </header>

      <div className="h2h-picker">
        <SidePanel label={cap > 1 ? 'Search a player for side 1' : 'Search player 1'}
          players={side1} cap={cap} onAdd={addTo(setSide1)} onRemove={removeFrom(setSide1)} />
        <button className="h2h-vs" onClick={swap} title="Swap sides" aria-label="Swap sides">VS</button>
        <SidePanel label={cap > 1 ? 'Search a player for side 2' : 'Search player 2'}
          players={side2} cap={cap} onAdd={addTo(setSide2)} onRemove={removeFrom(setSide2)} />
      </div>

      {overlap ? (
        <p className="muted">A player can’t be on both sides.</p>
      ) : ready ? (
        <Matchup event={event} side1={side1} side2={side2} />
      ) : (
        <p className="muted">{DOUBLES.has(event) ? 'Choose a pair on each side to compare.' : 'Choose two players to compare.'}</p>
      )}
    </div>
  )
}
