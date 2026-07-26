import { useRef, useState } from 'react'
import { api } from '../../api.js'
import MatchesEditor from './MatchesEditor.jsx'

// Find a tournament by name, then edit its metadata (logo, dates, tier, venue,
// prize). Only tournaments that already have matches are searchable.
function TournamentSearch({ onPick }) {
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
      const data = await api.studioTournaments(query)
      if (mine === seq.current) setResults(data.results)
    } catch {
      if (mine === seq.current) setResults([])
    }
  }

  return (
    <div className="pp">
      <input value={q} onChange={onChange} placeholder="Search tournaments by name…" autoFocus />
      {results.length > 0 && (
        <ul className="pp-results">
          {results.map((t) => (
            <li key={t.tournament_id}>
              <button type="button" onClick={() => onPick(t)}>
                <span className="pp-name">{t.name}</span>
                <span className="pp-flag">
                  {t.start_date ? String(t.start_date).slice(0, 4) : '—'} · {t.match_count} matches
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

const FIELDS = [
  { key: 'name', label: 'Name', type: 'text' },
  { key: 'category_name', label: 'Tier / category', type: 'text' },
  { key: 'start_date', label: 'Start date', type: 'date' },
  { key: 'end_date', label: 'End date', type: 'date' },
  { key: 'venue_name', label: 'Venue', type: 'text' },
  { key: 'prize_money', label: 'Prize money', type: 'number' },
  { key: 'logo_url', label: 'Logo URL', type: 'text' },
]

function toForm(t) {
  const f = {}
  for (const { key } of FIELDS) f[key] = t[key] == null ? '' : t[key]
  return f
}

function MetadataForm({ tournament, onSaved }) {
  const [form, setForm] = useState(() => toForm(tournament))
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState(null) // { ok, text }

  function set(key, value) {
    setForm((f) => ({ ...f, [key]: value }))
    setMsg(null)
  }

  async function save() {
    setSaving(true)
    setMsg(null)
    // Empty date/number → null (clears the field); strings pass through.
    const body = {}
    for (const { key, type } of FIELDS) {
      const v = form[key]
      body[key] = v === '' && (type === 'date' || type === 'number') ? null : v
    }
    try {
      const updated = await api.studioTournamentEdit(tournament.tournament_id, body)
      setForm(toForm(updated))
      setMsg({ ok: true, text: 'Saved.' })
      onSaved?.(updated)
    } catch (e) {
      setMsg({ ok: false, text: e.message || 'Save failed' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="studio-form">
      <div className="studio-form-grid">
        {FIELDS.map(({ key, label, type }) => (
          <label className="studio-field" key={key}>
            <span>{label}</span>
            <input
              type={type === 'date' ? 'date' : type === 'number' ? 'number' : 'text'}
              value={form[key] ?? ''}
              onChange={(e) => set(key, e.target.value)}
            />
          </label>
        ))}
      </div>
      {form.logo_url ? (
        <div className="studio-logo-preview">
          <img src={form.logo_url} alt="logo preview"
               onError={(e) => { e.currentTarget.style.display = 'none' }} />
          <span className="muted small">Logo preview</span>
        </div>
      ) : null}
      <div className="studio-form-actions">
        <button className="btn-primary" onClick={save} disabled={saving}>
          {saving ? 'Saving…' : 'Save changes'}
        </button>
        {msg && <span className={msg.ok ? 'studio-ok' : 'studio-error'}>{msg.text}</span>}
      </div>
    </div>
  )
}

// Create a tournament from scratch, then drop straight into its editor.
function NewTournamentForm({ onCreated, onCancel }) {
  const [form, setForm] = useState(() => {
    const f = {}
    for (const { key } of FIELDS) f[key] = ''
    return f
  })
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  async function create() {
    if (!form.name.trim()) { setErr('Name is required.'); return }
    setSaving(true)
    setErr('')
    const body = {}
    for (const { key, type } of FIELDS) {
      const v = form[key]
      body[key] = v === '' && (type === 'date' || type === 'number') ? null : v
    }
    try {
      onCreated(await api.studioTournamentCreate(body))
    } catch (e) {
      setErr(e.message || 'Create failed')
      setSaving(false)
    }
  }

  return (
    <div className="studio-form">
      <div className="studio-form-grid">
        {FIELDS.map(({ key, label, type }) => (
          <label className="studio-field" key={key}>
            <span>{label}{key === 'name' ? ' *' : ''}</span>
            <input
              type={type === 'date' ? 'date' : type === 'number' ? 'number' : 'text'}
              value={form[key]}
              autoFocus={key === 'name'}
              onChange={(e) => { setForm((f) => ({ ...f, [key]: e.target.value })); setErr('') }}
            />
          </label>
        ))}
      </div>
      {err && <div className="studio-error">{err}</div>}
      <div className="studio-form-actions">
        <button className="btn-primary" onClick={create} disabled={saving || !form.name.trim()}>
          {saving ? 'Creating…' : 'Create tournament'}
        </button>
        <button className="btn-ghost" onClick={onCancel} disabled={saving}>Cancel</button>
      </div>
    </div>
  )
}

export default function TournamentsTab() {
  const [picked, setPicked] = useState(null)
  const [creating, setCreating] = useState(false)

  if (!picked) {
    return (
      <div className="studio-section">
        <div className="studio-section-head">
          <p className="muted">Pick a tournament to edit its details and matches.</p>
          {!creating && (
            <button className="btn-ghost" onClick={() => setCreating(true)}>+ New tournament</button>
          )}
        </div>
        {creating ? (
          <NewTournamentForm
            onCreated={(t) => { setCreating(false); setPicked(t) }}
            onCancel={() => setCreating(false)}
          />
        ) : (
          <TournamentSearch onPick={setPicked} />
        )}
      </div>
    )
  }

  return (
    <div className="studio-section">
      <div className="studio-section-head">
        <div>
          <h2>{picked.name}</h2>
          <span className="muted small">
            {picked.category_name || 'No tier'} · id {picked.tournament_id}
          </span>
        </div>
        <button className="btn-ghost" onClick={() => setPicked(null)}>Change tournament</button>
      </div>
      <MetadataForm
        tournament={picked}
        onSaved={(u) => setPicked((p) => ({ ...p, ...u }))}
      />
      <MatchesEditor tournamentId={picked.tournament_id} />
    </div>
  )
}
