import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api.js'

// Data operations, moved out of the public header into the staff-only Studio:
//  - Get latest data: collect the newest season, then re-rate + rebuild analytics.
//  - Rebuild ratings: re-rate the current data (e.g. after manual edits) —
//    no collection. Run this after fixing scores/matches so ratings reflect them.
// Both run as one background job (only one at a time); progress is polled.
export default function DataTab() {
  const [status, setStatus] = useState(null)
  const timer = useRef(null)

  const poll = useCallback(async () => {
    try {
      const s = await api.refreshStatus()
      setStatus(s)
      if (s.running) timer.current = setTimeout(poll, 2500)
    } catch {
      timer.current = setTimeout(poll, 3000)
    }
  }, [])

  useEffect(() => {
    api.refreshStatus().then((s) => {
      setStatus(s)
      if (s.running) poll()
    }).catch(() => setStatus({ allowed: false }))
    return () => clearTimeout(timer.current)
  }, [poll])

  async function run(kind) {
    setStatus((p) => ({ ...p, running: true, phase: 'Starting…', ok: null, message: null,
      steps_done: 0, steps_total: 0 }))
    try {
      const s = kind === 'rebuild' ? await api.studioRebuild() : await api.refreshStart()
      setStatus(s)
      if (s.running !== false) poll()
    } catch (e) {
      setStatus((p) => ({ ...p, running: false, ok: false, message: e.message }))
    }
  }

  if (!status) return <div className="muted">Loading…</div>
  if (status.allowed === false) {
    return <p className="muted">Data operations are disabled on this deployment.</p>
  }

  const running = status.running
  const pct = status.steps_total ? Math.round((status.steps_done / status.steps_total) * 100) : 0

  return (
    <div className="studio-section">
      <div className="data-cards">
        <div className="data-card">
          <h3>Get latest data</h3>
          <p className="muted small">
            Collect the newest season from BWF, then re-rate everything and rebuild
            analytics. Takes a couple of minutes.
          </p>
          <button className="btn-primary" onClick={() => run('full')} disabled={running}>
            Get latest data
          </button>
        </div>
        <div className="data-card">
          <h3>Rebuild ratings</h3>
          <p className="muted small">
            Re-rate the current data and rebuild analytics — no new collection.
            Run this after editing matches, scores, or nationalities.
          </p>
          <button className="btn-primary" onClick={() => run('rebuild')} disabled={running}>
            Rebuild ratings
          </button>
        </div>
      </div>

      {(running || status.ok != null) && (
        <div className="data-progress" role="status" aria-live="polite">
          {running ? (
            <>
              <div className="rt-head"><span className="rt-spinner" /> <b>Working…</b></div>
              <div className="muted small">{status.phase || 'Starting…'}</div>
              <div className="rt-track"><div className="rt-fill" style={{ width: `${pct}%` }} /></div>
              <div className="muted small">
                Step {Math.min((status.steps_done || 0) + 1, status.steps_total || 1)} of{' '}
                {status.steps_total || '…'}
              </div>
            </>
          ) : status.ok ? (
            <>
              <div className="rt-head"><span className="rt-ok">✓</span> <b>Done</b></div>
              <div className="muted small">{status.message}</div>
              <button className="btn-ghost" onClick={() => window.location.reload()}>
                Reload to see it
              </button>
            </>
          ) : (
            <>
              <div className="rt-head"><span className="rt-err">⚠</span> <b>Failed</b></div>
              <div className="muted small">{status.message}</div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
