import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api.js'

// A header button that triggers a background data refresh (collect the latest
// season → re-rate → rebuild analytics) and polls its progress into a toast.
// Hidden entirely when the server reports the refresh is disabled.
export default function RefreshButton() {
  const [status, setStatus] = useState(null)
  const [dismissed, setDismissed] = useState(true)
  const timer = useRef(null)

  const poll = useCallback(async () => {
    try {
      const s = await api.refreshStatus()
      setStatus(s)
      if (s.running) {
        timer.current = setTimeout(poll, 2500)
      }
    } catch {
      /* ignore transient poll errors (the DB may be briefly locked mid-rebuild) */
      timer.current = setTimeout(poll, 3000)
    }
  }, [])

  useEffect(() => {
    // Initial status: learn whether refresh is allowed, and resume a run in
    // progress (e.g. after a page reload while a job is running).
    api.refreshStatus().then((s) => {
      setStatus(s)
      if (s.running) { setDismissed(false); poll() }
    }).catch(() => {})
    return () => clearTimeout(timer.current)
  }, [poll])

  async function start() {
    setDismissed(false)
    try {
      const s = await api.refreshStart()
      setStatus(s)
      if (s.running !== false) poll()
    } catch (e) {
      setStatus((prev) => ({ ...prev, running: false, ok: false, message: String(e.message || e) }))
    }
  }

  if (!status || status.allowed === false) return null

  const running = status.running
  const pct = status.steps_total
    ? Math.round((status.steps_done / status.steps_total) * 100)
    : 0
  const showToast = !dismissed && (running || status.ok != null)

  return (
    <>
      <button
        className="refresh-btn"
        onClick={start}
        disabled={running}
        aria-label="Get the latest data"
        title="Collect the latest tournaments and re-rate"
      >
        <svg className={running ? 'spin' : ''} viewBox="0 0 24 24" width="17" height="17"
             fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"
             strokeLinejoin="round">
          <path d="M21 12a9 9 0 1 1-2.64-6.36" />
          <path d="M21 3v6h-6" />
        </svg>
      </button>

      {showToast && (
        <div className="refresh-toast" role="status" aria-live="polite">
          <button className="refresh-toast-x" onClick={() => setDismissed(true)}
                  aria-label="Dismiss">×</button>
          {running ? (
            <>
              <div className="rt-head">
                <span className="rt-spinner" />
                <b>Getting the latest data…</b>
              </div>
              <div className="rt-phase muted small">{status.phase || 'Starting…'}</div>
              <div className="rt-track"><div className="rt-fill" style={{ width: `${pct}%` }} /></div>
              <div className="muted small">
                Step {Math.min(status.steps_done + 1, status.steps_total || 1)} of{' '}
                {status.steps_total || '…'} · this can take a couple of minutes.
              </div>
            </>
          ) : status.ok ? (
            <>
              <div className="rt-head"><span className="rt-ok">✓</span> <b>Data updated</b></div>
              <div className="muted small">{status.message}</div>
              <button className="pgbtn rt-reload" onClick={() => window.location.reload()}>
                Reload to see it
              </button>
            </>
          ) : (
            <>
              <div className="rt-head"><span className="rt-err">⚠</span> <b>Refresh failed</b></div>
              <div className="muted small">{status.message}</div>
              <button className="pgbtn rt-reload" onClick={start}>Try again</button>
            </>
          )}
        </div>
      )}
    </>
  )
}
