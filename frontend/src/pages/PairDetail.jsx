import { Link, useParams } from 'react-router-dom'
import { api } from '../api.js'
import { useAsync } from '../useAsync.js'
import Pager from '../components/Pager.jsx'
import Avatar from '../components/Avatar.jsx'
import StyleCard from '../components/StyleCard.jsx'
import { ErrorState } from '../components/Empty.jsx'
import { flag } from '../flags.js'
import Icon from '../components/Icon.jsx'
import CourtLines from '../components/CourtLines.jsx'
import { Ev, ScoreChips, WL } from '../components/Chips.jsx'
import { fmtDay } from '../dates.js'
import { usePageFor } from '../hooks.js'

const names = (players) => players.map((p) => p.name_display).join(' / ') || '—'
const PAGE = 20

export default function PairDetail() {
  const { event, p1, p2 } = useParams()
  const [page, setPage] = usePageFor([event, p1, p2])
  const { data, error, loading, reload } = useAsync(
    () => api.pairDetail(event, p1, p2),
    [event, p1, p2],
  )

  if (loading) return <div className="sk-hero" style={{ height: 170 }} />
  if (error) return <ErrorState error={error} onRetry={reload} what="this pair" />

  const pair = data.pair
  const winPct = data.matches_together ? Math.round((100 * data.wins) / data.matches_together) : 0
  const both = [data.player1, data.player2]

  return (
    <div className="player-page">
      <div className="crumb">
        <Link to={`/rankings?event=${event}&view=pairs`}>Rankings</Link><span className="sep">/</span>
        <span>{event} pairs</span><span className="sep">/</span><span>{names(both)}</span>
      </div>
      <section className="pl-hero arena pair-hero">
        <CourtLines />
        <span className="pair-av">{both.map((p) => <Avatar key={p.player_id} player={p} size={76} onDeep />)}</span>
        <div className="pl-id">
          <h1>
            <Link to={`/players/${data.player1.player_id}`}>{data.player1.name_display}</Link>
            <span className="amp"> / </span>
            <Link to={`/players/${data.player2.player_id}`}>{data.player2.name_display}</Link>
          </h1>
          <div className="pl-meta">
            <span><Ev code={event} /></span>
            {both.map((p) => <span key={p.player_id}>{flag(p.country_code)} <b>{p.country_code}</b></span>)}
            <span>Together <b>{data.matches_together} matches</b></span>
          </div>
          <div className="pl-acts">
            <Link className="btn primary" to={`/h2h?event=${event}&s1=${data.player1.player_id},${data.player2.player_id}`}>
              <Icon name="swords" size={15} /> Compare head-to-head
            </Link>
          </div>
        </div>
        {pair && (
          <div className="pl-rating">
            <span className="pl-rank">Pair rating · {event}</span>
            <span className="num-display">{Math.round(pair.rating).toLocaleString()}</span>
            {pair.peak_rating != null && <span className="pl-sk">peak {Math.round(pair.peak_rating).toLocaleString()}</span>}
          </div>
        )}
      </section>

      <div className="kpis card">
        <div className="kpi"><span className="k">Record together</span><span className="v num-display">{data.wins}–{data.losses}</span><span className="s">{winPct}% wins</span></div>
        <div className="kpi"><span className="k">Matches</span><span className="v num-display">{data.matches_together}</span><span className="s">as a pair in {event}</span></div>
        {pair?.peak_rating != null && <div className="kpi"><span className="k">Peak</span><span className="v num-display">{Math.round(pair.peak_rating).toLocaleString()}</span><span className="s">combined rating</span></div>}
        {pair && <div className="kpi"><span className="k">Now</span><span className="v num-display">{Math.round(pair.rating).toLocaleString()}</span><span className="s">mean of the two players</span></div>}
      </div>

      <div className="sec-head"><h2>Matches together</h2></div>
      {data.matches.length === 0 ? (
        <p className="muted">No matches found.</p>
      ) : (
        <>
          <div className="mh card">
            {data.matches.slice(page * PAGE, page * PAGE + PAGE).map((m) => {
              const ourSide = m.side1.some((p) => String(p.player_id) === String(data.player1.player_id)) ? 1 : 2
              const won = m.winner_side === ourSide
              const opp = ourSide === 1 ? m.side2 : m.side1
              // Orient the scoreline to the pair (first number is "us").
              const score = ourSide === 2 ? m.score.map(([a, b]) => [b, a]) : m.score
              return (
                <Link key={m.match_id} to={`/matches/${m.match_id}`} className="mh-row">
                  <WL won={won} />
                  <span className="mh-ev">
                    <b>{[m.round_name, m.tournament?.name].filter(Boolean).join(' · ') || 'Match'}</b>
                    <span>{m.match_time_utc ? fmtDay(m.match_time_utc, true) : ''}</span>
                  </span>
                  <span className="mh-opp">
                    <span className="pair-av">{opp.map((p) => <Avatar key={p.player_id} player={p} size="sm" />)}</span>
                    <span className="mh-on"><span className="nm">{names(opp)}</span><span className="cc">{flag(opp[0]?.country_code)} {opp[0]?.country_code}</span></span>
                  </span>
                  <span className="mh-sc"><ScoreChips games={score} /></span>
                  <span />
                </Link>
              )
            })}
          </div>
          <Pager page={page} setPage={setPage} count={data.matches.length} pageSize={PAGE} unit="matches" />
        </>
      )}

      <StyleCard playerId={data.player1.player_id} partner={data.player2.player_id} title="This pair’s style" />
    </div>
  )
}
