import { useEffect, useState } from 'react'
import { usePolled, useNow } from '../hooks.js'
import {
  listAllAccounts, accountHealth, accountUsage, addAccount, updateAccount, deleteAccount,
  listPlans, updatePlan, fmtInt, fmtPct, fmtDur, fmtClock,
} from '../api.js'

export default function Accounts() {
  const { data: accData } = usePolled(() => listAllAccounts(), 30000)
  const { data: health } = usePolled(() => accountHealth(), 30000)
  const now = useNow(1000)

  const [live, setLive] = useState({})
  const [reload, setReload] = useState(0)
  const [showAddModal, setShowAddModal] = useState(false)
  const [showPlanModal, setShowPlanModal] = useState(false)
  const [copiedId, setCopiedId] = useState(null)

  useEffect(() => {
    let cancelled = false
    const load = () => {
      ;(accData?.accounts || []).forEach(async (a) => {
        try {
          const r = await accountUsage(a.id)
          if (!cancelled) setLive((p) => ({ ...p, [a.id]: r }))
        } catch {
          /* keep prior value */
        }
      })
    }
    load()
    const id = setInterval(load, 30000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [accData, reload])

  const accounts = accData?.accounts || []
  const enabledCount = accounts.filter((a) => a.enabled).length
  const disabledCount = accounts.length - enabledCount
  const totalUsedToday = Object.values(live).reduce((acc, curr) => acc + (curr?.live?.used_today || 0), 0)

  const apiErr = accData
    ? null
    : 'Could not load accounts — check your token / admin access, or that the backend is reachable.'

  const handleCopy = (text, id) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  return (
    <div className="stack" style={{ gap: 20 }}>
      {apiErr && <div className="error">{apiErr}</div>}

      {/* Page Header with Action Buttons */}
      <div className="page-header-row">
        <div className="page-header-info">
          <h1 className="page-title">API Key & Pool Management</h1>
          <p className="page-subtitle">
            Configure multi-provider API keys, automatic failover routing, rate limits, and health tracking.
          </p>
        </div>
        <div className="page-header-actions">
          <button className="btn ghost" onClick={() => setShowPlanModal(true)} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
            Plan Limits
          </button>
          <button className="btn primary" onClick={() => setShowAddModal(true)} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            Add New API Key
          </button>
        </div>
      </div>

      {/* Stats Overview Cards */}
      <div className="stats-grid-compact">
        <div className="stat-card-compact">
          <span className="stat-label">Total Accounts</span>
          <span className="stat-val">{accounts.length}</span>
          <span className="stat-sub">Across all AI providers</span>
        </div>
        <div className="stat-card-compact">
          <span className="stat-label">Active Pool</span>
          <span className="stat-val" style={{ color: enabledCount > 0 ? '#34d399' : '#f87171' }}>
            {enabledCount} Live
          </span>
          <span className="stat-sub">{disabledCount} disabled accounts</span>
        </div>
        <div className="stat-card-compact">
          <span className="stat-label">Total Handled Today</span>
          <span className="stat-val">{fmtInt(totalUsedToday)}</span>
          <span className="stat-sub">Generations consumed</span>
        </div>
        <div className="stat-card-compact">
          <span className="stat-label">Router Strategy</span>
          <span className="stat-val" style={{ fontSize: 16, color: '#38bdf8' }}>Smart Weighted</span>
          <span className="stat-sub">Health & RPM aware</span>
        </div>
      </div>

      {/* Main Accounts Table Card */}
      <section className="card" style={{ padding: 0 }}>
        <div style={{ padding: '18px 20px', borderBottom: '1px solid #1c1e2e', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div className="card-label" style={{ margin: 0 }}>
              Accounts Pool — Live{accounts.length ? ` (${accounts.length})` : ''}
            </div>
            <div className="card-sub" style={{ margin: '4px 0 0 0', fontSize: 12 }}>
              Dynamic failover list. Enabled keys automatically receive traffic based on real-time health score.
            </div>
          </div>
        </div>

        {accounts.length === 0 ? (
          <div className="empty" style={{ padding: '40px 20px' }}>
            <p>No API keys configured yet.</p>
            <button className="btn primary" onClick={() => setShowAddModal(true)}>+ Add First Key</button>
          </div>
        ) : (
          <div className="table-wrap" style={{ margin: 0 }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Provider</th>
                  <th>API Key Preview</th>
                  <th>Label</th>
                  <th>Health</th>
                  <th>Used / Limit (Today)</th>
                  <th>RPM</th>
                  <th>State</th>
                  <th>Cooldown / Reset</th>
                  <th>Enabled</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((a) => {
                  const lv = live[a.id]?.live
                  const limit = live[a.id]?.limit ?? a.daily_limit
                  const used = lv?.used_today ?? 0
                  const usedPct = limit ? Math.min(100, (used / limit) * 100) : 0
                  const inCooldown = !!(lv?.cooldown_until && now / 1000 < lv.cooldown_until)
                  const h = (health?.health || {})[a.id]?.health
                  return (
                    <AccountRow
                      key={a.id}
                      a={a}
                      h={h}
                      used={used}
                      usedPct={usedPct}
                      limit={limit}
                      live={lv}
                      inCooldown={inCooldown}
                      now={now}
                      copiedId={copiedId}
                      onCopyKey={handleCopy}
                      onToggle={(enabled) =>
                        updateAccount(a.id, { enabled: enabled ? 1 : 0 }).then(() => setReload((r) => r + 1))
                      }
                      onRemove={() => {
                        if (window.confirm(`Are you sure you want to remove account "${a.label || a.id}"?`)) {
                          deleteAccount(a.id).then(() => setReload((r) => r + 1))
                        }
                      }}
                    />
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Add Account Modal */}
      {showAddModal && (
        <AddAccountModal
          onClose={() => setShowAddModal(false)}
          onAdded={() => {
            setShowAddModal(false)
            setReload((r) => r + 1)
          }}
        />
      )}

      {/* Plan Limits Modal */}
      {showPlanModal && (
        <PlanLimitsModal
          onClose={() => setShowPlanModal(false)}
          onChanged={() => setReload((r) => r + 1)}
        />
      )}
    </div>
  )
}

function AccountRow({ a, h, used, usedPct, limit, live, inCooldown, now, copiedId, onCopyKey, onToggle, onRemove }) {
  const [editing, setEditing] = useState(false)
  const [label, setLabel] = useState(a.label || '')
  const [dailylimit, setDailylimit] = useState(a.daily_limit)
  const [rpmlimit, setRpmlimit] = useState(a.rpm_limit)
  const [key, setKey] = useState('')
  const [err, setErr] = useState(null)

  function save() {
    const payload = {
      label,
      daily_limit: Number(dailylimit),
      rpm_limit: Number(rpmlimit),
    }
    if (key.trim()) payload.key = key.trim()
    updateAccount(a.id, payload)
      .then(() => {
        setErr(null)
        setKey('')
        setEditing(false)
      })
      .catch((e) => setErr(e.message || 'Save failed.'))
  }

  const fillCls = usedPct > 85 ? 'danger' : usedPct > 60 ? 'warn' : ''
  let stateCell = <span className="badge ok">live</span>
  let resetCell = <span>—</span>
  if (inCooldown && live?.cooldown_until) {
    stateCell = <span className="badge cool">COOLDOWN</span>
    resetCell = <span className="mono">{fmtDur((live.cooldown_until * 1000 - now) / 1000)}</span>
  } else if (live?.header_remaining != null) {
    resetCell = <span className="mono">hdr {fmtInt(live.header_remaining)}</span>
  }

  return (
    <tr className={a.enabled ? '' : 'row-disabled'}>
      <td>
        <span className={`provider provider-${a.provider}`}>{a.provider}</span>
      </td>
      <td>
        {editing ? (
          <input
            type="password"
            className="in"
            placeholder="Paste new key (blank = keep)"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            style={{ width: 180 }}
          />
        ) : (
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span className="mono" title={a.key_preview || undefined}>
              {a.key_preview || '—'}
            </span>
            {a.key_preview && (
              <button
                type="button"
                onClick={() => onCopyKey(a.key_preview, a.id)}
                title="Copy preview"
                style={{ background: 'transparent', border: 'none', color: '#64748b', cursor: 'pointer', padding: 2, display: 'flex', alignItems: 'center' }}
              >
                {copiedId === a.id ? (
                  <span style={{ fontSize: 10, color: '#34d399' }}>✓</span>
                ) : (
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                  </svg>
                )}
              </button>
            )}
          </div>
        )}
      </td>
      <td>
        {editing ? (
          <input
            className="in"
            value={label}
            placeholder="Key Label"
            onChange={(e) => setLabel(e.target.value)}
            style={{ width: 130 }}
          />
        ) : (
          <span style={{ fontWeight: 500, color: a.label ? '#e2e8f0' : '#64748b' }}>
            {a.label || '—'}
          </span>
        )}
      </td>
      <td>
        {h == null ? (
          <span style={{ color: '#64748b' }}>—</span>
        ) : (
          <span className={`health health-${h < 0.3 ? 'bad' : h < 0.6 ? 'warn' : 'good'}`} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: h < 0.3 ? '#f87171' : h < 0.6 ? '#fbbf24' : '#34d399' }} />
            {fmtPct(h)}
          </span>
        )}
      </td>
      <td>
        <div className="usage-cell">
          <span className="mono" style={{ fontSize: 12 }}>
            {fmtInt(used)} / {fmtInt(limit)}
          </span>
          <div className="bar thin" style={{ marginTop: 4 }}>
            <div className={`bar-fill ${fillCls}`} style={{ width: `${usedPct}%` }} />
          </div>
        </div>
      </td>
      <td>
        <span className="mono">{live ? fmtInt(live.rpm_window_count) : '—'}</span>
      </td>
      <td>
        {stateCell}
        {live?.last_used ? <div className="sub" style={{ fontSize: 11, marginTop: 2 }}>{fmtClock(live.last_used)} last</div> : null}
      </td>
      <td>{resetCell}</td>
      <td>
        <label className="switch">
          <input type="checkbox" checked={!!a.enabled} onChange={(e) => onToggle(e.target.checked)} />
          <span />
        </label>
      </td>
      <td style={{ textAlign: 'right' }}>
        {editing ? (
          <div className="action-buttons-group" style={{ justifyContent: 'flex-end' }}>
            {err && <span className="error" style={{ fontSize: 11 }}>{err}</span>}
            <button className="btn sm primary" onClick={save}>Save</button>
            <button className="btn sm ghost" onClick={() => setEditing(false)}>Cancel</button>
          </div>
        ) : (
          <div className="action-buttons-group" style={{ justifyContent: 'flex-end' }}>
            <button className="action-pill-btn edit-pill" onClick={() => setEditing(true)} title="Edit Account">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
              </svg>
              edit
            </button>
            <button className="action-pill-btn delete-pill" onClick={onRemove} title="Remove Account">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
        )}
      </td>
    </tr>
  )
}

function AddAccountModal({ onClose, onAdded }) {
  const [provider, setProvider] = useState('openrouter')
  const [label, setLabel] = useState('')
  const [key, setKey] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [dailylimit, setDailylimit] = useState('50')
  const [rpmlimit, setRpmlimit] = useState('20')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  async function submit(e) {
    e.preventDefault()
    if (!key.trim()) {
      setErr('API key is required.')
      return
    }
    setErr(null)
    setBusy(true)
    try {
      await addAccount({
        provider,
        label: label.trim() || null,
        key: key.trim(),
        daily_limit: dailylimit ? Number(dailylimit) : 50,
        rpm_limit: rpmlimit ? Number(rpmlimit) : 20,
      })
      onAdded()
    } catch (a) {
      setErr(a.message || 'Failed to add account.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal-card">
        <div className="modal-header">
          <h3 className="modal-title">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" strokeWidth="2">
              <polyline points="16 18 22 12 16 6" />
              <polyline points="8 6 2 12 8 18" />
            </svg>
            Add New AI Provider Key
          </h3>
          <button className="modal-close-btn" onClick={onClose}>✕</button>
        </div>

        <form onSubmit={submit}>
          <div className="modal-body">
            {err && <div className="error">{err}</div>}

            <div className="field">
              <span>Provider Selection</span>
              <div className="row" style={{ marginTop: 4 }}>
                {['openrouter', 'groq'].map((p) => (
                  <label
                    key={p}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      padding: '8px 14px',
                      borderRadius: 8,
                      border: `1px solid ${provider === p ? '#38bdf8' : '#242c3d'}`,
                      background: provider === p ? 'rgba(56, 189, 248, 0.1)' : 'transparent',
                      cursor: 'pointer',
                      fontWeight: 600,
                      textTransform: 'capitalize',
                      color: provider === p ? '#38bdf8' : '#9ca3af',
                    }}
                  >
                    <input
                      type="radio"
                      name="provider"
                      checked={provider === p}
                      onChange={() => {
                        setProvider(p)
                        if (p === 'groq') {
                          setDailylimit('14400')
                          setRpmlimit('30')
                        } else {
                          setDailylimit('50')
                          setRpmlimit('20')
                        }
                      }}
                      style={{ accentColor: '#38bdf8' }}
                    />
                    {p}
                  </label>
                ))}
              </div>
            </div>

            <label className="field">
              <span>Label / Account Name</span>
              <input
                className="in"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="e.g. OpenRouter Prod Key 9"
              />
            </label>

            <label className="field">
              <span>API Key</span>
              <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                <input
                  className="in"
                  type={showKey ? 'text' : 'password'}
                  value={key}
                  onChange={(e) => setKey(e.target.value)}
                  placeholder={provider === 'groq' ? 'gsk_...' : 'sk-or-...'}
                  style={{ paddingRight: 40 }}
                />
                <button
                  type="button"
                  onClick={() => setShowKey(!showKey)}
                  style={{
                    position: 'absolute',
                    right: 10,
                    background: 'transparent',
                    border: 'none',
                    color: '#64748b',
                    cursor: 'pointer',
                    fontSize: 12,
                  }}
                >
                  {showKey ? 'Hide' : 'Show'}
                </button>
              </div>
            </label>

            <div className="row" style={{ gap: 12 }}>
              <label className="field grow">
                <span>Daily Limit (Requests)</span>
                <input
                  className="in"
                  type="number"
                  value={dailylimit}
                  onChange={(e) => setDailylimit(e.target.value)}
                  placeholder="50"
                />
              </label>
              <label className="field grow">
                <span>RPM Limit</span>
                <input
                  className="in"
                  type="number"
                  value={rpmlimit}
                  onChange={(e) => setRpmlimit(e.target.value)}
                  placeholder="20"
                />
              </label>
            </div>
          </div>

          <div className="modal-footer">
            <button type="button" className="btn ghost" onClick={onClose} disabled={busy}>
              Cancel
            </button>
            <button type="submit" className="btn primary" disabled={busy}>
              {busy ? 'Adding...' : '+ Add to Live Pool'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function PlanLimitsModal({ onClose, onChanged }) {
  const { data, error } = usePolled(() => listPlans(), 15000)
  const [plans, setPlans] = useState([])
  const [msg, setMsg] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    if (data) {
      setPlans(
        (data.plans || []).map((p) => {
          let editValue = ''
          if (p.daily_limit != null && p.daily_limit !== -1) {
            editValue = String(p.daily_limit)
          }
          return { ...p, edited: editValue }
        })
      )
    }
  }, [data])

  function save(planId) {
    const plan = plans.find((p) => p.plan_id === planId)
    const val = plan.edited === '' || plan.edited == null ? null : Number(plan.edited)
    updatePlan({ plan_id: planId, daily_limit: val })
      .then(() => {
        setErr(null)
        setMsg('Plan saved — synced to Firestore + D1.')
        onChanged()
      })
      .catch((e) => setErr(e.message || 'Failed to update plan.'))
  }

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal-card">
        <div className="modal-header">
          <h3 className="modal-title">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" strokeWidth="2">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
            Tier Generation Limits
          </h3>
          <button className="modal-close-btn" onClick={onClose}>✕</button>
        </div>

        <div className="modal-body">
          {err && <div className="error">{err}</div>}
          {msg && <div className="ok">{msg}</div>}
          {error && <div className="error">Could not load plans.</div>}

          {plans.map((p, idx) => (
            <div
              key={`${p.plan_id}-${idx}`}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '14px 16px',
                borderRadius: 10,
                background: '#141824',
                border: '1px solid #242c3d',
              }}
            >
              <div>
                <span className={`tier-pill tier-${p.plan_id}`}>{p.plan_id}</span>
                <div style={{ fontSize: 12, color: '#8b95a9', marginTop: 4 }}>
                  {p.plan_id === 'pro' ? 'Unlimited generations per day' : 'Daily generation cap for free tier'}
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <input
                  className="in"
                  type="number"
                  value={p.edited}
                  placeholder={p.plan_id === 'pro' ? 'unlimited' : '10'}
                  onChange={(e) =>
                    setPlans(
                      plans.map((x) =>
                        x.plan_id === p.plan_id ? { ...x, edited: e.target.value } : x
                      )
                    )
                  }
                  disabled={p.plan_id === 'pro'}
                  style={{ width: 90, textAlign: 'center' }}
                />
                <button className="btn sm primary" onClick={() => save(p.plan_id)}>
                  Save
                </button>
              </div>
            </div>
          ))}
          <p className="card-sub" style={{ margin: 0, fontSize: 12 }}>
            Pro tier is unlimited. Changes sync to Firestore and D1 cache automatically.
          </p>
        </div>

        <div className="modal-footer">
          <button className="btn ghost" onClick={onClose}>
            Done
          </button>
        </div>
      </div>
    </div>
  )
}