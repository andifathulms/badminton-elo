import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { api } from './api.js'
import Avatar from './components/Avatar.jsx'
import RefreshButton from './components/RefreshButton.jsx'

function ThemeToggle() {
  const [theme, setTheme] = useState(
    () => document.documentElement.getAttribute('data-theme') || 'light',
  )
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    try { localStorage.setItem('theme', theme) } catch { /* ignore */ }
  }, [theme])

  const dark = theme === 'dark'
  return (
    <button
      className="theme-toggle"
      onClick={() => setTheme(dark ? 'light' : 'dark')}
      aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
      title={dark ? 'Light mode' : 'Dark mode'}
    >
      {dark ? (
        <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor"
             strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="4.5" />
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor"
             strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
        </svg>
      )}
    </button>
  )
}

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
  const [menuOpen, setMenuOpen] = useState(false)
  const { pathname } = useLocation()
  // Close the mobile menu whenever the route changes.
  useEffect(() => { setMenuOpen(false) }, [pathname])

  return (
    <div className="app">
      <a href="#main" className="skip-link">Skip to content</a>
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
        <nav className={`nav ${menuOpen ? 'open' : ''}`}>
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/rankings">Rankings</NavLink>
          <NavLink to="/tournaments">Tournaments</NavLink>
          <NavLink to="/insights">Insights</NavLink>
          <NavLink to="/h2h">Head-to-Head</NavLink>
          <NavLink to="/cups">Cups</NavLink>
        </nav>
        <Search />
        <RefreshButton />
        <ThemeToggle />
        <button
          className="nav-toggle"
          onClick={() => setMenuOpen((o) => !o)}
          aria-label="Menu"
          aria-expanded={menuOpen}
        >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
               strokeWidth="2.2" strokeLinecap="round">
            {menuOpen
              ? <><path d="M6 6l12 12" /><path d="M18 6L6 18" /></>
              : <><path d="M3 6h18" /><path d="M3 12h18" /><path d="M3 18h18" /></>}
          </svg>
        </button>
      </header>
      <main className="content" id="main" tabIndex={-1}>
        {/* Keyed by route so each page fades/rises in on navigation. */}
        <div className="route-fade" key={pathname}>
          <Outlet />
        </div>
      </main>
      <footer className="footer">
        Ratings are <strong>Glicko-2-with-pairs</strong> over BWF tournament data.
        Conservative score = mu − 2·rd.
      </footer>
    </div>
  )
}
