// vidrank API client. All calls are same-origin; vite dev proxy forwards
// /v1 and /admin to the backend (see vite.config.js). Firebase ID token is
// attached as `Authorization: Bearer <access_token>`.
//
// Auth pattern (two-token):
//   access_token  — HS256 JWT, 15 min TTL, kept in JS memory (never localStorage).
//                   Sent as Authorization: Bearer header on every admin API call.
//   refresh_token — HS256 JWT, 8 h TTL, stored ONLY in httpOnly Secure cookie
//                   managed by the server. Never readable by JS.
//                   Used by /admin/refresh to silently issue a new access_token.

const ROLE_KEY = 'vidrank_role'
const USER_KEY = 'vidrank_user'

// Access token lives ONLY in module memory — cleared on page refresh (intentional;
// /admin/login GET restores it silently via the httpOnly refresh cookie).
let _accessToken = ''
let _role = localStorage.getItem(ROLE_KEY) || 'admin'

// Backend base URL. Dev: same-origin (vite proxy forwards /v1 & /admin to local backend).
// Production: deployed worker URL (or VITE_API_BACKEND override).
const _BASE = (import.meta.env.VITE_API_BACKEND || (import.meta.env.DEV ? '' : 'https://vidrank-backend.fahad288ali.workers.dev')).replace(/\/+$/, '')

// ---- token memory helpers (no localStorage for access token) ----
export function setToken(token) {
  _accessToken = (token || '').trim()
}

export function getToken() {
  return _accessToken
}

export function setRole(role, username = '') {
  _role = role === 'sub' ? 'sub' : 'admin'
  localStorage.setItem(ROLE_KEY, _role)
  if (username) {
    localStorage.setItem(USER_KEY, username)
  } else {
    localStorage.removeItem(USER_KEY)
  }
}

export const getRole = () => _role

export const getAdminUser = () => {
  const saved = localStorage.getItem(USER_KEY)
  if (saved) return saved
  return _role === 'sub' ? 'Sub Admin' : 'Super Admin'
}

export function clearToken() {
  _accessToken = ''
  _role = 'admin'
  localStorage.removeItem(ROLE_KEY)
  localStorage.removeItem(USER_KEY)
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

// ---- internal fetch helpers ------------------------------------------------

// _refreshing prevents concurrent refresh storms
let _refreshing = null

async function _tryRefresh() {
  if (_refreshing) return _refreshing
  _refreshing = (async () => {
    try {
      const resp = await fetch(_BASE + '/admin/refresh', {
        method: 'POST',
        credentials: 'include',   // send httpOnly refresh cookie
      })
      if (!resp.ok) return false
      const data = await resp.json()
      if (data.access_token) {
        _accessToken = data.access_token
        // Sync role if server echoed it
        if (data.role) {
          _role = data.role === 'sub' ? 'sub' : 'admin'
          localStorage.setItem(ROLE_KEY, _role)
        }
        return true
      }
      return false
    } catch {
      return false
    } finally {
      _refreshing = null
    }
  })()
  return _refreshing
}

/**
 * Core fetch wrapper. Attaches access token, auto-refreshes once on 401.
 * @param {string} path
 * @param {RequestInit} options
 * @param {boolean} withCookie  — set true for cookie-touching endpoints
 */
async function _req(path, options = {}, withCookie = false) {
  const headers = { ...(options.headers || {}) }
  if (_accessToken) headers['Authorization'] = `Bearer ${_accessToken}`

  const fetchOpts = {
    ...options,
    headers,
    ...(withCookie ? { credentials: 'include' } : {}),
  }

  let resp
  try {
    resp = await fetch(_BASE + path, fetchOpts)
  } catch {
    throw new ApiError('backend unreachable', 0)
  }

  // Silently refresh on 401 and retry once
  if (resp.status === 401 && !withCookie) {
    const refreshed = await _tryRefresh()
    if (refreshed) {
      headers['Authorization'] = `Bearer ${_accessToken}`
      try {
        resp = await fetch(_BASE + path, { ...fetchOpts, headers })
      } catch {
        throw new ApiError('backend unreachable', 0)
      }
    }
  }

  let body = null
  try {
    body = await resp.json()
  } catch {
    /* non-JSON body */
  }
  if (!resp.ok) {
    const msg = (body && body.error) || `HTTP ${resp.status}`
    throw new ApiError(msg, resp.status)
  }
  return body
}

const _get  = (path) => _req(path)
const _json = (path, method, payload) =>
  _req(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
// cookie-touching variant (credentials: include)
const _cookiePost = (path, payload) =>
  _req(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }, true)

// ---- auth API calls --------------------------------------------------------

/** Login — POST /admin/login with credentials:include so server can set cookie */
export async function adminLogin(password, username = '') {
  const body = username ? { username, password } : { password }
  const data = await _req(
    '/admin/login',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) },
    true, // credentials: include → server sets admin_refresh cookie
  )
  // Store access_token in memory; refresh_token is in the httpOnly cookie.
  if (data.access_token) {
    _accessToken = data.access_token
  }
  return data  // { ok, access_token, role, username? }
}

/** Logout — clears server-side cookie and wipes local access token */
export async function adminLogout() {
  try {
    await _req('/admin/logout', { method: 'POST' }, true)
  } catch {
    // ignore network errors on logout
  }
  clearToken()
}

/** Restore session after page reload via GET /admin/login + refresh cookie */
export async function restoreSession() {
  try {
    const resp = await fetch(_BASE + '/admin/login', { credentials: 'include' })
    if (!resp.ok) return null
    const data = await resp.json()
    if (data.access_token) {
      _accessToken = data.access_token
      if (data.role) {
        _role = data.role === 'sub' ? 'sub' : 'admin'
        localStorage.setItem(ROLE_KEY, _role)
      }
      if (data.username) localStorage.setItem(USER_KEY, data.username)
    }
    return data  // { ok, access_token, role, username? }
  } catch {
    return null
  }
}

// ---- /v1 user endpoints ----
export const getMe = () => _get('/v1/me')
export const getHistory = (limit = 50) => _get(`/v1/history?limit=${limit}`)

// ---- /admin accounts ----
export const listAccounts = () => _get('/admin/accounts')
export const listAllAccounts = () => _get('/admin/accounts/all')
export const addAccount = (payload) => _json('/admin/accounts', 'POST', payload)
export const updateAccount = (id, payload) => _json(`/admin/accounts/${id}`, 'PUT', payload)
export const deleteAccount = (id) => _req(`/admin/accounts/${id}`, { method: 'DELETE' })
export const accountHealth = () => _get('/admin/accounts/health')
export const accountUsage = (id) => _get(`/admin/accounts/${id}/usage`)
export const accountsUsageDay = (days = 7) => _get(`/admin/accounts/usage?days=${days}`)
export const accountsUsagePaged = ({ days = 7, q = '', provider = '', page = 1, pageSize = 10 } = {}) => {
  const p = new URLSearchParams()
  p.set('days', days)
  if (q) p.set('q', q)
  if (provider && provider !== 'all') p.set('provider', provider)
  p.set('page', page)
  p.set('page_size', pageSize)
  return _get(`/admin/accounts/usage/paged?${p}`)
}


// ---- /admin users & plans ----
export const listUsers = (tier) => _get(tier ? `/admin/users?tier=${tier}` : '/admin/users')
export const listUsersPaged = ({ q = '', tier = '', page = 1, pageSize = 25 } = {}) => {
  const p = new URLSearchParams()
  if (q) p.set('q', q)
  if (tier) p.set('tier', tier)
  p.set('page', page)
  p.set('page_size', pageSize)
  return _get(`/admin/users/paged?${p}`)
}
export function recordLocalSubActivity(action, targetUid, targetEmail, details) {
  try {
    const role = getRole()
    if (role !== 'sub') return
    const subUsername = localStorage.getItem('vidrank_sub_username') || 'Sub-Admin'
    const item = {
      id: `act-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      sub_admin_username: subUsername,
      action,
      target_uid: targetUid,
      target_email: targetEmail || targetUid,
      details: details ? JSON.stringify(details) : null,
      created_at: Math.floor(Date.now() / 1000),
    }
    const current = JSON.parse(localStorage.getItem('vidrank_sub_activity_logs') || '[]')
    current.unshift(item)
    localStorage.setItem('vidrank_sub_activity_logs', JSON.stringify(current.slice(0, 500)))
  } catch {
    /* ignore storage errors */
  }
}

export const setUserTier = (uid, tier, targetEmail = '', options = {}) => {
  const { durationDays = 30, addBalance = false, amount = 499 } = options
  const details = {
    tier: { from: 'free/pro', to: tier },
  }
  if (tier === 'pro') {
    details.duration_days = durationDays
    if (addBalance) details.added_balance = amount
  }
  recordLocalSubActivity('set_user', uid, targetEmail, details)

  return _json(`/admin/users/${uid}`, 'PATCH', {
    tier,
    duration_days: durationDays,
    add_balance: addBalance,
    amount,
  })
}
export const setUserStatus = (uid, isActive, targetEmail = '') => {
  recordLocalSubActivity('set_user', uid, targetEmail, { is_active: { to: isActive ? 1 : 0 } })
  return _json(`/admin/users/${uid}`, 'PATCH', { is_active: isActive ? 1 : 0 })
}
export const approveUser = (uid, targetEmail = '') => setUserTier(uid, 'pro', targetEmail)
export const makeUserFree = (uid, targetEmail = '') => {
  recordLocalSubActivity('set_user', uid, targetEmail, { tier: { to: 'free' } })
  return _json(`/admin/users/${uid}`, 'PATCH', { tier: 'free', force: true })
}
export const resetUserQuota = (uid, targetEmail = '') => {
  recordLocalSubActivity('reset_quota', uid, targetEmail)
  return _json(`/admin/users/${uid}/reset-quota`, 'POST')
}
export const setUserUsage = (uid, usageCount, targetEmail = '') => {
  recordLocalSubActivity('set_usage', uid, targetEmail, { usage_count: usageCount })
  return _json(`/admin/users/${uid}/set-usage`, 'POST', { usage_count: usageCount })
}
export const listPlans = () => _get('/admin/plans')
export const updatePlan = (payload) => _json('/admin/plans', 'PATCH', payload)
export const getPricing = () => _get('/admin/pricing')
export const getFreeQuota = () => _get('/admin/free-quota')
export const setFreeQuota = (payload) => _json('/admin/free-quota', 'PUT', payload)

export const listSubscriptions = () => _get('/admin/subscriptions')
export const approveSubscription = (subId) => _json(`/admin/subscriptions/${subId}/approve`, 'POST')
export const rejectSubscription = (subId) => _json(`/admin/subscriptions/${subId}/reject`, 'POST')

// ---- /admin sub-admins (super admin only) ----
export const listSubAdmins = () => _get('/admin/sub-admins')
export const addSubAdmin = (username, password) => _json('/admin/sub-admins', 'POST', { username, password })
export const updateSubAdmin = (id, payload) => _json(`/admin/sub-admins/${id}`, 'PUT', payload)
export const deleteSubAdmin = (id) => _req(`/admin/sub-admins/${id}`, { method: 'DELETE' })
export const listSubAdminActivity = (limit = 100) => _get(`/admin/sub-admins/activity?limit=${limit}`)
export const listSubAdminActivityPaged = ({ q = '', subAdmin = '', page = 1, pageSize = 25 } = {}) => {
  const p = new URLSearchParams()
  if (q) p.set('q', q)
  if (subAdmin && subAdmin !== 'all') p.set('sub_admin', subAdmin)
  p.set('page', page)
  p.set('page_size', pageSize)
  return _get(`/admin/sub-admins/activity/paged?${p}`)
}


// ---- /admin stats ----
export const statsOverview = () => _get('/admin/stats/overview')
export const statsLatency = (hours = 24) => _get(`/admin/stats/latency?hours=${hours}`)
export const statsUsage = (days = 7) => _get(`/admin/stats/usage?days=${days}`)

// ---- /admin geo ----
export const adminGeo = (days = 30) => _get(`/admin/geo?days=${days}`)

// ---- formatting helpers (shared) ----
export const fmtInt = (n) => (n == null || isNaN(n) ? '—' : Number(n).toLocaleString('en-US'))
export const fmtPct = (n) => (n == null || isNaN(n) ? '—' : `${(n * 100).toFixed(1)}%`)
export const fmtDur = (sec) => {
  if (sec == null || isNaN(sec) || sec < 0) return '—'
  if (sec < 60) return `${Math.round(sec)}s`
  if (sec < 3600) return `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s`
  return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`
}
export const fmtClock = (ts) => {
  if (!ts) return '—'
  const d = new Date(ts * 1000)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleTimeString('en-US', { hour12: false })
}
