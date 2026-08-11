import { useCallback, useEffect, useState } from 'react'
import { listUsers, setUserTier, setUserStatus, resetUserQuota, setUserUsage, fmtInt, fmtClock } from '../api.js'

const PAGE_SIZE = 25

const AVATAR_COLORS = ['#2563eb', '#7c3aed', '#db2777', '#ea580c', '#059669', '#d97706', '#dc2626', '#0891b2']

function Avatar({ u }) {
  const photo = u.photo_url || u.photoURL || u.avatar
  if (photo) {
    return <img src={photo} alt="" style={{ width: 28, height: 28, borderRadius: '50%', objectFit: 'cover' }} />
  }
  const name = u.name || u.displayName || u.email || '?'
  const initial = (name.trim()[0] || '?').toUpperCase()
  const hash = [...name].reduce((a, c) => a + c.charCodeAt(0), 0)
  const color = AVATAR_COLORS[hash % AVATAR_COLORS.length]
  return (
    <span
      aria-hidden="true"
      style={{
        display: 'inline-flex', width: 28, height: 28, borderRadius: '50%',
        alignItems: 'center', justifyContent: 'center',
        background: color, color: '#fff', fontSize: 13, fontWeight: 600, flexShrink: 0,
      }}
    >
      {initial}
    </span>
  )
}

export default function Users() {
  const [q, setQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [tier, setTier] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [acting, setActing] = useState(null)

  useEffect(() => {
    const id = setTimeout(() => setDebouncedQ(q), 300)
    return () => clearTimeout(id)
  }, [q])

  useEffect(() => { setPage(1) }, [debouncedQ, tier])

  const load = useCallback(async (query, tierSel) => {
    setBusy(true)
    try {
      const res = await listUsers(tierSel)
      let userList = []
      if (Array.isArray(res)) {
        userList = res
      } else if (res && Array.isArray(res.users)) {
        userList = res.users
      } else if (res && res.users && typeof res.users === 'object') {
        userList = Object.values(res.users)
      }
      setData(userList)
      setError('')
    } catch (e) {
      setError(e.message || 'Failed to load users')
      setData([])
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => { load(debouncedQ, tier) }, [debouncedQ, tier, load])

  const onApprove = async (uid, newTier) => {
    setActing(uid); setError('')
    try {
      await setUserTier(uid, newTier)
      await load(debouncedQ, tier)
    } catch (e) {
      setError(e.message)
    } finally {
      setActing(null)
    }
  }

  const onResetQuota = async (uid) => {
    if (!window.confirm("Reset this user's quota usage to 0 for today?")) return
    setActing(uid); setError('')
    try {
      await resetUserQuota(uid)
      await load(debouncedQ, tier)
    } catch (e) {
      setError(e.message)
    } finally {
      setActing(null)
    }
  }

  const onEditQuota = async (uid, currentUsage) => {
    const input = window.prompt("Enter new usage count for today (0 = full 10 quota available):", currentUsage || 0)
    if (input === null) return
    const val = parseInt(input, 10)
    if (isNaN(val) || val < 0) {
      alert("Invalid number")
      return
    }
    setActing(uid); setError('')
    try {
      await setUserUsage(uid, val)
      await load(debouncedQ, tier)
    } catch (e) {
      setError(e.message)
    } finally {
      setActing(null)
    }
  }

  const onToggleStatus = async (uid, currentActive) => {
    const newStatus = !currentActive
    const actionName = newStatus ? "activate" : "suspend / set offline"
    if (!window.confirm(`Are you sure you want to ${actionName} this user account?`)) return
    setActing(uid); setError('')
    try {
      await setUserStatus(uid, newStatus)
      await load(debouncedQ, tier)
    } catch (e) {
      setError(e.message)
    } finally {
      setActing(null)
    }
  }

  const allUsers = Array.isArray(data) ? data : []
  const ql = debouncedQ.trim().toLowerCase()
  const filtered = ql
    ? allUsers.filter((u) =>
        u && typeof u === 'object' && (
          (u.email || '').toLowerCase().includes(ql) ||
          (u.name || u.displayName || '').toLowerCase().includes(ql) ||
          (u.firebase_uid || u.uid || u.id || '').toLowerCase().includes(ql)
        )
      )
    : allUsers

  const safeFiltered = Array.isArray(filtered) ? filtered : []
  const pages = Math.max(1, Math.ceil(safeFiltered.length / PAGE_SIZE))
  const curt = Math.min(page, pages)
  const users = safeFiltered.slice((curt - 1) * PAGE_SIZE, curt * PAGE_SIZE)
  const total = safeFiltered.length

  return (
    <div className="stack">
      <section className="card">
        <div className="card-label">Users — {busy ? 'loading…' : `${fmtInt(total)} total`}</div>

        <div style={{ display: 'flex', gap: 10, marginBottom: 14, alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            className="in"
            style={{ maxWidth: 320 }}
            placeholder="Search email, name, or UID…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <select className="in" style={{ width: 140 }} value={tier} onChange={(e) => setTier(e.target.value)}>
            <option value="">All plans</option>
            <option value="free">Free</option>
            <option value="pro">Pro</option>
          </select>
        </div>

        {error && <div className="error">{error}</div>}

        {users.length === 0 ? (
          <div className="empty">{busy ? 'Loading…' : 'No users match your filters.'}</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>User</th>
                <th>Name</th>
                <th>Plan</th>
                <th>Usage (today)</th>
                <th>Active</th>
                <th>Last sync</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u, idx) => {
                const uid = u.firebase_uid || u.uid || u.id || `user-${idx}`
                const userTier = u.tier || 'free'
                const isActive = u.is_active ?? u.isActive ?? true
                const usageVal = u.usage_count ?? u.usageCount ?? 0
                const syncTs = u.synced_at || u.updatedAt

                return (
                  <tr key={uid}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Avatar u={u} />
                        <span>{u.email || '—'}</span>
                      </div>
                    </td>
                    <td>{u.name || u.displayName || '—'}</td>
                    <td><span className={`tier-pill tier-${userTier === 'pro' ? 'pro' : 'free'}`}>{userTier}</span></td>
                    <td>{fmtInt(usageVal)}</td>
                    <td>
                      <button
                        className={`status ${isActive ? 'status-ok' : 'status-err'}`}
                        style={{ border: 'none', cursor: 'pointer', background: 'transparent', padding: 0, fontWeight: 600 }}
                        disabled={acting === uid}
                        onClick={() => onToggleStatus(uid, isActive)}
                        title={isActive ? "Click to suspend account (offline)" : "Click to activate account"}
                      >
                        {isActive ? 'active 🟢' : 'suspended 🔴'}
                      </button>
                    </td>
                    <td>{syncTs ? fmtClock(syncTs) : '—'}</td>
                    <td>
                      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                        <select
                          className="in"
                          style={{ width: 90 }}
                          disabled={acting === uid}
                          value={userTier === 'pro' ? 'pro' : 'free'}
                          onChange={(e) => onApprove(uid, e.target.value)}
                        >
                          <option value="free">Free</option>
                          <option value="pro">Pro</option>
                        </select>
                        <button
                          className="btn sm ghost"
                          style={{ padding: '4px 8px', fontSize: 12 }}
                          disabled={acting === uid}
                          onClick={() => onEditQuota(uid, usageVal)}
                          title="Edit Quota Usage"
                        >
                          ✏️ Edit
                        </button>
                        <button
                          className="btn sm ghost"
                          style={{ padding: '4px 8px', fontSize: 12, color: '#10b981' }}
                          disabled={acting === uid}
                          onClick={() => onResetQuota(uid)}
                          title="Reset Quota to 0"
                        >
                          🔄 Reset
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}

        {data && pages > 1 && (
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', justifyContent: 'flex-end', marginTop: 14 }}>
            <button className="btn sm ghost" disabled={curt <= 1} onClick={() => setPage((p) => p - 1)}>Prev</button>
            <span className="card-label" style={{ margin: 0 }}>Page {curt} of {pages}</span>
            <button className="btn sm ghost" disabled={curt >= pages} onClick={() => setPage((p) => p + 1)}>Next</button>
          </div>
        )}
      </section>
    </div>
  )
}