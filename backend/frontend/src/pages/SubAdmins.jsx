import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  listSubAdmins, addSubAdmin, updateSubAdmin, deleteSubAdmin,
  fmtInt, fmtClock,
} from '../api.js'

function PaginationControls({ page, totalPages, totalCount, startIndex, endIndex, onPageChange }) {
  if (totalCount === 0) return null

  const pagesToShow = []
  const maxButtons = 5
  let startP = Math.max(1, page - Math.floor(maxButtons / 2))
  let endP = Math.min(totalPages, startP + maxButtons - 1)
  if (endP - startP + 1 < maxButtons) {
    startP = Math.max(1, endP - maxButtons + 1)
  }
  for (let p = startP; p <= endP; p++) {
    pagesToShow.push(p)
  }

  return (
    <div className="pagination-bar">
      <div className="pagination-info">
        Showing <span className="mono">{startIndex + 1}</span>–<span className="mono">{endIndex}</span> of <span className="mono">{fmtInt(totalCount)}</span> activity logs
      </div>
      
      {totalPages > 1 && (
        <div className="pagination-buttons">
          <button className="btn sm ghost" disabled={page <= 1} onClick={() => onPageChange(1)} title="First page">«</button>
          <button className="btn sm ghost" disabled={page <= 1} onClick={() => onPageChange(page - 1)} title="Previous page">Prev</button>
          
          {startP > 1 && <span className="pagination-ellipsis">…</span>}
          {pagesToShow.map((p) => (
            <button
              key={p}
              className={`btn sm ${p === page ? 'primary' : 'ghost'}`}
              onClick={() => onPageChange(p)}
              style={{ minWidth: 28, padding: '4px 8px' }}
            >
              {p}
            </button>
          ))}
          {endP < totalPages && <span className="pagination-ellipsis">…</span>}
          
          <button className="btn sm ghost" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)} title="Next page">Next</button>
          <button className="btn sm ghost" disabled={page >= totalPages} onClick={() => onPageChange(totalPages)} title="Last page">»</button>
        </div>
      )}
    </div>
  )
}

function formatDetails(detailsJson, action) {
  if (action === 'reset_quota') return 'Reset daily usage quota to 0'
  if (!detailsJson) return '—'
  try {
    const obj = typeof detailsJson === 'string' ? JSON.parse(detailsJson) : detailsJson
    if (!obj || typeof obj !== 'object') return String(detailsJson)
    const parts = []
    if (obj.tier) {
      const fromTier = obj.tier.from || 'free'
      const toTier = obj.tier.to || 'free'
      parts.push(`Changed plan: ${fromTier.toUpperCase()} ➔ ${toTier.toUpperCase()}`)
    }
    if (obj.is_active != null) {
      const fromSt = obj.is_active.from ? 'active' : 'suspended'
      const toSt = obj.is_active.to ? 'active' : 'suspended'
      parts.push(`Status: ${fromSt} ➔ ${toSt}`)
    }
    if (obj.usage_count != null) {
      parts.push(`Set today usage: ${obj.usage_count}`)
    }
    if (parts.length > 0) return parts.join(' | ')
    return Object.entries(obj).map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join(', ')
  } catch {
    return String(detailsJson)
  }
}

const SAMPLE_LOGS = [
  {
    id: 'act-sample-1',
    sub_admin_username: 'Alamin',
    action: 'set_user',
    target_uid: 'fahad-uid-101',
    target_email: 'fahad@gmail.com',
    details: JSON.stringify({ tier: { from: 'free', to: 'pro' } }),
    created_at: Math.floor(Date.now() / 1000) - 1800,
  },
  {
    id: 'act-sample-2',
    sub_admin_username: 'Alamin',
    action: 'reset_quota',
    target_uid: 'user-sample-202',
    target_email: 'user2@example.com',
    details: null,
    created_at: Math.floor(Date.now() / 1000) - 7200,
  }
]

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

  // Sub Admin Activity state
  const [activityQ, setActivityQ] = useState('')
  const [debouncedActivityQ, setDebouncedActivityQ] = useState('')
  const [subAdminFilter, setSubAdminFilter] = useState('all')
  const [activityPage, setActivityPage] = useState(1)
  const [activityPageSize, setActivityPageSize] = useState(10)
  const [activityLogs, setActivityLogs] = useState([])

  // Debounce activity search
  useEffect(() => {
    const id = setTimeout(() => setDebouncedActivityQ(activityQ), 300)
    return () => clearTimeout(id)
  }, [activityQ])

  // Reset page when filters change
  useEffect(() => {
    setActivityPage(1)
  }, [debouncedActivityQ, subAdminFilter, activityPageSize])

  const loadSubAdmins = useCallback(async () => {
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

  const loadActivity = useCallback(() => {
    const raw = localStorage.getItem('vidrank_sub_activity_logs')
    let logs = []
    if (raw) {
      try {
        logs = JSON.parse(raw)
      } catch {
        logs = []
      }
    }
    if (!logs || logs.length === 0) {
      logs = SAMPLE_LOGS
      localStorage.setItem('vidrank_sub_activity_logs', JSON.stringify(SAMPLE_LOGS))
    }
    setActivityLogs(logs)
  }, [])

  useEffect(() => { loadSubAdmins() }, [loadSubAdmins])
  useEffect(() => { loadActivity() }, [loadActivity])

  const onCreate = async (e) => {
    e.preventDefault()
    setMsg(''); setError('')
    setActing('new')
    try {
      await addSubAdmin(username.trim(), password)
      setUsername(''); setPassword('')
      setMsg(`Created ${username.trim()}`)
      await loadSubAdmins()
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
      await loadSubAdmins()
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
      await loadSubAdmins()
    } catch (err) {
      setError(err.message)
    } finally {
      setActing(null)
    }
  }

  // Calculate filtered and paginated activity logs
  const { pagedActivity, totalActivityCount, totalActivityPages, curtActivityPage, activityStartIdx, activityEndIdx } = useMemo(() => {
    const filtered = activityLogs.filter((item) => {
      const ql = debouncedActivityQ.trim().toLowerCase()
      const formattedDet = formatDetails(item.details, item.action).toLowerCase()
      const matchesQ = !ql ||
        (item.sub_admin_username || '').toLowerCase().includes(ql) ||
        (item.action || '').toLowerCase().includes(ql) ||
        (item.target_uid || '').toLowerCase().includes(ql) ||
        (item.target_email || '').toLowerCase().includes(ql) ||
        formattedDet.includes(ql)
      const matchesSub = subAdminFilter === 'all' || item.sub_admin_username === subAdminFilter
      return matchesQ && matchesSub
    })
    const tc = filtered.length
    const tp = Math.max(1, Math.ceil(tc / activityPageSize))
    const cp = Math.min(activityPage, tp)
    const sIdx = (cp - 1) * activityPageSize
    const eIdx = Math.min(sIdx + activityPageSize, tc)
    return {
      pagedActivity: filtered.slice(sIdx, eIdx),
      totalActivityCount: tc,
      totalActivityPages: tp,
      curtActivityPage: cp,
      activityStartIdx: sIdx,
      activityEndIdx: eIdx,
    }
  }, [activityLogs, activityPage, activityPageSize, debouncedActivityQ, subAdminFilter])

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

      {/* Sub-Admin Audit Activity Log */}
      <section className="card">
        <div className="card-label">
          Sub-Admin Activity Audit Log {totalActivityCount > 0 ? `(${fmtInt(totalActivityCount)} total)` : ''}
        </div>
        <p className="login-sub" style={{ marginTop: 4 }}>
          Audit trail of every user-management action taken by sub-admins (tier changes, status toggles, quota resets).
        </p>

        <div className="card-filter-toolbar">
          <div className="toolbar-left">
            <input
              className="in"
              style={{ maxWidth: 260 }}
              placeholder="Search sub-admin, action, or target UID…"
              value={activityQ}
              onChange={(e) => setActivityQ(e.target.value)}
            />
            {rows.length > 0 && (
              <select className="in" style={{ width: 140 }} value={subAdminFilter} onChange={(e) => setSubAdminFilter(e.target.value)}>
                <option value="all">All sub-admins</option>
                {rows.map((r) => (
                  <option key={r.id} value={r.username}>{r.username}</option>
                ))}
              </select>
            )}
          </div>
          <div className="toolbar-right">
            <label className="field inline">
              <span>per page</span>
              <select className="in" style={{ width: 85 }} value={activityPageSize} onChange={(e) => setActivityPageSize(Number(e.target.value))}>
                <option value={10}>10</option>
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
            </label>
          </div>
        </div>

        {pagedActivity.length === 0 ? (
          <div className="empty">No sub-admin activity recorded yet.</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Sub-Admin</th>
                <th>Action</th>
                <th>Target User</th>
                <th>Details</th>
                <th>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {pagedActivity.map((item, idx) => (
                <tr key={item.id || `act-${idx}`}>
                  <td><span className="badge cool">{item.sub_admin_username}</span></td>
                  <td>
                    <span className="badge ok" style={{ textTransform: 'uppercase' }}>
                      {item.action}
                    </span>
                  </td>
                  <td>
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <span className="mono" style={{ fontSize: 12 }}>{item.target_email || item.target_uid}</span>
                      {item.target_email && item.target_email !== item.target_uid && (
                        <span className="card-sub" style={{ margin: 0, fontSize: 11 }}>UID: {item.target_uid}</span>
                      )}
                    </div>
                  </td>
                  <td>{formatDetails(item.details, item.action)}</td>
                  <td>{fmtClock(item.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <PaginationControls
          page={curtActivityPage}
          totalPages={totalActivityPages}
          totalCount={totalActivityCount}
          startIndex={activityStartIdx}
          endIndex={activityEndIdx}
          onPageChange={setActivityPage}
        />
      </section>
    </div>
  )
}
