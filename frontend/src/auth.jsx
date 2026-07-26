import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api } from './api.js'

// Session-auth context for the Studio. Loads /auth/me once on mount (which also
// plants the CSRF cookie needed for writes), then exposes login/logout.
const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null) // { authenticated, username, is_staff }
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      setUser(await api.authMe())
    } catch {
      setUser({ authenticated: false, is_staff: false })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const login = useCallback(async (username, password) => {
    const me = await api.authLogin(username, password)
    setUser(me)
    return me
  }, [])

  const logout = useCallback(async () => {
    try { await api.authLogout() } catch { /* ignore */ }
    setUser({ authenticated: false, is_staff: false })
  }, [])

  const isAdmin = !!(user && user.authenticated && user.is_staff)
  return (
    <AuthContext.Provider value={{ user, loading, isAdmin, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
