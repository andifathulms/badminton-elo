import { useCallback, useEffect, useState } from 'react'
import { api, EVENTS } from '../../api.js'
import { flag } from '../../flags.js'
import PlayerPicker from '../../components/PlayerPicker.jsx'

const ROUNDS = ['', 'R128', 'R64', 'R32', 'R16', 'QF', 'SF', 'Final']
const STATUSES = ['Normal', 'Retired', 'Walkover', 'NoMatch', 'Disqualified', 'Promoted', 'Bye']

const EVENT_LABEL = Object.fromEntries(EVENTS.map((e) => [e.code, e.code]))

function blankForm() {
  return {
    event: 'MS', round_name: '', side1: [], side2: [],
    side1_country: '', side2_country: '', games: [['', '']],
    winner_side: null, score_status: 'Normal', match_time_utc: '', scoring_format: '',
  }
}

function fromMatch(m) {
  return {
    event: m.event || 'MS',
    round_name: m.round_name || '',
    side1: m.side1 || [],
    side2: m.side2 || [],
    side1_country: m.side1_country || '',
    side2_country: m.side2_country || '',
    games: (m.games && m.games.length ? m.games : [['', '']]).map(([a, b]) => [a, b]),
    winner_side: m.winner_side ?? null,
    score_status: m.score_status || 'Normal',
    match_time_utc: m.match_time_utc ? String(m.match_time_utc).slice(0, 10) : '',
    scoring_format: m.scoring_format || '',
  }
}

function sideName(players) {
  if (!players?.length) return '—'
  return players.map((p) => p.name_display).join(' / ')
}

function scoreText(games) {
  return (games || []).map(([a, b]) => `${a}-${b}`).join(', ') || '—'
}

// One editable side: chips of chosen players (removable) + a picker to add more.
function SideEditor({ label, players, onAdd, onRemove, country, onCountry }) {
  return (
    <div className="me-side">
      <div className="me-side-head">
        <span>{label}</span>
        <input className="me-country" value={country} maxLength={8}
               placeholder="NAT" onChange={(e) => onCountry(e.target.value)}
               title="Nation this side represented (optional)" />
      </div>
      <div className="me-chips">
        {players.map((p) => (
          <span className="me-chip" key={p.player_id}>
            {flag(p.country_code)} {p.name_display}
            <button type="button" onClick={() => onRemove(p.player_id)} aria-label="Remove">×</button>
          </span>
        ))}
      </div>
      {players.length < 2 && (
        <PlayerPicker onPick={onAdd} placeholder={`Add to ${label.toLowerCase()}…`} />
      )}
    </div>
  )
}

function MatchForm({ tournamentId, initial, onSaved, onCancel, onDeleted }) {
  const editing = !!initial
  const [f, setF] = useState(() => (initial ? fromMatch(initial) : blankForm()))
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const set = (k, v) => setF((p) => ({ ...p, [k]: v }))

  function addPlayer(side, p) {
    setF((prev) => {
      const key = `side${side}`
      if (prev[key].some((x) => x.player_id === p.player_id)) return prev
      return { ...prev, [key]: [...prev[key], p] }
    })
  }
  function removePlayer(side, pid) {
    const key = `side${side}`
    setF((prev) => ({ ...prev, [key]: prev[key].filter((x) => x.player_id !== pid) }))
  }
  function setGame(i, j, v) {
    setF((prev) => {
      const games = prev.games.map((g) => [...g])
      games[i][j] = v.replace(/[^0-9]/g, '')
      return { ...prev, games }
    })
  }
  const addGame = () => setF((p) => ({ ...p, games: [...p.games, ['', '']] }))
  const removeGame = (i) => setF((p) => ({
    ...p, games: p.games.filter((_, k) => k !== i).length ? p.games.filter((_, k) => k !== i) : [['', '']],
  }))

  async function save() {
    setErr('')
    if (!f.side1.length || !f.side2.length) { setErr('Each side needs at least one player.'); return }
    setBusy(true)
    // Only send games that have both numbers filled (an empty last row is dropped).
    const games = f.games
      .filter(([a, b]) => a !== '' && b !== '')
      .map(([a, b]) => [Number(a), Number(b)])
    const body = {
      event: f.event,
      round_name: f.round_name,
      side1: f.side1.map((p) => p.player_id),
      side2: f.side2.map((p) => p.player_id),
      side1_country: f.side1_country,
      side2_country: f.side2_country,
      games,
      winner_side: f.winner_side,
      score_status: f.score_status,
      match_time_utc: f.match_time_utc || null,
      scoring_format: f.scoring_format,
    }
    try {
      const saved = editing
        ? await api.studioMatchEdit(initial.match_id, body)
        : await api.studioMatchCreate(tournamentId, body)
      onSaved(saved)
    } catch (e) {
      setErr(e.message || 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  async function del() {
    if (!editing) return
    if (!window.confirm('Delete this match? This cannot be undone.')) return
    setBusy(true)
    try {
      await api.studioMatchDelete(initial.match_id)
      onDeleted(initial.match_id)
    } catch (e) {
      setErr(e.message || 'Delete failed')
      setBusy(false)
    }
  }

  return (
    <div className="me-form">
      <div className="me-form-top">
        <label className="studio-field">
          <span>Discipline</span>
          <select value={f.event} onChange={(e) => set('event', e.target.value)}>
            {EVENTS.map((e) => <option key={e.code} value={e.code}>{e.code} · {e.label}</option>)}
          </select>
        </label>
        <label className="studio-field">
          <span>Round</span>
          <select value={f.round_name} onChange={(e) => set('round_name', e.target.value)}>
            {ROUNDS.map((r) => <option key={r} value={r}>{r || '—'}</option>)}
          </select>
        </label>
        <label className="studio-field">
          <span>Date</span>
          <input type="date" value={f.match_time_utc}
                 onChange={(e) => set('match_time_utc', e.target.value)} />
        </label>
      </div>

      <div className="me-sides">
        <SideEditor label="Side 1" players={f.side1}
                    onAdd={(p) => addPlayer(1, p)} onRemove={(id) => removePlayer(1, id)}
                    country={f.side1_country} onCountry={(v) => set('side1_country', v)} />
        <div className="me-vs">vs</div>
        <SideEditor label="Side 2" players={f.side2}
                    onAdd={(p) => addPlayer(2, p)} onRemove={(id) => removePlayer(2, id)}
                    country={f.side2_country} onCountry={(v) => set('side2_country', v)} />
      </div>

      <div className="me-score">
        <span className="me-score-label">Score <em>(side 1 – side 2, in order)</em></span>
        {f.games.map((g, i) => (
          <div className="me-game" key={i}>
            <input inputMode="numeric" value={g[0]} onChange={(e) => setGame(i, 0, e.target.value)} />
            <span>–</span>
            <input inputMode="numeric" value={g[1]} onChange={(e) => setGame(i, 1, e.target.value)} />
            <button type="button" className="me-x" onClick={() => removeGame(i)} aria-label="Remove game">×</button>
          </div>
        ))}
        <button type="button" className="btn-ghost me-addgame" onClick={addGame}>+ Game</button>
      </div>

      <div className="me-form-bottom">
        <div className="studio-field">
          <span>Winner (who advanced)</span>
          <div className="me-winner">
            {[[1, 'Side 1'], [2, 'Side 2'], [null, 'Unknown']].map(([v, lbl]) => (
              <button type="button" key={String(v)}
                      className={f.winner_side === v ? 'active' : ''}
                      onClick={() => set('winner_side', v)}>{lbl}</button>
            ))}
          </div>
        </div>
        <label className="studio-field">
          <span>Status</span>
          <select value={f.score_status} onChange={(e) => set('score_status', e.target.value)}>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <label className="studio-field">
          <span>Scoring format</span>
          <input value={f.scoring_format} placeholder="auto (by date)"
                 onChange={(e) => set('scoring_format', e.target.value)} />
        </label>
      </div>

      {err && <div className="studio-error">{err}</div>}
      <div className="studio-form-actions">
        <button className="btn-primary" onClick={save} disabled={busy}>
          {busy ? 'Saving…' : editing ? 'Save match' : 'Create match'}
        </button>
        <button className="btn-ghost" onClick={onCancel} disabled={busy}>Cancel</button>
        {editing && (
          <button className="btn-danger" onClick={del} disabled={busy} style={{ marginLeft: 'auto' }}>
            Delete
          </button>
        )}
      </div>
    </div>
  )
}

function MatchRow({ m, onEdit }) {
  const w = m.winner_side
  return (
    <div className="me-row">
      <span className="me-round">{m.round_name || '—'}</span>
      <span className={`me-team ${w === 1 ? 'won' : ''}`}>{sideName(m.side1)}</span>
      <span className="me-vs-sm">vs</span>
      <span className={`me-team ${w === 2 ? 'won' : ''}`}>{sideName(m.side2)}</span>
      <span className="me-score-cell">{scoreText(m.games)}</span>
      {m.score_status !== 'Normal' && <span className="me-status">{m.score_status}</span>}
      {m.is_manual && <span className="me-manual" title="Manually added">✎</span>}
      <button className="btn-ghost me-edit" onClick={() => onEdit(m)}>Edit</button>
    </div>
  )
}

export default function MatchesEditor({ tournamentId }) {
  const [matches, setMatches] = useState(null)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(null) // match object being edited
  const [adding, setAdding] = useState(false)

  const load = useCallback(async () => {
    setError('')
    try {
      const data = await api.studioMatches(tournamentId)
      setMatches(data.results)
    } catch (e) {
      setError(e.message || 'Failed to load matches')
    }
  }, [tournamentId])

  useEffect(() => { load() }, [load])

  function afterSave() {
    setEditing(null)
    setAdding(false)
    load()
  }

  // Group by discipline for readability.
  const groups = {}
  for (const m of matches || []) (groups[m.event] ||= []).push(m)

  return (
    <div className="me-wrap">
      <div className="studio-section-head">
        <h2>Matches {matches ? <span className="muted small">· {matches.length}</span> : null}</h2>
        {!adding && !editing && (
          <button className="btn-primary" onClick={() => setAdding(true)}>+ Add match</button>
        )}
      </div>

      {error && <div className="studio-error">{error}</div>}

      {adding && (
        <MatchForm tournamentId={tournamentId} initial={null}
                   onSaved={afterSave} onCancel={() => setAdding(false)} onDeleted={afterSave} />
      )}
      {editing && (
        <MatchForm tournamentId={tournamentId} initial={editing}
                   onSaved={afterSave} onCancel={() => setEditing(null)} onDeleted={afterSave} />
      )}

      {matches === null && !error && <div className="muted">Loading…</div>}
      {matches && matches.length === 0 && !adding && (
        <p className="muted">No matches yet. Add the first one.</p>
      )}

      {!adding && !editing && Object.entries(groups).map(([event, ms]) => (
        <div className="me-group" key={event}>
          <div className="me-group-head">{EVENT_LABEL[event] || event}</div>
          {ms.map((m) => <MatchRow key={m.match_id} m={m} onEdit={setEditing} />)}
        </div>
      ))}
    </div>
  )
}
