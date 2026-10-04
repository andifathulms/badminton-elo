import { nationRing } from '../nations.js'

// Player avatar: the BWF photo when present, otherwise initials inside a ring of
// the player's flag colours — meaningful at a glance, never a random gradient.
// size: 'xs' | 'sm' | '' (md) | 'lg' | 'xl', or a number of pixels.
const SIZES = { xs: 22, sm: 28, '': 34, md: 34, lg: 56, xl: 88 }

function initials(name = '') {
  const parts = name.replace(/[.]/g, '').trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return '?'
  const first = parts[0][0]
  const last = parts.length > 1 ? parts[parts.length - 1][0] : ''
  return (first + last).toUpperCase()
}

export default function Avatar({ player, size = '', onDeep = false }) {
  const name = player?.name_display || ''
  const px = typeof size === 'number' ? size : SIZES[size] ?? 34
  const style = { '--s': `${px}px`, '--ring': nationRing(player?.country_code) }
  return (
    <span className={`avatar${onDeep ? ' on-deep' : ''}`} style={style}
          title={name} aria-hidden="true">
      {player?.avatar_url
        ? <img src={player.avatar_url} alt="" loading="lazy" />
        : <i>{initials(name)}</i>}
    </span>
  )
}
