import { useState } from 'react'
import { usePlayerSearch } from '../hooks.js'
import { flag } from '../flags.js'
import Avatar from './Avatar.jsx'

// Search-as-you-type player picker. Calls onPick(player) with the chosen
// {player_id, name_display, country_code, avatar_url}. Used by the Studio
// player editor and the match editor's side pickers.
export default function PlayerPicker({ onPick, placeholder = 'Search players…', autoFocus }) {
  const [q, setQ] = useState('')
  const results = usePlayerSearch(q)

  function onChange(e) {
    setQ(e.target.value)
  }

  function pick(p) {
    onPick(p)
    setQ('')
  }

  return (
    <div className="pp">
      <input value={q} onChange={onChange} placeholder={placeholder} autoFocus={autoFocus} />
      {results.length > 0 && (
        <ul className="pp-results">
          {results.map((p) => (
            <li key={p.player_id}>
              <button type="button" onClick={() => pick(p)}>
                <Avatar player={p} size="sm" />
                <span className="pp-name">{p.name_display}</span>
                <span className="pp-flag">{flag(p.country_code)} {p.country_code}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
