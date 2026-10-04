import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'
import Avatar from './Avatar.jsx'
import Icon from './Icon.jsx'
import { flag } from '../flags.js'

const RECENT_KEY = 'recent-searches'
const JUMPS = [
  { label: "Men's Singles rankings", to: '/rankings?event=MS', icon: 'list' },
  { label: "Women's Singles rankings", to: '/rankings?event=WS', icon: 'list' },
  { label: 'Tournaments', to: '/tournaments', icon: 'trophy' },
  { label: 'Head-to-Head predictor', to: '/h2h', icon: 'swords' },
  { label: 'Insights', to: '/insights', icon: 'chart' },
]

function readRecent() {
  try { return JSON.parse(localStorage.getItem(RECENT_KEY)) || [] } catch { return [] }
}
function pushRecent(item) {
  try {
    const next = [item, ...readRecent().filter((r) => r.to !== item.to)].slice(0, 5)
    localStorage.setItem(RECENT_KEY, JSON.stringify(next))
  } catch { /* storage unavailable */ }
}

// ⌘K / Ctrl+K / "/" — search players and tournaments from anywhere.
export default function CommandPalette({ open, onClose }) {
  const [q, setQ] = useState('')
  const [players, setPlayers] = useState([])
  const [tours, setTours] = useState([])
  const [sel, setSel] = useState(0)
  const seq = useRef(0)
  const input = useRef(null)
  const navigate = useNavigate()

  useEffect(() => {
    if (!open) return
    setQ(''); setPlayers([]); setTours([]); setSel(0)
    const t = setTimeout(() => input.current?.focus(), 10)
    return () => clearTimeout(t)
  }, [open])

  useEffect(() => {
    const query = q.trim()
    if (query.length < 2) { seq.current++; setPlayers([]); setTours([]); return }
    const mine = ++seq.current
    const t = setTimeout(async () => {
      const [p, tr] = await Promise.allSettled([
        api.searchPlayers(query),
        api.tournaments({ q: query, limit: 6 }),
      ])
      if (mine !== seq.current) return
      setPlayers(p.status === 'fulfilled' ? p.value.results.slice(0, 7) : [])
      setTours(tr.status === 'fulfilled' ? tr.value.results.slice(0, 5) : [])
      setSel(0)
    }, 140)
    return () => clearTimeout(t)
  }, [q])

  const items = useMemo(() => {
    if (q.trim().length < 2) {
      const recent = readRecent().map((r) => ({ ...r, group: 'Recent', icon: r.kind === 't' ? 'trophy' : 'users' }))
      return [...recent, ...JUMPS.map((j) => ({ ...j, group: 'Jump to' }))]
    }
    return [
      ...players.map((p) => ({ group: 'Players', label: p.name_display, to: `/players/${p.player_id}`, player: p, kind: 'p' })),
      ...tours.map((t) => ({ group: 'Tournaments', label: t.name, to: `/tournaments/${t.tournament_id}`, sub: `${(t.category_name || '').replace('HSBC BWF World Tour ', '')} · ${t.start_date || ''}`, kind: 't', icon: 'trophy' })),
    ]
  }, [q, players, tours])

  function go(item) {
    if (!item) return
    if (item.kind) pushRecent({ label: item.label, to: item.to, kind: item.kind, sub: item.sub })
    navigate(item.to)
    onClose()
  }

  function onKey(e) {
    if (e.key === 'Escape') { e.preventDefault(); onClose() }
    else if (e.key === 'ArrowDown') { e.preventDefault(); setSel((s) => Math.min(items.length - 1, s + 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setSel((s) => Math.max(0, s - 1)) }
    else if (e.key === 'Enter') { e.preventDefault(); go(items[sel]) }
  }

  if (!open) return null
  let lastGroup = null
  return (
    <div className="cmdk-backdrop" onMouseDown={onClose}>
      <div className="cmdk" role="dialog" aria-modal="true" aria-label="Search"
           onMouseDown={(e) => e.stopPropagation()} onKeyDown={onKey}>
        <div className="cmdk-input">
          <Icon name="search" size={17} />
          <input ref={input} value={q} onChange={(e) => setQ(e.target.value)}
                 placeholder="Search players or tournaments…" aria-label="Search players or tournaments"
                 aria-activedescendant={items[sel] ? `cmdk-${sel}` : undefined} />
          <kbd>esc</kbd>
        </div>
        <ul className="cmdk-list" role="listbox">
          {items.length === 0 && q.trim().length >= 2 && (
            <li className="cmdk-empty">No players or tournaments match “{q.trim()}”.</li>
          )}
          {items.map((it, i) => {
            const head = it.group !== lastGroup ? (lastGroup = it.group) : null
            return (
              <li key={`${it.group}-${it.to}`} role="presentation">
                {head && <div className="cmdk-group">{head}</div>}
                <button id={`cmdk-${i}`} role="option" aria-selected={i === sel}
                        className={i === sel ? 'on' : ''} onMouseEnter={() => setSel(i)} onClick={() => go(it)}>
                  {it.player
                    ? <Avatar player={it.player} size="sm" />
                    : <span className="cmdk-ic"><Icon name={it.icon || 'arrowRight'} size={15} /></span>}
                  <span className="cmdk-text">
                    <span className="cmdk-label">{it.label}</span>
                    {it.player && <span className="cmdk-sub">{flag(it.player.country_code)} {it.player.country_code}</span>}
                    {!it.player && it.sub && <span className="cmdk-sub">{it.sub}</span>}
                  </span>
                  {i === sel && <Icon name="arrowRight" size={14} className="cmdk-go" />}
                </button>
              </li>
            )
          })}
        </ul>
        <div className="cmdk-foot"><span><kbd>↑</kbd><kbd>↓</kbd> move</span><span><kbd>↵</kbd> open</span><span><kbd>esc</kbd> close</span></div>
      </div>
    </div>
  )
}
