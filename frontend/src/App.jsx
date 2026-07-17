import { useState } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { api } from './api.js'

function Search() {
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const navigate = useNavigate()

  async function onChange(e) {
    const v = e.target.value
    setQ(v)
    if (v.trim().length < 2) return setResults([])
    try {
      const data = await api.searchPlayers(v.trim())
      setResults(data.results)
    } catch {
      setResults([])
    }
  }

  return (
    <div className="search">
      <input
        value={q}
        onChange={onChange}
        placeholder="Search players…"
        aria-label="Search players"
      />
      {results.length > 0 && (
        <ul className="search-results">
          {results.map((p) => (
            <li key={p.player_id}>
              <button
                onClick={() => {
                  navigate(`/players/${p.player_id}`)
                  setQ('')
                  setResults([])
                }}
              >
                {p.name_display}{' '}
                <span className="muted small">{p.country_code}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">🏸 Badminton Ratings</Link>
        <nav className="nav">
          <NavLink to="/" end>Rankings</NavLink>
          <NavLink to="/tournaments">Tournaments</NavLink>
        </nav>
        <Search />
      </header>
      <main className="content">
        <Outlet />
      </main>
      <footer className="footer">
        Ratings are Glicko-2-with-pairs over BWF tournament data. Conservative
        score = mu − 2·rd.
      </footer>
    </div>
  )
}
