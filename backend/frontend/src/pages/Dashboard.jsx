import { useState } from 'react'
import { usePolled } from '../hooks.js'
import { statsOverview, listUsers, listAllAccounts, getPricing, adminGeo, getFreeQuota, setFreeQuota, fmtInt } from '../api.js'

const CADENC_LABEL = { daily: 'Daily (resets each day)', never: 'Never (one-time total)', unlimited: 'Unlimited (no cap)' }

export default function Dashboard() {
  const { data: overview } = usePolled(() => statsOverview(), 5000)
  const { data: usersData } = usePolled(() => listUsers(), 5000)
  const { data: accountsData } = usePolled(() => listAllAccounts(), 5000)
  const { data: pricingData } = usePolled(() => getPricing(), 10000)
  
  const days = overview?.days || []
  const today = days[0] || {}
  const users = usersData?.users || []
  const accounts = accountsData?.accounts || []
  const pricing = pricingData?.pricing || {}
  
  const freeUsers = users.filter(u => u.tier === 'free').length
  const proUsers = users.filter(u => u.tier === 'pro').length
  const totalRequests = today.total_requests || 0
  const cacheHits = today.cache_hits || 0
  const errors = today.errors || 0
  const cacheHitRate = totalRequests > 0 ? (cacheHits / totalRequests) * 100 : 0

  // Calculate capacity metrics
  const totalDailyCapacity = accounts.reduce((sum, a) => sum + (a.daily_limit || 0), 0)
  const totalRPMCapacity = accounts.reduce((sum, a) => sum + (a.rpm_limit || 0), 0)
  const capacityUsage = totalDailyCapacity > 0 ? (totalRequests / totalDailyCapacity) * 100 : 0
  const remainingToday = totalDailyCapacity - totalRequests
  
  // Calculate 7-day average
  const last7Days = days.slice(0, 7)
  const avgDailyRequests = last7Days.length > 0 
    ? last7Days.reduce((sum, d) => sum + (d.total_requests || 0), 0) / last7Days.length 
    : 0
  const projectedMonthly = avgDailyRequests * 30
  
  // DYNAMIC PRICING - Get from Firebase plans (no more hardcoded!)
  const costPerRequest = pricing.free?.request_cost || 0.0001  // Fallback to estimate
  const proPrice = pricing.pro?.monthly_price || 10  // Fallback to default
  const freePrice = pricing.free?.monthly_price || 0
  
  const todayCost = totalRequests * costPerRequest
  const projectedMonthlyCost = projectedMonthly * costPerRequest
  
  // Revenue potential (if pro users pay)
  const potentialMonthlyRevenue = proUsers * proPrice
  const profitMargin = potentialMonthlyRevenue - projectedMonthlyCost
  
  const { data: quota } = usePolled(() => getFreeQuota(), 10000)
  const [limit, setLimit] = useState(10)
  const [cadence, setCadence] = useState('daily')
  const [windowDays, setWindowDays] = useState(0)
  const [saved, setSaved] = useState('')
  const [saveErr, setSaveErr] = useState('')
  const [saving, setSaving] = useState(false)

  // guarded setState-on-render so re-polls never clobber in-progress edits; populates the form once on first load
  const [synced, setSynced] = useState(false)
  if (quota && !synced) {
    setLimit(quota.limit)
    setCadence(quota.cadence)
    setWindowDays(quota.window_days)
    setSynced(true)
  }

  const saveFreeQuota = async () => {
    setSaving(true); setSaved(''); setSaveErr('')
    try {
      await setFreeQuota({ limit: Number(limit), cadence, window_days: Number(windowDays) })
      setSaved('Saved — free users now see the updated quota.')
    } catch (e) {
      setSaveErr(e.message)
    } finally {
      setSaving(false)
    }
  }

  const userBalancesSum = users.reduce((sum, u) => sum + Number(u.balance || 0), 0)
  const localEarnings = Number(localStorage.getItem('vidrank_total_earnings') || 0)
  const totalRevenueTaka = Math.max(userBalancesSum, proUsers * 499) + localEarnings

  return (
    <div className="stack">
      {/* Top metrics */}
      <section className="cards">
        <div className="card">
          <div className="card-label">Total Users</div>
          <div className="big">{fmtInt(users.length)}</div>
          <div className="card-sub">
            {fmtInt(freeUsers)} free • {fmtInt(proUsers)} pro
          </div>
        </div>
        <div className="card">
          <div className="card-label">Total Revenue Earned</div>
          <div className="big" style={{ color: '#10b981' }}>৳{fmtInt(totalRevenueTaka)}</div>
          <div className="card-sub">
            {fmtInt(proUsers)} Pro users • ৳499 per upgrade
          </div>
        </div>
        <div className="card">
          <div className="card-label">Requests Today</div>
          <div className="big">{fmtInt(totalRequests)}</div>
          <div className="card-sub">
            {fmtInt(today.free_requests || 0)} free • {fmtInt(today.pro_requests || 0)} pro
          </div>
        </div>
        <div className="card">
          <div className="card-label">Cache Hit Rate</div>
          <div className="big">
            {cacheHitRate.toFixed(1)}%
          </div>
          <div className="bar">
            <div className="bar-fill ok" style={{ width: `${cacheHitRate}%` }} />
          </div>
          <div className="card-sub">
            {fmtInt(cacheHits)} / {fmtInt(totalRequests)} cached
          </div>
        </div>
      </section>

      {/* Capacity Analysis */}
      <section className="cards">
        <div className="card">
          <div className="card-label">Daily Capacity</div>
          <div className="big">{fmtInt(totalDailyCapacity)}</div>
          <div className="bar">
            <div 
              className={`bar-fill ${capacityUsage > 80 ? 'err' : capacityUsage > 60 ? 'warn' : 'ok'}`}
              style={{ width: `${Math.min(capacityUsage, 100)}%` }} 
            />
          </div>
          <div className="card-sub">
            {fmtInt(remainingToday)} remaining ({capacityUsage.toFixed(1)}% used)
          </div>
        </div>
        <div className="card">
          <div className="card-label">API Accounts</div>
          <div className="big">{accounts.length}</div>
          <div className="card-sub">
            {totalRPMCapacity} req/min capacity
          </div>
        </div>
        <div className="card">
          <div className="card-label">Avg Daily (7d)</div>
          <div className="big">{fmtInt(avgDailyRequests)}</div>
          <div className="card-sub">
            ~{fmtInt(projectedMonthly)}/month projected
          </div>
        </div>
        <div className="card">
          <div className="card-label">Cache Savings</div>
          <div className="big">{cacheHits > 0 ? fmtInt(cacheHits) : '0'}</div>
          <div className="card-sub">
            ${(cacheHits * costPerRequest).toFixed(2)} saved today
          </div>
        </div>
      </section>

      {/* Revenue & Cost Analysis — HIDDEN for now (was computed from hardcoded request_cost) */}
      {false && (
      <section className="card">
        <div className="card-label">💰 Revenue & Cost Analysis (Dynamic from Firebase)</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '1rem', marginTop: '1rem' }}>
          <div>
            <div style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.5rem' }}>Today's API Cost</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>${todayCost.toFixed(2)}</div>
            <div style={{ fontSize: '0.75rem', color: '#9ca3af', marginTop: '0.25rem' }}>
              {totalRequests} requests × ${costPerRequest.toFixed(6)}
            </div>
          </div>
          <div>
            <div style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.5rem' }}>Projected Monthly Cost</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>${projectedMonthlyCost.toFixed(2)}</div>
            <div style={{ fontSize: '0.75rem', color: '#9ca3af', marginTop: '0.25rem' }}>
              Based on 7-day average
            </div>
          </div>
          {paidUsers > 0 ? (
            <>
              <div>
                <div style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.5rem' }}>Actual Revenue</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#10b981' }}>${actualMonthlyRevenue.toFixed(2)}/mo</div>
                <div style={{ fontSize: '0.75rem', color: '#9ca3af', marginTop: '0.25rem' }}>
                  {paidUsers} paid users × ${proPrice}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.5rem' }}>Actual Profit</div>
                <div style={{ 
                  fontSize: '1.5rem', 
                  fontWeight: 'bold',
                  color: actualProfitMargin > 0 ? '#10b981' : '#ef4444'
                }}>
                  ${actualProfitMargin.toFixed(2)}/mo
                </div>
                <div style={{ fontSize: '0.75rem', color: '#9ca3af', marginTop: '0.25rem' }}>
                  {actualProfitMargin > 0 ? '✅ Profitable!' : '❌ Need more users'}
                </div>
              </div>
            </>
          ) : (
            <>
              <div>
                <div style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.5rem' }}>Potential Revenue</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#f59e0b' }}>${potentialMonthlyRevenue.toFixed(2)}/mo</div>
                <div style={{ fontSize: '0.75rem', color: '#9ca3af', marginTop: '0.25rem' }}>
                  {proUsers} pro users × ${proPrice}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.5rem' }}>Potential Profit</div>
                <div style={{ 
                  fontSize: '1.5rem', 
                  fontWeight: 'bold',
                  color: '#f59e0b'
                }}>
                  ${profitMargin.toFixed(2)}/mo
                </div>
                <div style={{ fontSize: '0.75rem', color: '#9ca3af', marginTop: '0.25rem' }}>
                  ⚠️ If they all pay
                </div>
              </div>
            </>
          )}
        </div>
        
        {/* Pricing Info */}
        <div style={{ marginTop: '1rem', padding: '0.75rem', background: '#374151', borderRadius: '0.5rem' }}>
          <div style={{ fontSize: '0.875rem', color: '#d1d5db' }}>
            <strong>💳 Pricing from Firebase:</strong> Free = ${freePrice}/mo, Pro = ${proPrice}/mo
            {paidUsers === 0 && proUsers > 0 && (
              <span style={{ color: '#f59e0b' }}> • ⚠️ No active subscriptions detected</span>
            )}
          </div>
        </div>
        
        {/* Recommendations */}
        <div style={{ marginTop: '1.5rem', padding: '1rem', background: '#1f2937', borderRadius: '0.5rem', border: '1px solid #374151' }}>
          <div style={{ fontWeight: 'bold', marginBottom: '0.5rem', color: '#f9fafb' }}>📊 Recommendations:</div>
          <ul style={{ margin: 0, paddingLeft: '1.5rem', fontSize: '0.875rem', color: '#d1d5db' }}>
            {capacityUsage > 80 && (
              <li style={{ color: '#ef4444', marginBottom: '0.25rem' }}>
                ⚠️ Capacity at {capacityUsage.toFixed(0)}% - Consider adding more API accounts
              </li>
            )}
            {profitMargin < 0 && (
              <li style={{ color: '#f59e0b', marginBottom: '0.25rem' }}>
                💡 Convert {Math.ceil(Math.abs(profitMargin) / 10)} more users to Pro to break even
              </li>
            )}
            {cacheHitRate < 30 && totalRequests > 0 && (
              <li style={{ color: '#3b82f6', marginBottom: '0.25rem' }}>
                🎯 Cache hit rate is {cacheHitRate.toFixed(0)}% - Optimize caching to reduce costs
              </li>
            )}
            {proUsers === 0 && (
              <li style={{ color: '#8b5cf6', marginBottom: '0.25rem' }}>
                🚀 No pro users yet - Start marketing to convert free users!
              </li>
            )}
            {capacityUsage < 50 && profitMargin > 100 && (
              <li style={{ color: '#10b981', marginBottom: '0.25rem' }}>
                ✅ Healthy margins! You can support {Math.floor(remainingToday / (avgDailyRequests / Math.max(users.length, 1)))} more users
              </li>
            )}
            {proUsers > 0 && profitMargin > 0 && (
              <li style={{ color: '#10b981', marginBottom: '0.25rem' }}>
                💰 Note: Profit assumes pro users are PAYING. Enable payments in Firebase!
              </li>
            )}
          </ul>
        </div>
      </section>
      )}

      {/* Free Quota Settings */}
      <section className="card">
        <div className="card-label">Free Tier Quota</div>
        <div className="card-sub" style={{ marginBottom: 14 }}>
          How many requests a free user gets. Saved to the backend and reflected live in the extension.
          {quota && (
            <span className="note"> Current: {quota.cadence === 'unlimited' ? 'unlimited' : `${quota.limit} / ${quota.cadence === 'never' ? 'ever' : 'day'}`}{quota.window_days > 0 ? ` for ${quota.window_days} days` : ''}</span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <label>
            <div className="card-sub">Limit</div>
            <input className="in" type="number" min="1" value={limit}
              onChange={(e) => setLimit(e.target.value)} style={{ width: 90 }} />
          </label>
          <label>
            <div className="card-sub">Reset cadence</div>
            <select className="in" value={cadence} onChange={(e) => setCadence(e.target.value)} style={{ width: 210 }}>
              <option value="daily">Daily</option>
              <option value="never">Never</option>
              <option value="unlimited">Unlimited</option>
            </select>
          </label>
          {cadence === 'daily' && (
            <label>
              <div className="card-sub">Days (0 = forever)</div>
              <input className="in" type="number" min="0" value={windowDays}
                onChange={(e) => setWindowDays(e.target.value)} style={{ width: 90 }} />
            </label>
          )}
          <button className="btn primary" onClick={saveFreeQuota} disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
        {saved && <div className="status status-ok" style={{ marginTop: 10 }}>{saved}</div>}
        {saveErr && <div className="status status-err" style={{ marginTop: 10 }}>{saveErr}</div>}
      </section>

      {/* 7-day history table */}
      <section className="card">
        <div className="card-label">Last 7 Days — Usage Overview</div>
        {days.length === 0 ? (
          <div className="empty">No usage data yet — requests will appear here once the system is used.</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Day</th>
                <th>Total Requests</th>
                <th>Free</th>
                <th>Pro</th>
                <th>Cache Hits</th>
                <th>Errors</th>
                <th>Avg Latency</th>
                <th>Est. Cost</th>
              </tr>
            </thead>
            <tbody>
              {days.map((d, i) => (
                <tr key={i}>
                  <td>{d.day}</td>
                  <td>{fmtInt(d.total_requests)}</td>
                  <td>{fmtInt(d.free_requests)}</td>
                  <td>{fmtInt(d.pro_requests)}</td>
                  <td>
                    <span className="badge hit">{fmtInt(d.cache_hits)}</span>
                    {d.total_requests > 0 && (
                      <span className="sub"> ({((d.cache_hits / d.total_requests) * 100).toFixed(0)}%)</span>
                    )}
                  </td>
                  <td>
                    {d.errors > 0 ? (
                      <span className="status status-err">{fmtInt(d.errors)}</span>
                    ) : (
                      <span className="status status-ok">0</span>
                    )}
                  </td>
                  <td>{d.avg_latency_ms ? `${d.avg_latency_ms}ms` : '—'}</td>
                  <td>${(d.total_requests * costPerRequest).toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="card-sub note">
          Usage data is aggregated daily. Current day stats update in real-time.
        </div>
      </section>
    </div>
  )
}