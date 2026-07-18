import { useEffect, useRef, useState } from 'react'

// A small, accessible custom dropdown that matches the app's control styling —
// replaces the browser-default <select>, which renders inconsistently (and looks
// dated) across platforms. Options: [{ value, label }].
export default function Select({ value, onChange, options, label, ariaLabel }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const current = options.find((o) => String(o.value) === String(value))

  useEffect(() => {
    if (!open) return
    const onDoc = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    const onKey = (e) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div className="sel" ref={ref}>
      {label && <span className="sel-label">{label}</span>}
      <button
        type="button"
        className={`sel-btn ${open ? 'open' : ''}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel || label}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="sel-value">{current ? current.label : '—'}</span>
        <svg className="sel-caret" viewBox="0 0 24 24" width="14" height="14"
             fill="none" stroke="currentColor" strokeWidth="2.4"
             strokeLinecap="round" strokeLinejoin="round">
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      {open && (
        <ul className="sel-menu" role="listbox">
          {options.map((o) => (
            <li key={String(o.value)} role="option"
                aria-selected={String(o.value) === String(value)}>
              <button
                type="button"
                className={`sel-opt ${String(o.value) === String(value) ? 'active' : ''}`}
                onClick={() => {
                  onChange(o.value)
                  setOpen(false)
                }}
              >
                {o.label}
                {String(o.value) === String(value) && (
                  <svg viewBox="0 0 24 24" width="15" height="15" fill="none"
                       stroke="currentColor" strokeWidth="3" strokeLinecap="round"
                       strokeLinejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
