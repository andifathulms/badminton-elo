// Player avatar: uses the BWF avatar_url when present, otherwise renders the
// player's initials on a deterministic brand-tinted gradient (stable per name).
const GRADIENTS = [
  ['#6366f1', '#8b5cf6'], ['#0ea5e9', '#6366f1'], ['#f43f5e', '#f97316'],
  ['#10b981', '#06b6d4'], ['#8b5cf6', '#ec4899'], ['#f59e0b', '#ef4444'],
  ['#14b8a6', '#3b82f6'], ['#ec4899', '#8b5cf6'],
]

function hash(str = '') {
  let h = 0
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) | 0
  return Math.abs(h)
}

function initials(name = '') {
  const parts = name.replace(/[.]/g, '').trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return '?'
  const first = parts[0][0]
  const last = parts.length > 1 ? parts[parts.length - 1][0] : ''
  return (first + last).toUpperCase()
}

export default function Avatar({ player, size = '' }) {
  const name = player?.name_display || ''
  const cls = `avatar ${size}`.trim()
  if (player?.avatar_url) {
    return <img className={cls} src={player.avatar_url} alt={name} loading="lazy" />
  }
  const [a, b] = GRADIENTS[hash(name) % GRADIENTS.length]
  return (
    <span className={cls} aria-hidden="true"
          style={{ background: `linear-gradient(135deg, ${a}, ${b})` }}>
      {initials(name)}
    </span>
  )
}
