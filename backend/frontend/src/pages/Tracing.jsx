import { useMemo, useState } from 'react'
import { usePolled } from '../hooks.js'
import { statsUsage, accountsUsageDay, listAllAccounts, fmtInt, fmtPct, fmtDur } from '../api.js'

const W = 640
const H = 180
const PAD = { l: 44, r: 10, t: 10, b: 22 }

// Raw-SVG line chart: values -> polyline with min/max labels.
function LineChart({ points, color = '#7dd3fc', label = '' }) {
  const data = useMemo(() => {
    const n = points.length
    if (n === 0) return null
    const max = Math.max(...points, 1)
    const x = (i) => PAD.l + (i / Math.max(1, n - 1)) * (W - PAD.l - PAD.r)
    const y = (v) => PAD.t + (1 - v / max) * (H - PAD.t - PAD.b)
    const d = points.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
    return { max, d, x, y }
  }, [points])

  if (!data) return <div className="empty">No data yet.</div>
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label={label}>
      {[0.25, 0.5, 0.75, 1].map((f) => (
        <line key={f} x1={PAD.l} x2={W - PAD.r} y1={PAD.t + f * (H - PAD.t - PAD.b)}
          y2={PAD.t + f * (H - PAD.t - PAD.b)} className="gridline" />
      ))}
      <polyline points={data.d} fill="none" stroke={color} strokeWidth="2" />
      {points.map((v, i) => (
        <circle key={i} cx={data.x(i)} cy={data.y(v)} r="2.4" fill={color} />
      ))}
      <text x={PAD.l} y={H - 6} className="axis">{label}</text>
      <text x={W - PAD.r} y={PAD.t + 10} textAnchor="end" className="axis">{fmtInt(data.max)}</text>
    </svg>
  )
}

// Per-account bars with a drawn daily-limit line.
function AccountBars({ account }) {
  const days = account?.days || []
  const limit = account.daily_limit || null
  const data = useMemo(() => {
    if (days.length === 0) return null
    const vals = days.map((d) => d.requests || 0)
    const max = Math.max(...vals, limit || 0, 1)
    const x = (i) => PAD.l + (i + 0.15) * ((W - PAD.l - PAD.r) / days.length)
    const bw = Math.max(2, 0.7 * ((W - PAD.l - PAD.r) / days.length))
    const y = (v) => PAD.t + (1 - v / max) * (H - PAD.t - PAD.b)
    return { max, x, bw, y, vals }
  }, [days, limit])

  if (!data) return <div className="empty">No daily usage for this account yet.</div>
  const limitY = limit != null ? data.y(limit) : null
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label={`${account.label || account.id} usage vs limit`}>
      {[0.25, 0.5, 0.75, 1].map((f) => (
        <line key={f} x1={PAD.l} x2={W - PAD.r} y1={PAD.t + f * (H - PAD.t - PAD.b)}
          y2={PAD.t + f * (H - PAD.t - PAD.b)} className="gridline" />
      ))}
      {data.vals.map((v, i) => (
        <rect key={i} x={data.x(i)} y={data.y(v)} width={data.bw}
          height={Math.max(0, H - PAD.b - data.y(v))} className="bar-rect" />
      ))}
      {limitY != null && (
        <>
          <line x1={PAD.l} x2={W - PAD.r} y1={limitY} y2={limitY} className="limit-line" />
          <text x={W - PAD.r} y={limitY - 4} textAnchor="end" className="limit-label">limit {fmtInt(limit)}</text>
        </>
      )}
      {days.map((d, i) => (
        <text key={i} x={data.x(i) + data.bw / 2} y={H - 6} textAnchor="middle" className="axis small">
          {d.day.slice(5)}
        </text>
      ))}
    </svg>
  )
}

function StatsCard({ label, value, sub }) {
  return (
    <div className="card mini">
      <div className="card-label">{label}</div>
      <div className="big">{value}</div>
      {sub && <div className="card-sub">{sub}</div>}
    </div>
  )
}

export default function Tracing() {
  const [days, setDays] = useState(14)
  const { data: site } = usePolled(() => statsUsage(days), 15000, [days])
  const { data: perAccount } = usePolled(() => accountsUsageDay(days), 15000, [days])

  const sDays = site?.days || []
  const accts = perAccount?.accounts || []
  const totals = useMemo(() => {
    let total = 0, free = 0, pro = 0, cache = 0, errors = 0, latSum = 0, latN = 0
    for (const d of sDays) {
      total += d.total_requests || 0
      free += d.free_requests || 0
      pro += d.pro_requests || 0
      cache += d.cache_hits || 0
      errors += d.errors || 0
      if (d.avg_latency_ms != null) { latSum += d.avg_latency_ms * (d.total_requests || 1); latN += d.total_requests || 1 }
    }
    const avgLat = latN ? latSum / latN : null
    const success = total ? 1 - errors / total : null
    return { total, free, pro, cache, errors, avgLat, success, cacheRatio: total ? cache / total : null }
  }, [sDays])

  // live usage (today) for exhaustion estimates
  const { data: accList } = usePolled(() => listAllAccounts(), 15000)
  const enabledIds = new Set((accList?.accounts || []).filter((a) => a.enabled).map((a) => a.id))
  const nearCap = accts.filter((a) => {
    const d = (a.days || []).slice(-1)[0]
    return a.daily_limit && d && d.requests >= a.daily_limit * 0.8
  })

  return (
    <div className="stack">
      <div className="row-between">
        <h2>Tracing / Analytics</h2>
        <label className="field inline">
          <span>range</span>
          <select className="in" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {[7, 14, 30, 90].map((d) => <option key={d} value={d}>{d} days</option>)}
          </select>
        </label>
      </div>

      <section className="cards">
        <StatsCard label="Total requests" value={fmtInt(totals.total)} sub={`${days} days`} />
        <StatsCard label="Success rate" value={fmtPct(totals.success)} sub={`${fmtInt(totals.errors)} errors`} />
        <StatsCard label="Avg latency" value={totals.avgLat == null ? '—' : `${totals.avgLat.toFixed(0)}ms`} sub="weighted p50 proxy" />
        <StatsCard label="Cache hit ratio" value={fmtPct(totals.cacheRatio)} sub={`${fmtInt(totals.cache)} hits`} />
      </section>

      <div className="grid-2">
        <section className="card">
          <div className="card-label">Requests over time (free vs pro)</div>
          {sDays.length === 0 ? <div className="empty">No usage recorded yet.</div> : (
            <>
              <LineChart points={sDays.map((d) => d.free_requests || 0)} color="#38bdf8" label="free" />
              <LineChart points={sDays.map((d) => d.pro_requests || 0)} color="#a78bfa" label="pro" />
            </>
          )}
        </section>
        <section className="card">
          <div className="card-label">Free vs pro split</div>
          {totals.total === 0 ? <div className="empty">No usage yet.</div> : (
            <div className="split">
              <div className="split-row">
                <span className="split-label">free</span>
                <div className="bar"><div className="bar-fill free" style={{ width: `${(totals.free / totals.total) * 100}%` }} /></div>
                <span className="mono">{fmtInt(totals.free)}</span>
              </div>
              <div className="split-row">
                <span className="split-label">pro</span>
                <div className="bar"><div className="bar-fill pro" style={{ width: `${(totals.pro / totals.total) * 100}%` }} /></div>
                <span className="mono">{fmtInt(totals.pro)}</span>
              </div>
              <div className="split-row">
                <span className="split-label">errors</span>
                <div className="bar"><div className="bar-fill danger" style={{ width: `${(totals.errors / totals.total) * 100}%` }} /></div>
                <span className="mono">{fmtInt(totals.errors)}</span>
              </div>
            </div>
          )}
        </section>
      </div>

      <section className="card">
        <div className="card-label">Per-account usage vs limit (with limit line)</div>
        {accts.length === 0 ? (
          <div className="empty">No accounts with usage yet — add accounts and wait for traffic.</div>
        ) : (
          <div className="acc-charts">
            {accts.map((a) => (
              <div className="acc-chart" key={a.id}>
                <div className="acc-title">
                  <span>{a.label || a.id}</span>
                  <span className={`provider provider-${a.provider}`}>{a.provider}</span>
                  {!enabledIds.has(a.id) && <span className="badge cool">disabled</span>}
                </div>
                <AccountBars account={a} />
              </div>
            ))}
          </div>
        )}
        {nearCap.length > 0 && (
          <div className="error warn-box">
            Near-cap: {nearCap.map((a) => a.label || a.id).join(', ')} are at ≥80% of daily limit.
          </div>
        )}
      </section>

      <section className="card">
        <div className="card-label">Per-account table</div>
        {accts.length === 0 ? (
          <div className="empty">No data yet — add accounts or wait for usage.</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Account</th>
                <th>Success rate</th>
                <th>p50/p95 ms</th>
                <th>Failures</th>
                <th>Used / limit</th>
                <th>Est. exhaustion</th>
                <th>State</th>
              </tr>
            </thead>
            <tbody>
              {accts.map((a) => {
                const d = (a.days || []).slice(-1)[0]
                const last = (a.days || []).slice(-1)[0]
                const requests = last?.requests || 0
                const errors = last?.errors || 0
                const success = requests ? 1 - errors / requests : null
                const p50 = last?.avg_latency_ms
                const p95 = last?.avg_latency_ms != null ? last.avg_latency_ms * 1.8 : null
                const limit = a.daily_limit
                const used = (a.days || []).reduce((s, x) => s + (x.requests || 0), 0)
                const exhaustion = exhaustionEst(used, d?.day, limit)
                return (
                  <tr key={a.id}>
                    <td><span className={`provider provider-${a.provider}`}>{a.provider}</span> {a.label || a.id}</td>
                    <td>{fmtPct(success)}</td>
                    <td>{p50 == null ? '—' : `${p50.toFixed(0)} / ${p95.toFixed(0)}`}</td>
                    <td>{fmtInt(errors)}</td>
                    <td className="mono">{fmtInt(used)} / {fmtInt(limit)}</td>
                    <td>{exhaustion}</td>
                    <td>{enabledIds.has(a.id) ? <span className="badge ok">enabled</span> : <span className="badge cool">disabled</span>}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}

// Estimate when an account hits its daily cap given its average per-day rate.
function exhaustionEst(totalUsed, lastDay, limit) {
  if (!limit) return '—'
  if (!lastDay || totalUsed <= 0) return '—'
  if (totalUsed >= limit) return <span className="badge cool">exhausted</span>
  const today = new Date().toISOString().slice(0, 10)
  const usedToday = today === lastDay ? totalUsed : 0
  if (today !== lastDay) return '—' // no activity today yet
  // very rough: assume today's usage keeps pace with average daily rate
  const hourFrac = new Date().getHours() / 24
  const pace = hourFrac > 0 ? usedToday / hourFrac : 0
  if (pace <= 0) return '—'
  const hoursLeft = (limit - usedToday) / pace
  if (hoursLeft > 24) return '—'
  if (hoursLeft <= 0) return <span className="badge cool">exhausted</span>
  return <span>{fmtDur(Math.max(0, Math.round(hoursLeft * 3600)))} left</span>
}