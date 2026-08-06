import { useEffect, useState } from 'react'
import { usePolled, useNow } from '../hooks.js'
import {
  listAllAccounts, accountHealth, accountUsage, addAccount, updateAccount, deleteAccount,
  listPlans, updatePlan, fmtInt, fmtPct, fmtDur, fmtClock,
} from '../api.js'

export default function Accounts() {
  const { data: accData } = usePolled(() => listAllAccounts(), 5000)
  const { data: health } = usePolled(() => accountHealth(), 5000)
  const now = useNow(1000)

  const [live, setLive] = useState({})
  const [reload, setReload] = useState(0)
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
    const id = setInterval(load, 5000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [accData, reload])

  const accounts = accData?.accounts || []
  const apiErr = accData
    ? null
    : 'Could not load accounts — check your token / admin access, or that the backend is reachable.'

  return (
    <div className="stack">
      {apiErr && <div className="error">{apiErr}</div>}
      <div className="grid-2">
        <AddAccount onAdded={() => setReload((r) => r + 1)} />
        <PlanEditor onChanged={() => setReload((r) => r + 1)} />
      </div>

      <section className="card">
        <div className="card-label">Accounts — live{accounts.length ? ` (${accounts.length})` : ''}</div>
        {accounts.length === 0 ? (
          <div className="empty">No accounts yet. Add a Groq or OpenRouter key above.</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Provider</th>
                <th>API key</th>
                <th>Label</th>
                <th>Health</th>
                <th>Used / limit (today)</th>
                <th>RPM</th>
                <th>State</th>
                <th>Cooldown / reset</th>
                <th>Enabled</th>
                <th>Actions</th>
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
                  <AccountRow key={a.id} a={a} h={h} used={used} usedPct={usedPct}
                    limit={limit} live={lv} inCooldown={inCooldown} now={now}
                    onToggle={(enabled) =>
                      updateAccount(a.id, { enabled: enabled ? 1 : 0 }).then(() => setReload((r) => r + 1))}
                    onRemove={() => {
                      if (window.confirm(`Remove account ${a.label || a.id}?`)) {
                        deleteAccount(a.id).then(() => setReload((r) => r + 1))
                      }
                    }} />
                )
              })}
            </tbody>
          </table>
        )}
        <div className="card-sub note">
          Adding an account adds its full limit to the pool automatically — the router reads the dynamic list.
        </div>
      </section>
    </div>
  )
}

function AccountRow({ a, h, used, usedPct, limit, live, inCooldown, now, onToggle, onRemove }) {
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
    updateAccount(a.id, payload).then(() => {
      setErr(null)
      setKey('')
      setEditing(false)
    }).catch((e) => setErr(e.message || 'Save failed.'))
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
      <td><span className={`provider provider-${a.provider}`}>{a.provider}</span></td>
      <td>
        {editing
          ? <input type="password" className="in" placeholder="new key (blank = keep)" value={key}
              onChange={(e) => setKey(e.target.value)} title="Paste a new provider API key, or leave blank to keep the current one." />
          : <span className="mono" title={a.key_preview || undefined}>{a.key_preview || '—'}</span>}
      </td>
      <td>
        {editing
          ? <input className="in" value={label} onChange={(e) => setLabel(e.target.value)} />
          : (a.label || '—')}
      </td>
      <td>
        {h == null ? '—' : (
          <span className={`health health-${h < 0.3 ? 'bad' : h < 0.6 ? 'warn' : 'good'}`}>{fmtPct(h)}</span>
        )}
      </td>
      <td>
        <div className="usage-cell">
          <span className="mono">{fmtInt(used)} / {fmtInt(limit)}</span>
          <div className="bar thin">
            <div className={`bar-fill ${fillCls}`} style={{ width: `${usedPct}%` }} />
          </div>
        </div>
      </td>
      <td>{live ? fmtInt(live.rpm_window_count) : '—'}</td>
      <td>
        {stateCell}
        {live?.last_used ? <div className="sub">{fmtClock(live.last_used)} last</div> : null}
      </td>
      <td>{resetCell}</td>
      <td>
        <label className="switch">
          <input type="checkbox" checked={!!a.enabled} onChange={(e) => onToggle(e.target.checked)} />
          <span />
        </label>
      </td>
      <td className="actions">
        {editing ? (
          <>
            {err && <span className="error">{err}</span>}
            <button className="btn sm" onClick={save}>save</button>
            <button className="btn sm ghost" onClick={() => setEditing(false)}>cancel</button>
          </>
        ) : (
          <>
            <button className="btn sm ghost" onClick={() => setEditing(true)}>edit</button>
            <button className="btn sm danger" onClick={onRemove}>✕</button>
          </>
        )}
      </td>
    </tr>
  )
}

function AddAccount({ onAdded }) {
  const [provider, setProvider] = useState('groq')
  const [label, setLabel] = useState('')
  const [key, setKey] = useState('')
  const [dailylimit, setDailylimit] = useState('')
  const [rpmlimit, setRpmlimit] = useState('')
  const [msg, setMsg] = useState(null)
  const [err, setErr] = useState(null)

  async function submit(e) {
    e.preventDefault()
    setErr(null)
    setMsg(null)
    try {
      await addAccount({
        provider,
        label: label || null,
        key: key.trim(),
        daily_limit: dailylimit ? Number(dailylimit) : undefined,
        rpm_limit: rpmlimit ? Number(rpmlimit) : undefined,
      })
      setMsg('Account added — live in the pool.')
      setLabel('')
      setKey('')
      setDailylimit('')
      setRpmlimit('')
      onAdded()
    } catch (a) {
      setErr(a.message || 'Failed to add account.')
    }
  }

  return (
    <section className="card">
      <div className="card-label">Add account</div>
      <form className="form" onSubmit={submit}>
        <div className="row">
          {['groq', 'openrouter'].map((p) => (
            <label key={p} className="radio">
              <input type="radio" name="provider" checked={provider === p} onChange={() => setProvider(p)} /> {p}
            </label>
          ))}
        </div>
        <label className="field"><span>Label</span>
          <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="groq-key-1" /></label>
        <label className="field"><span>API key</span>
          <input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="sk-..." /></label>
        <div className="row">
          <label className="field grow"><span>Daily limit</span>
            <input 
              type="number" 
              value={dailylimit} 
              onChange={(e) => setDailylimit(e.target.value)} 
              placeholder="14400" 
            />
          </label>
          <label className="field grow"><span>RPM limit</span>
            <input 
              type="number" 
              value={rpmlimit} 
              onChange={(e) => setRpmlimit(e.target.value)} 
              placeholder="60" 
            />
          </label>
        </div>
        {err && <div className="error">{err}</div>}
        {msg && <div className="ok">{msg}</div>}
        <button className="btn primary" type="submit">Add</button>
      </form>
    </section>
  )
}

function PlanEditor({ onChanged }) {
  const { data, error } = usePolled(() => listPlans(), 15000)
  const [plans, setPlans] = useState([])
  const [msg, setMsg] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => {
    if (data) {
      setPlans((data.plans || []).map((p) => {
        // Convert daily_limit to proper value for input
        let editValue = ''
        if (p.daily_limit != null && p.daily_limit !== -1) {
          editValue = String(p.daily_limit)
        }
        return { ...p, edited: editValue }
      }))
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
    <section className="card">
      <div className="card-label">Plan limits</div>
      {err && <div className="error">{err}</div>}
      {msg && <div className="ok">{msg}</div>}
      {error && <div className="error">Could not load plans.</div>}
      {plans.length === 0 && !error ? (
        <div className="empty">No plans synced yet.</div>
      ) : (
        <div className="stack">
          {plans.map((p, idx) => (
            <div className="row-between" key={`${p.plan_id}-${idx}`}>
              <span className={`tier-pill tier-${p.plan_id}`}>{p.plan_id}</span>
              <label className="field inline">
                <span>daily limit</span>
                <input
                  className="in"
                  type="number"
                  value={p.edited}
                  placeholder={p.plan_id === 'pro' ? 'unlimited' : '10'}
                  onChange={(e) =>
                    setPlans(plans.map((x) => (x.plan_id === p.plan_id ? { ...x, edited: e.target.value } : x)))}
                  disabled={p.plan_id === 'pro'}
                />
              </label>
              <button className="btn sm" onClick={() => save(p.plan_id)}>save</button>
            </div>
          ))}
          <div className="card-sub">
            Pro is unlimited (NULL). Free defaults to 10. Edits write Firestore, synced to D1 within ~5 min.
          </div>
        </div>
      )}
    </section>
  )
}