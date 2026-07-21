import { Link } from 'react-router-dom'
import Avatar from './Avatar.jsx'
import { flag } from '../flags.js'

// A player or a pair, rendered as avatar(s) + name(s), linking to the right
// detail page. `players` is a 1- or 2-element array of brief player objects.
// `rating`, if given, is shown after the country (e.g. rating before a match).
export default function Entity({ players, event, size = 'sm', rating }) {
  const list = (players || []).filter(Boolean)
  if (list.length === 0) return <span className="muted">—</span>
  const pair = list.length > 1
  const to = pair
    ? `/pairs/${event}/${list[0].player_id}/${list[1].player_id}`
    : `/players/${list[0].player_id}`
  const cc = list[0].country_code
  return (
    <Link to={to} className="ent">
      <span className={`ent-av${pair ? ' pair-av' : ''}`}>
        {list.map((p) => <Avatar key={p.player_id} player={p} size={size} />)}
      </span>
      <span className="ent-meta">
        <span className="ent-name">{list.map((p) => p.name_display).join(' / ')}</span>
        <span className="ent-sub">
          <span className="fl">{flag(cc)}</span>{cc}
          {rating != null && (
            <span className="ent-rating" title="Rating before this match">· {rating}</span>
          )}
        </span>
      </span>
    </Link>
  )
}

// Format an oriented games array ([[a,b],…]) as "21-15  21-18".
export const fmtScore = (games) =>
  (games || []).map(([a, b]) => `${a}-${b}`).join('  ')
