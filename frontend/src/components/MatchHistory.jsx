import { Link } from 'react-router-dom'
import { api } from '../api.js'
import { useAsync } from '../useAsync.js'
import Pager from './Pager.jsx'
import Avatar from './Avatar.jsx'
import { Delta, ScoreChips, WL } from './Chips.jsx'
import { SkeletonList } from './Skeleton.jsx'
import { EmptyState, ErrorState } from './Empty.jsx'
import { flag } from '../flags.js'
import { fmtDay } from '../dates.js'
import { usePageFor } from '../hooks.js'

const names = (players) => players.map((p) => p.name_display).join(' / ') || '—'
const PAGE = 20

// A player's matches as a timeline: result, round · event, opponent, games,
// rating change. Each row opens the match.
export default function MatchHistory({ playerId, event }) {
  const [page, setPage] = usePageFor([playerId, event])
  const { data, error, loading, reload } = useAsync(
    () => api.playerMatches(playerId, { event, limit: PAGE, offset: page * PAGE }),
    [playerId, event, page],
  )

  if (loading) return <SkeletonList rows={8} />
  if (error) return <ErrorState error={error} onRetry={reload} what="matches" />
  if (!data.results.length) return (
    <EmptyState icon="users" title="No matches" hint="No matches recorded for this discipline yet." />
  )

  return (
    <>
      <div className="mh card">
        {data.results.map((m) => (
          <Link key={m.match_id} to={`/matches/${m.match_id}`} className="mh-row">
            <WL won={m.won} />
            <span className="mh-ev">
              <b>{m.round_name ? `${m.round_name} · ` : ''}{m.tournament?.name}</b>
              <span>{m.match_time_utc ? fmtDay(m.match_time_utc, true) : m.tournament?.start_date ? fmtDay(m.tournament.start_date, true) : ''}
                {m.partners.length > 0 && <> · with {names(m.partners)}</>}</span>
            </span>
            <span className="mh-opp">
              <span className="pair-av">{m.opponents.map((p) => <Avatar key={p.player_id} player={p} size="sm" />)}</span>
              <span className="mh-on">
                <span className="nm">{names(m.opponents)}</span>
                <span className="cc">{flag(m.opponents[0]?.country_code)} {m.opponents[0]?.country_code}</span>
              </span>
            </span>
            <span className="mh-sc">
              {m.score_status !== 'Normal' && m.score_status
                ? <span className="pill warn tiny">{m.score_status}</span>
                : <ScoreChips games={m.score} />}
            </span>
            <span className="mh-d">{m.elo ? <Delta value={m.elo.delta} /> : <span className="muted">—</span>}</span>
          </Link>
        ))}
      </div>
      <Pager page={page} setPage={setPage} count={data.count} pageSize={PAGE} unit="matches" />
    </>
  )
}
