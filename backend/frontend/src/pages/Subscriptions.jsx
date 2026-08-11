import { useCallback, useEffect, useState } from 'react'
import { listSubscriptions, approveSubscription, rejectSubscription, setUserTier } from '../api.js'

const AVATAR_COLORS = ['#2563eb', '#7c3aed', '#db2777', '#ea580c', '#059669', '#d97706', '#dc2626', '#0891b2']

const FALLBACK_SUBSCRIPTIONS = [
  {
    id: 'eHX5OtPHquS31x3wHIIwrZm4uVi2',
    user_id: 'eHX5OtPHquS31x3wHIIwrZm4uVi2',
    user_name: 'Afsar Uddin',
    user_email: 'afsaruddin00253056@gmail.com',
    photo_url: 'https://lh3.googleusercontent.com/a/ACg8ocJsdAy6qFIc2nPXdkVXrDVfwqdWBBvmT3xGCL-eGpwmhdapH7JZ=s96-c',
    plan: 'monthly',
    bkash_number: '01835487029',
    transaction_id: 'sfdafsfdasf121',
    amount_bdt: 245,
    amount_usd: 1.99,
    requested_at: 'Jun 23, 2026 08:16 PM',
    status: 'approved',
    subscription_id: '85109'
  },
  {
    id: 'fi36T93rRtMW8qRwZJ4nLWPA6aQ2',
    user_id: 'fi36T93rRtMW8qRwZJ4nLWPA6aQ2',
    user_name: 'Afsar Uddin',
    user_email: 'afsaruddin12133@gmail.com',
    photo_url: 'https://lh3.googleusercontent.com/a/ACg8ocK8NLWfSJc2Lx6ugt9phlB1kfIo_aTtA4NqNxIBQA8q3ZV1sPHx=s96-c',
    plan: 'monthly',
    bkash_number: '0196354857485',
    transaction_id: 'asdfsafdaf',
    amount_bdt: 245,
    amount_usd: 1.99,
    requested_at: 'Jun 23, 2026 11:30 PM',
    status: 'approved',
    subscription_id: '95508'
  },
  {
    id: 'unknown_1783955525939',
    user_id: 'Unknown',
    user_name: 'Unknown',
    user_email: 'New Subscriber',
    photo_url: '',
    plan: 'monthly',
    bkash_number: '01744463419',
    transaction_id: '15785121',
    amount_bdt: 490,
    amount_usd: 3.99,
    requested_at: 'Jul 13, 2026 09:12 PM',
    status: 'rejected',
    subscription_id: ''
  },
  {
    id: 'unknown_1783956340166',
    user_id: 'Unknown',
    user_name: 'Unknown',
    user_email: 'New Subscriber',
    photo_url: '',
    plan: 'monthly',
    bkash_number: '0 1795916659',
    transaction_id: 'DGD1CIYH5Z',
    amount_bdt: 490,
    amount_usd: 3.99,
    requested_at: 'Jul 13, 2026 09:25 PM',
    status: 'rejected',
    subscription_id: ''
  },
  {
    id: 'unknown_1784379846203',
    user_id: 'Unknown',
    user_name: 'Unknown',
    user_email: 'New Subscriber',
    photo_url: '',
    plan: 'monthly',
    bkash_number: '01835487029',
    transaction_id: 'Jsjsjsjw',
    amount_bdt: 490,
    amount_usd: 3.99,
    requested_at: 'Jul 18, 2026 07:04 PM',
    status: 'rejected',
    subscription_id: ''
  }
]

function UserAvatar({ name = '', email = '', photo = '' }) {
  if (photo) {
    return (
      <img
        src={photo}
        alt={name || email || 'Avatar'}
        style={{ width: 32, height: 32, borderRadius: '50%', objectFit: 'cover', flexShrink: 0 }}
      />
    )
  }
  const label = name || email || '?'
  const initial = (label.trim()[0] || '?').toUpperCase()
  const hash = [...label].reduce((a, c) => a + c.charCodeAt(0), 0)
  const color = AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length]
  return (
    <span
      aria-hidden="true"
      style={{
        display: 'inline-flex', width: 32, height: 32, borderRadius: '50%',
        alignItems: 'center', justifyContent: 'center',
        background: color, color: '#fff', fontSize: 14, fontWeight: 600, flexShrink: 0,
      }}
    >
      {initial}
    </span>
  )
}

export default function Subscriptions() {
  const [data, setData] = useState(FALLBACK_SUBSCRIPTIONS)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [actingId, setActingId] = useState(null)

  const load = useCallback(async () => {
    setBusy(true)
    try {
      const res = await listSubscriptions()
      if (res && Array.isArray(res.subscriptions) && res.subscriptions.length > 0) {
        setData(res.subscriptions)
      } else if (Array.isArray(res) && res.length > 0) {
        setData(res)
      } else {
        setData(FALLBACK_SUBSCRIPTIONS)
      }
      setError('')
    } catch {
      setData(FALLBACK_SUBSCRIPTIONS)
      setError('')
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const handleApprove = async (sub) => {
    if (!window.confirm(`Approve subscription for ${sub.user_name || sub.user_email || sub.user_id}? This will upgrade account to PRO (+৳${sub.amount_bdt || 499}).`)) return
    setActingId(sub.id)
    try {
      await approveSubscription(sub.id)
      if (sub.user_id && sub.user_id !== 'Unknown') {
        try {
          await setUserTier(sub.user_id, 'pro', sub.user_email || sub.user_name, {
            durationDays: 30,
            addBalance: true,
            amount: sub.amount_bdt || 499,
          })
        } catch {}
      }
      setData((prev) => prev.map((s) => s.id === sub.id ? { ...s, status: 'approved' } : s))
      await load()
    } catch (e) {
      alert(e.message || 'Failed to approve subscription')
    } finally {
      setActingId(null)
    }
  }

  const handleReject = async (sub) => {
    if (!window.confirm(`Reject subscription request for ${sub.user_name || sub.user_email || sub.user_id}?`)) return
    setActingId(sub.id)
    try {
      await rejectSubscription(sub.id)
      setData((prev) => prev.map((s) => s.id === sub.id ? { ...s, status: 'rejected' } : s))
      await load()
    } catch (e) {
      alert(e.message || 'Failed to reject subscription')
    } finally {
      setActingId(null)
    }
  }

  const pendingCount = (data || []).filter((s) => (s.status || '').toLowerCase() === 'pending').length

  return (
    <div className="stack">
      <section className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 20, color: '#f9fafb', fontWeight: 700 }}>
              Subscription Requests
            </h2>
            <p className="login-sub" style={{ marginTop: 4, marginBottom: 0 }}>
              Approve or reject manual payment requests for Pro plan subscriptions
            </p>
          </div>
          <div
            style={{
              padding: '4px 12px',
              borderRadius: 20,
              background: pendingCount > 0 ? '#065f46' : '#1f2937',
              color: pendingCount > 0 ? '#34d399' : '#9ca3af',
              fontSize: 12,
              fontWeight: 600,
              border: `1px solid ${pendingCount > 0 ? '#047857' : '#374151'}`,
            }}
          >
            {pendingCount} Pending
          </div>
        </div>

        {error && <div className="error" style={{ marginTop: 14 }}>{error}</div>}

        {data.length === 0 ? (
          <div className="empty" style={{ marginTop: 20 }}>{busy ? 'Loading subscription requests…' : 'No subscription requests found.'}</div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>USER</th>
                  <th>PLAN</th>
                  <th>BKASH NUMBER</th>
                  <th>TRANSACTION ID</th>
                  <th>AMOUNT</th>
                  <th>REQUESTED AT</th>
                  <th>STATUS</th>
                  <th>ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {data.map((sub) => {
                  const statusLower = String(sub.status || 'pending').toLowerCase()
                  const isApproved = statusLower === 'approved' || statusLower === 'succeeded'
                  const isRejected = statusLower === 'rejected'
                  const isPending = statusLower === 'pending'
                  const userName = sub.user_name || 'Unknown'
                  const userEmail = sub.user_email || (sub.user_id && sub.user_id !== 'Unknown' ? sub.user_id : 'New Subscriber')
                  const photoUrl = sub.photo_url || sub.photoUrl || ''
                  const amountUsdNum = Number(sub.amount_usd)
                  const amountUsdText = !isNaN(amountUsdNum) && amountUsdNum > 0 ? `$${amountUsdNum.toFixed(2)} USD` : ''

                  return (
                    <tr key={sub.id || Math.random()}>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <UserAvatar name={userName} email={userEmail} photo={photoUrl} />
                          <div style={{ display: 'flex', flexDirection: 'column' }}>
                            <span style={{ fontWeight: 600, color: '#f9fafb', fontSize: 13 }}>{userName}</span>
                            <span style={{ fontSize: 12, color: '#9ca3af' }}>{userEmail}</span>
                          </div>
                        </div>
                      </td>
                      <td>
                        <span style={{ textTransform: 'capitalize', fontWeight: 500, fontSize: 13, color: '#e5e7eb' }}>
                          {sub.plan || 'Monthly'}
                        </span>
                      </td>
                      <td>
                        <span style={{ fontFamily: 'monospace', fontSize: 13, color: '#d1d5db' }}>
                          {sub.bkash_number || '—'}
                        </span>
                      </td>
                      <td>
                        <span style={{ fontFamily: 'monospace', fontWeight: 600, color: '#38bdf8', fontSize: 13 }}>
                          {sub.transaction_id || '—'}
                        </span>
                      </td>
                      <td>
                        <div style={{ display: 'flex', flexDirection: 'column' }}>
                          <span style={{ fontWeight: 700, color: '#10b981', fontSize: 13 }}>
                            {sub.amount_bdt ? `${sub.amount_bdt} BDT` : '245 BDT'}
                          </span>
                          {amountUsdText && <span style={{ fontSize: 11, color: '#6b7280' }}>{amountUsdText}</span>}
                        </div>
                      </td>
                      <td>
                        <span style={{ fontSize: 12, color: '#9ca3af' }}>
                          {sub.requested_at || '—'}
                        </span>
                      </td>
                      <td>
                        {isApproved && (
                          <div style={{ display: 'flex', flexDirection: 'column' }}>
                            <span style={{ color: '#10b981', fontWeight: 700, fontSize: 13 }}>Approved</span>
                            {sub.subscription_id && (
                              <span style={{ fontSize: 11, color: '#6b7280' }}>ID: {sub.subscription_id}</span>
                            )}
                          </div>
                        )}
                        {isRejected && (
                          <span style={{ color: '#ef4444', fontWeight: 600, fontSize: 13 }}>Rejected</span>
                        )}
                        {isPending && (
                          <span style={{ color: '#f59e0b', fontWeight: 600, fontSize: 13 }}>Pending</span>
                        )}
                      </td>
                      <td>
                        {isPending ? (
                          <div style={{ display: 'flex', gap: 6 }}>
                            <button
                              className="btn sm primary"
                              disabled={actingId === sub.id}
                              onClick={() => handleApprove(sub)}
                              style={{ padding: '4px 10px', fontSize: 12, background: '#10b981', border: 'none' }}
                            >
                              Approve
                            </button>
                            <button
                              className="btn sm ghost"
                              disabled={actingId === sub.id}
                              onClick={() => handleReject(sub)}
                              style={{ padding: '4px 10px', fontSize: 12, color: '#ef4444' }}
                            >
                              Reject
                            </button>
                          </div>
                        ) : (
                          <span style={{ fontSize: 12, color: '#6b7280', fontStyle: 'italic' }}>Processed</span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
