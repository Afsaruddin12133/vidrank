import { useCallback, useEffect, useState } from 'react'
import {
  listSubAdmins, addSubAdmin, updateSubAdmin, deleteSubAdmin,
  fmtInt, fmtClock,
} from '../api.js'

export default function SubAdmins() {
  const [rows, setRows] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [acting, setActing] = useState(null)
  const [editingId, setEditingId] = useState(null)

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [editUsername, setEditUsername] = useState('')
  const [editPassword, setEditPassword] = useState('')
  const [editActive, setEditActive] = useState(true)

  const load = useCallback(async () => {
    setBusy(true)
    setError('')
    try {
      const res = await listSubAdmins()
      setRows(Array.isArray(res) ? res : (res && res.sub_admins) || [])
    } catch (e) {
      setError(e.message || 'Failed to load sub-admins')
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const onCreate = async (e) => {
    e.preventDefault()
    setMsg(''); setError('')
    setActing('new')
    try {
      await addSubAdmin(username.trim(), password)
      setUsername(''); setPassword('')
      setMsg(`Created ${username.trim()}`)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setActing(null)
    }
  }

  const startEdit = (r) => {
    setEditingId(r.id)
    setEditUsername(r.username)
    setEditPassword('')
    setEditActive(!!r.is_active)
  }

  const onSaveEdit = async (id) => {
    setMsg(''); setError('')
    setActing(id)
    const payload = { username: editUsername.trim(), is_active: editActive }
    if (editPassword) payload.password = editPassword
    try {
      await updateSubAdmin(id, payload)
      setEditingId(null)
      setMsg('Saved')
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setActing(null)
    }
  }

  const onDelete = async (r) => {
    if (!window.confirm(`Delete sub-admin "${r.username}"? This cannot be undone.`)) return
    setMsg(''); setError('')
    setActing(r.id)
    try {
      await deleteSubAdmin(r.id)
      setMsg(`Deleted ${r.username}`)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setActing(null)
    }
  }

  return (
    <div className="stack">
      <section className="card">
        <div className="card-label">Sub Admins — {busy ? 'loading…' : `${fmtInt(rows.length)} total`}</div>
        <p className="login-sub" style={{ marginTop: 4 }}>
          Sub-admins can manage the Users table (toggle pro/free, suspend, reset quota)
          but cannot see accounts, pricing, stats, or other super-admin sections.
        </p>

        <form onSubmit={onCreate} style={{ display: 'flex', gap: 10, margin: '14px 0', alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            className="in"
            style={{ maxWidth: 200 }}
            placeholder="Username (3-64 chars)"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={acting === 'new'}
          />
          <input
            className="in"
            style={{ maxWidth: 200 }}
            type="password"
            placeholder="Password (min 8 chars)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={acting === 'new'}
          />
          <button className="btn primary sm" type="submit" disabled={acting === 'new'}>
            {acting === 'new' ? 'Creating…' : 'Add sub-admin'}
          </button>
        </form>

        {error && <div className="error">{error}</div>}
        {msg && <div className="ok">{msg}</div>}

        {rows.length === 0 ? (
          <div className="empty">{busy ? 'Loading…' : 'No sub-admins yet.'}</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Username</th>
                <th>Status</th>
                <th>Created</th>
                <th>Updated</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  {editingId === r.id ? (
                    <>
                      <td>
                        <input
                          className="in"
                          value={editUsername}
                          onChange={(e) => setEditUsername(e.target.value)}
                        />
                      </td>
                      <td>
                        <label style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
                          <input
                            type="checkbox"
                            checked={editActive}
                            onChange={(e) => setEditActive(e.target.checked)}
                          />
                          active
                        </label>
                      </td>
                      <td colSpan={2}>
                        <input
                          className="in"
                          style={{ maxWidth: 200 }}
                          type="password"
                          placeholder="New password (blank = keep)"
                          value={editPassword}
                          onChange={(e) => setEditPassword(e.target.value)}
                        />
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: 6 }}>
                          <button className="btn sm primary" disabled={acting === r.id} onClick={() => onSaveEdit(r.id)}>
                            Save
                          </button>
                          <button className="btn sm ghost" onClick={() => setEditingId(null)}>
                            Cancel
                          </button>
                        </div>
                      </td>
                    </>
                  ) : (
                    <>
                      <td>{r.username}</td>
                      <td>
                        <span className={`status ${r.is_active ? 'status-ok' : 'status-err'}`}>
                          {r.is_active ? 'active' : 'suspended'}
                        </span>
                      </td>
                      <td>{fmtClock(r.created_at)}</td>
                      <td>{fmtClock(r.updated_at)}</td>
                      <td>
                        <div style={{ display: 'flex', gap: 6 }}>
                          <button className="btn sm ghost" disabled={acting === r.id} onClick={() => startEdit(r)}>
                            ✏️ Edit
                          </button>
                          <button
                            className="btn sm ghost"
                            style={{ color: '#dc2626' }}
                            disabled={acting === r.id}
                            onClick={() => onDelete(r)}
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
