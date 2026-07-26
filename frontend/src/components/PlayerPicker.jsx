import { useRef, useState } from 'react'
import { api } from '../api.js'
import { flag } from '../flags.js'
import Avatar from './Avatar.jsx'

// Search-as-you-type player picker. Calls onPick(player) with the chosen
// {player_id, name_display, country_code, avatar_url}. Used by the Studio
// player editor and the match editor's side pickers.
export default function PlayerPicker({ onPick, placeholder = 'Search players…', autoFocus }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const seq = useRef(0)

  async function onChange(e) {
    const v = e.target.value
    setQ(v)
    const query = v.trim()
    if (query.length < 2) { seq.current++; return setResults([]) }
    const mine = ++seq.current
    try {
      const data = await api.searchPlayers(query)
      if (mine === seq.current) setResults(data.results)
    } catch {
      if (mine === seq.current) setResults([])
    }
  }

  function pick(p) {
    onPick(p)
    setQ('')
    setResults([])
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
