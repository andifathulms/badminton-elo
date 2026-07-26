import { useState } from 'react'
import { useAuth } from '../auth.jsx'
import TournamentsTab from './studio/TournamentsTab.jsx'
import PlayersTab from './studio/PlayersTab.jsx'

// The in-app admin ("Studio"): a staff-gated surface for manually curating data
// that the scrapers can't fully fill — old-tournament metadata, missing matches,
// wrong scores, blank nationalities. Everything here writes through /api/studio.

function LoginForm() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function onSubmit(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      await login(username.trim(), password)
    } catch (err) {
      setError(err.message || 'Login failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="studio-login">
      <form className="studio-login-card" onSubmit={onSubmit}>
        <h1>Studio</h1>
        <p className="muted">Sign in to curate tournament data.</p>
        <label>
          <span>Username</span>
          <input value={username} onChange={(e) => setUsername(e.target.value)}
                 autoComplete="username" autoFocus />
        </label>
        <label>
          <span>Password</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                 autoComplete="current-password" />
        </label>
        {error && <div className="studio-error" role="alert">{error}</div>}
        <button className="btn-primary" disabled={busy || !username || !password}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}

const TABS = [
  { key: 'tournaments', label: 'Tournaments' },
  { key: 'players', label: 'Players' },
  { key: 'data', label: 'Data' },
]

export default function Studio() {
  const { user, loading, isAdmin, logout } = useAuth()
  const [tab, setTab] = useState('tournaments')

  if (loading) return <div className="studio-wrap"><div className="muted">Loading…</div></div>
  if (!isAdmin) return <LoginForm />

  return (
    <div className="studio-wrap">
      <div className="studio-bar">
        <div className="studio-bar-title">
          <h1>Studio</h1>
          <span className="studio-badge">curator</span>
        </div>
        <div className="studio-bar-right">
          <span className="muted small">Signed in as <b>{user.username}</b></span>
          <button className="btn-ghost" onClick={logout}>Sign out</button>
        </div>
      </div>

      <div className="studio-tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            className={tab === t.key ? 'active' : ''}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="studio-panel">
        {tab === 'tournaments' && <TournamentsTab />}
        {tab === 'players' && <PlayersTab />}
        {tab === 'data' && <p className="muted">Data tools — coming up.</p>}
      </div>
    </div>
  )
}
