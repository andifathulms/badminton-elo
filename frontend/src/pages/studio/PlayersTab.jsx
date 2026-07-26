import { useEffect, useState } from 'react'
import { api } from '../../api.js'
import { flag } from '../../flags.js'
import Avatar from '../../components/Avatar.jsx'
import PlayerPicker from '../../components/PlayerPicker.jsx'

const GENDERS = [
  { value: '', label: '—' },
  { value: 'M', label: 'Male' },
  { value: 'F', label: 'Female' },
]

// Edit an existing player's nationality/name/gender, or create a manual player
// (for matches whose players BWF never indexed).
function EditForm({ player, onDone }) {
  const [name, setName] = useState(player.name_display || '')
  const [country, setCountry] = useState(player.country_code || '')
  const [gender, setGender] = useState(player.gender || '')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState(null)

  // Reset when a different player is picked. The search result is a "brief"
  // that omits gender, so fetch the full record to pre-fill it — otherwise a
  // save would blank an existing gender.
  useEffect(() => {
    setName(player.name_display || '')
    setCountry(player.country_code || '')
    setGender(player.gender || '')
    setMsg(null)
    let alive = true
    api.player(player.player_id)
      .then((full) => { if (alive) setGender(full.gender || '') })
      .catch(() => {})
    return () => { alive = false }
  }, [player])

  async function save() {
    setSaving(true)
    setMsg(null)
    try {
      const updated = await api.studioPlayerEdit(player.player_id, {
        name_display: name.trim(),
        country_code: country.trim(),
        gender,
      })
      setMsg({ ok: true, text: 'Saved.' })
      onDone?.(updated)
    } catch (e) {
      setMsg({ ok: false, text: e.message || 'Save failed' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="studio-form">
      <div className="studio-player-head">
        <Avatar player={player} />
        <div>
          <b>{player.name_display}</b>
          <div className="muted small">id {player.player_id}</div>
        </div>
      </div>
      <div className="studio-form-grid">
        <label className="studio-field">
          <span>Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="studio-field">
          <span>Nationality (IOC code, e.g. INA)</span>
          <input value={country} onChange={(e) => setCountry(e.target.value)}
                 maxLength={8} />
        </label>
        <label className="studio-field">
          <span>Gender</span>
          <select value={gender} onChange={(e) => setGender(e.target.value)}>
            {GENDERS.map((g) => <option key={g.value} value={g.value}>{g.label}</option>)}
          </select>
        </label>
        <div className="studio-field">
          <span>Flag</span>
          <div className="studio-flag-box">{flag(country) || '—'} {country.toUpperCase()}</div>
        </div>
      </div>
      <div className="studio-form-actions">
        <button className="btn-primary" onClick={save} disabled={saving || !name.trim()}>
          {saving ? 'Saving…' : 'Save changes'}
        </button>
        {msg && <span className={msg.ok ? 'studio-ok' : 'studio-error'}>{msg.text}</span>}
      </div>
    </div>
  )
}

function CreateForm({ onCreated, onCancel }) {
  const [name, setName] = useState('')
  const [country, setCountry] = useState('')
  const [gender, setGender] = useState('')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState(null)

  async function create() {
    setSaving(true)
    setMsg(null)
    try {
      const p = await api.studioPlayerCreate({
        name_display: name.trim(),
        country_code: country.trim(),
        gender,
      })
      onCreated?.(p)
    } catch (e) {
      setMsg({ ok: false, text: e.message || 'Create failed' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="studio-form">
      <div className="studio-form-grid">
        <label className="studio-field">
          <span>Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        </label>
        <label className="studio-field">
          <span>Nationality (IOC code)</span>
          <input value={country} onChange={(e) => setCountry(e.target.value)} maxLength={8} />
        </label>
        <label className="studio-field">
          <span>Gender</span>
          <select value={gender} onChange={(e) => setGender(e.target.value)}>
            {GENDERS.map((g) => <option key={g.value} value={g.value}>{g.label}</option>)}
          </select>
        </label>
      </div>
      <div className="studio-form-actions">
        <button className="btn-primary" onClick={create} disabled={saving || !name.trim()}>
          {saving ? 'Creating…' : 'Create player'}
        </button>
        <button className="btn-ghost" onClick={onCancel}>Cancel</button>
        {msg && <span className="studio-error">{msg.text}</span>}
      </div>
    </div>
  )
}

export default function PlayersTab() {
  const [player, setPlayer] = useState(null)
  const [creating, setCreating] = useState(false)

  return (
    <div className="studio-section">
      <div className="studio-section-head">
        <p className="muted">Search a player to fix their nationality, or add a new one.</p>
        {!creating && (
          <button className="btn-ghost" onClick={() => { setCreating(true); setPlayer(null) }}>
            + New player
          </button>
        )}
      </div>

      {creating ? (
        <CreateForm
          onCreated={(p) => { setCreating(false); setPlayer(p) }}
          onCancel={() => setCreating(false)}
        />
      ) : (
        <>
          <PlayerPicker onPick={setPlayer} />
          {player && <EditForm player={player} onDone={setPlayer} />}
        </>
      )}
    </div>
  )
}
