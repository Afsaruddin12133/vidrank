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

function getProDaysRemaining(expiresAt) {
  if (!expiresAt) return 0
  let expTimeMs = 0
  if (typeof expiresAt === 'number') {
    expTimeMs = expiresAt > 1e11 ? expiresAt : expiresAt * 1000
  } else if (typeof expiresAt === 'string') {
    if (!isNaN(expiresAt)) {
      const num = Number(expiresAt)
      expTimeMs = num > 1e11 ? num : num * 1000
    } else {
      expTimeMs = new Date(expiresAt).getTime()
    }
  }
  if (!expTimeMs || isNaN(expTimeMs)) return 0
  const diffMs = expTimeMs - Date.now()
  if (diffMs <= 0) return 0
  return Math.ceil(diffMs / (1000 * 60 * 60 * 24))
}

function ProModal({ user, onClose, onConfirm }) {
  const [duration, setDuration] = useState('30') // default 1 month (30 days)
  const [customDays, setCustomDays] = useState('30')
  const [addBalance, setAddBalance] = useState(true) // checkmark default checked
  const [amount, setAmount] = useState(499) // default 499 taka
  const [busy, setBusy] = useState(false)

  const handleConfirm = async () => {
    setBusy(true)
    const days = duration === 'custom' ? Math.max(1, Number(customDays)) : Number(duration)
    await onConfirm({
      durationDays: days,
      addBalance,
      amount: Number(amount),
    })
    setBusy(false)
  }

  return (
    <div className="modal-overlay" style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.75)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999
    }}>
      <div className="card" style={{ maxWidth: 440, width: '90%', padding: 24, background: '#111827', border: '1px solid #374151', borderRadius: 12 }}>
        <h3 style={{ margin: '0 0 8px 0', fontSize: 18, color: '#f9fafb', display: 'flex', alignItems: 'center', gap: 8 }}>
          ⭐ Upgrade to PRO — {user.email || user.name || 'User'}
        </h3>
        <p className="card-sub" style={{ margin: '0 0 16px 0', fontSize: 13 }}>
          Configure duration and payment balance credit for this Pro subscription upgrade.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Duration Selector */}
          <div>
            <label className="field-label" style={{ fontWeight: 600, display: 'block', marginBottom: 6, color: '#e5e7eb' }}>
              📅 Pro Subscription Duration:
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              {[
                { label: '1 Month (30 Days)', value: '30' },
                { label: '15 Days', value: '15' },
                { label: '7 Days', value: '7' },
                { label: 'Custom Days', value: 'custom' },
              ].map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  className={`btn sm ${duration === opt.value ? 'primary' : 'ghost'}`}
                  onClick={() => setDuration(opt.value)}
                  style={{ textAlign: 'left', justifyContent: 'flex-start' }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            {duration === 'custom' && (
              <input
                className="in"
                type="number"
                min="1"
                placeholder="Enter days"
                value={customDays}
                onChange={(e) => setCustomDays(e.target.value)}
                style={{ marginTop: 8 }}
              />
            )}
          </div>

          {/* ৳499 Balance Checkmark */}
          <div style={{ padding: 12, borderRadius: 8, background: '#1f2937', border: '1px solid #374151' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontWeight: 600, color: '#10b981' }}>
              <input
                type="checkbox"
                checked={addBalance}
                onChange={(e) => setAddBalance(e.target.checked)}
                style={{ width: 18, height: 18, accentColor: '#10b981' }}
              />
              Add ৳{amount} Payment Balance & Total Revenue Credit
            </label>
            {addBalance && (
              <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
                <span className="card-sub" style={{ fontSize: 13 }}>Amount (Taka): ৳</span>
                <input
                  className="in"
                  type="number"
                  style={{ width: 110 }}
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                />
              </div>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 20 }}>
          <button className="btn ghost" disabled={busy} onClick={onClose}>
            Cancel
          </button>
          <button className="btn primary" disabled={busy} onClick={handleConfirm}>
            {busy ? 'Upgrading…' : `Confirm PRO Upgrade`}
          </button>
        </div>
      </div>
    </div>
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
  const [proModalUser, setProModalUser] = useState(null)

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

  const onTierSelectChange = (u, selectedTier) => {
    const uid = u.firebase_uid || u.uid || u.id
    const email = u.email || u.name || uid
    if (selectedTier === 'pro') {
      setProModalUser({ uid, email, name: u.name, raw: u })
    } else if (selectedTier === 'free') {
      const daysLeft = getProDaysRemaining(u.expires_at)
      if (u.tier === 'pro' && daysLeft > 0) {
        alert(
          `⚠️ Cannot downgrade to Free!\n\nUser "${email}" has an active Pro package running for another ${daysLeft} days.\n\nYou can only downgrade this account to Free after the Pro package time expires.`
        )
        return
      }
      onDowngradeToFree(uid, email)
    }
  }

  const onDowngradeToFree = async (uid, email) => {
    setActing(uid); setError('')
    try {
      await setUserTier(uid, 'free', email)
      await load(debouncedQ, tier)
    } catch (e) {
      setError(e.message)
    } finally {
      setActing(null)
    }
  }

  const onConfirmProUpgrade = async (options) => {
    if (!proModalUser) return
    const { uid, email } = proModalUser
    setActing(uid); setError('')
    try {
      await setUserTier(uid, 'pro', email, options)
      setProModalUser(null)
      await load(debouncedQ, tier)
    } catch (e) {
      setError(e.message)
    } finally {
      setActing(null)
    }
  }

  const onResetQuota = async (uid, email = '') => {
    if (!window.confirm("Reset this user's quota usage to 0 for today?")) return
    setActing(uid); setError('')
    try {
      await resetUserQuota(uid, email)
      await load(debouncedQ, tier)
    } catch (e) {
      setError(e.message)
    } finally {
      setActing(null)
    }
  }

  const onEditQuota = async (uid, currentUsage, email = '') => {
    const input = window.prompt("Enter new usage count for today (0 = full 10 quota available):", currentUsage || 0)
    if (input === null) return
    const val = parseInt(input, 10)
    if (isNaN(val) || val < 0) {
      alert("Invalid number")
      return
    }
    setActing(uid); setError('')
    try {
      await setUserUsage(uid, val, email)
      await load(debouncedQ, tier)
    } catch (e) {
      setError(e.message)
    } finally {
      setActing(null)
    }
  }

  const onToggleStatus = async (uid, currentActive, email = '') => {
    const newStatus = !currentActive
    const actionName = newStatus ? "activate" : "suspend / set offline"
    if (!window.confirm(`Are you sure you want to ${actionName} this user account?`)) return
    setActing(uid); setError('')
    try {
      await setUserStatus(uid, newStatus, email)
      await load(debouncedQ, tier)
    } catch (e) {
      setError(e.message)
    } finally {
      setActing(null)
    }
  }

  // Filter client-side
  const users = (data || []).filter((u) => {
    const query = debouncedQ.trim().toLowerCase()
    if (!query) return true
    const email = (u.email || '').toLowerCase()
    const name = (u.name || u.displayName || '').toLowerCase()
    const uid = (u.firebase_uid || u.uid || u.id || '').toLowerCase()
    return email.includes(query) || name.includes(query) || uid.includes(query)
  })

  const total = users.length
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const curt = Math.min(page, pages)
  const pageUsers = users.slice((curt - 1) * PAGE_SIZE, curt * PAGE_SIZE)

  return (
    <div className="stack">
      {proModalUser && (
        <ProModal
          user={proModalUser}
          onClose={() => setProModalUser(null)}
          onConfirm={onConfirmProUpgrade}
        />
      )}

      <section className="card">
        <div className="card-label">Users — {busy ? 'loading…' : `${fmtInt(total)} total`}</div>
        <p className="login-sub" style={{ marginTop: 4 }}>
          User directory synced from Firebase Auth. Change tier (Free / Pro) or activate/suspend accounts.
        </p>

        <div style={{ display: 'flex', gap: 10, margin: '14px 0', alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            className="in"
            style={{ maxWidth: 280 }}
            placeholder="Search email, name, or UID…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <select className="in" style={{ width: 130 }} value={tier} onChange={(e) => setTier(e.target.value)}>
            <option value="">All tiers</option>
            <option value="free">Free tier</option>
            <option value="pro">Pro tier</option>
          </select>
        </div>

        {error && <div className="error">{error}</div>}

        {pageUsers.length === 0 ? (
          <div className="empty">{busy ? 'Loading…' : 'No users found.'}</div>
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
              {pageUsers.map((u, idx) => {
                const uid = u.firebase_uid || u.uid || u.id || `user-${idx}`
                const userTier = u.tier || 'free'
                const isActive = u.is_active ?? u.isActive ?? true
                const usageVal = u.usage_count ?? u.usageCount ?? 0
                const syncTs = u.synced_at || u.updatedAt
                const email = u.email || u.name || uid
                const daysRemaining = getProDaysRemaining(u.expires_at)

                return (
                  <tr key={uid}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Avatar u={u} />
                        <span>{u.email || '—'}</span>
                      </div>
                    </td>
                    <td>{u.name || u.displayName || '—'}</td>
                    <td>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                        <span className={`tier-pill tier-${userTier === 'pro' ? 'pro' : 'free'}`}>{userTier}</span>
                        {userTier === 'pro' && daysRemaining > 0 && (
                          <span style={{ fontSize: 11, color: '#3b82f6', fontWeight: 600 }}>⏱️ {daysRemaining}d active</span>
                        )}
                        {u.balance > 0 && <span style={{ fontSize: 11, color: '#10b981', fontWeight: 600 }}>৳{u.balance} paid</span>}
                      </div>
                    </td>
                    <td>{fmtInt(usageVal)}</td>
                    <td>
                      <button
                        className={`status ${isActive ? 'status-ok' : 'status-err'}`}
                        style={{ border: 'none', cursor: 'pointer', background: 'transparent', padding: 0, fontWeight: 600 }}
                        disabled={acting === uid}
                        onClick={() => onToggleStatus(uid, isActive, email)}
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
                          onChange={(e) => onTierSelectChange(u, e.target.value)}
                        >
                          <option value="free">Free</option>
                          <option value="pro">Pro</option>
                        </select>
                        <button
                          className="btn sm ghost"
                          style={{ padding: '4px 8px', fontSize: 12 }}
                          disabled={acting === uid}
                          onClick={() => onEditQuota(uid, usageVal, email)}
                          title="Edit Quota Usage"
                        >
                          ✏️ Edit
                        </button>
                        <button
                          className="btn sm ghost"
                          style={{ padding: '4px 8px', fontSize: 12, color: '#10b981' }}
                          disabled={acting === uid}
                          onClick={() => onResetQuota(uid, email)}
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