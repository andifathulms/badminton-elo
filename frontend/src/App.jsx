import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import CommandPalette from './components/CommandPalette.jsx'
import Icon from './components/Icon.jsx'

function ThemeToggle() {
  const [theme, setTheme] = useState(
    () => document.documentElement.getAttribute('data-theme') || 'light',
  )
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    try { localStorage.setItem('theme', theme) } catch { /* ignore */ }
    const meta = document.querySelector('meta[name="theme-color"]')
    if (meta) meta.setAttribute('content', theme === 'dark' ? '#0A110E' : '#F3F5F2')
  }, [theme])

  const dark = theme === 'dark'
  return (
    <button
      className="icon-btn"
      onClick={() => setTheme(dark ? 'light' : 'dark')}
      aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
      title={dark ? 'Light mode' : 'Dark mode'}
    >
      <Icon name={dark ? 'sun' : 'moon'} size={16} />
    </button>
  )
}

// Header search trigger: a pill with the ⌘K hint (an icon on phones). Opens the
// command palette; ⌘K / Ctrl+K / "/" open it from anywhere.
function SearchTrigger() {
  const [open, setOpen] = useState(false)
  useEffect(() => {
    function onKey(e) {
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable
      if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !typing)) {
        e.preventDefault()
        setOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  const mac = typeof navigator !== 'undefined' && /Mac|iP(hone|ad)/.test(navigator.platform)
  return (
    <>
      <button className="search-trigger" onClick={() => setOpen(true)} aria-label="Search players and tournaments">
        <Icon name="search" size={15} />
        <span className="st-text">Search players, events</span>
        <kbd>{mac ? '⌘K' : 'Ctrl K'}</kbd>
      </button>
      <CommandPalette open={open} onClose={() => setOpen(false)} />
    </>
  )
}

const NAV = [
  { to: '/', label: 'Home', end: true },
  { to: '/rankings', label: 'Rankings' },
  { to: '/tournaments', label: 'Tournaments' },
  { to: '/insights', label: 'Insights' },
  { to: '/h2h', label: 'Head-to-Head' },
  { to: '/cups', label: 'Cups' },
]

// Phone navigation: four primary tabs within thumb reach + a "More" sheet.
function TabBar() {
  const [more, setMore] = useState(false)
  const { pathname } = useLocation()
  useEffect(() => { setMore(false) }, [pathname])
  const moreActive = ['/insights', '/cups', '/studio'].some((p) => pathname.startsWith(p))
  return (
    <>
      <div className={`more-sheet ${more ? 'open' : ''}`} role="menu">
        <NavLink to="/insights"><Icon name="chart" />Insights</NavLink>
        <NavLink to="/cups"><Icon name="flag" />Team cups</NavLink>
        <NavLink to="/studio"><Icon name="gear" />Studio</NavLink>
      </div>
      <nav className="tabbar" aria-label="Primary">
        <NavLink to="/" end><Icon name="home" size={20} />Home</NavLink>
        <NavLink to="/rankings"><Icon name="list" size={20} />Rankings</NavLink>
        <NavLink to="/tournaments"><Icon name="trophy" size={20} />Events</NavLink>
        <NavLink to="/h2h"><Icon name="swords" size={20} />H2H</NavLink>
        <button className={more || moreActive ? 'active' : ''} aria-expanded={more}
                onClick={() => setMore((m) => !m)}>
          <Icon name="more" size={20} />More
        </button>
      </nav>
    </>
  )
}

export default function App() {
  const { pathname } = useLocation()
  useEffect(() => { window.scrollTo(0, 0) }, [pathname])

  return (
    <div className="app">
      <a href="#main" className="skip-link">Skip to content</a>
      <header className="topbar">
        <Link to="/" className="brand" aria-label="Badminton Ratings home">
          <span className="brand-mark"><Icon name="logo" /></span>
          <span>Badminton <b>Ratings</b></span>
        </Link>
        <nav className="nav" aria-label="Primary">
          {NAV.map((n) => <NavLink key={n.to} to={n.to} end={n.end}>{n.label}</NavLink>)}
        </nav>
        <div className="topbar-tools">
          <SearchTrigger />
          <NavLink to="/studio" className="icon-btn studio-link" aria-label="Studio (admin)" title="Studio">
            <Icon name="gear" size={16} />
          </NavLink>
          <ThemeToggle />
        </div>
      </header>
      <main className="content" id="main" tabIndex={-1}>
        {/* Keyed by route so each page fades/rises in on navigation. */}
        <div className="route-fade" key={pathname}>
          <Outlet />
        </div>
      </main>
      <footer className="footer">
        <span>Ratings use <strong>Glicko-2 with paired doubles strength</strong>, built from BWF tournament results.</span>
        <span>Rating = skill − 2 × uncertainty</span>
      </footer>
      <TabBar />
    </div>
  )
}
