import { useState } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { api } from './api.js'
import Avatar from './components/Avatar.jsx'

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
                <Avatar player={p} size="sm" />
                <span className="pmeta">
                  <span className="pname">{p.name_display}</span>{' '}
                  <span className="flag">{p.country_code}</span>
                </span>
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
        <Link to="/" className="brand">
          <span className="brand-mark">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M4 20l7-7" />
              <path d="M11 13l6.5-6.5a2.1 2.1 0 0 0-3-3L8 10" />
              <path d="M8 10l3 3" />
              <circle cx="6" cy="18" r="2" />
            </svg>
          </span>
          <span><b>Badminton</b> <span>Ratings</span></span>
        </Link>
        <nav className="nav">
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/rankings">Rankings</NavLink>
          <NavLink to="/tournaments">Tournaments</NavLink>
          <NavLink to="/insights">Insights</NavLink>
          <NavLink to="/cups">Cups</NavLink>
        </nav>
        <Search />
      </header>
      <main className="content">
        <Outlet />
      </main>
      <footer className="footer">
        Ratings are <strong>Glicko-2-with-pairs</strong> over BWF tournament data.
        Conservative score = mu − 2·rd.
      </footer>
    </div>
  )
}
