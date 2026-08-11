// vidrank API client. All calls are same-origin; vite dev proxy forwards
// /v1 and /admin to the backend (see vite.config.js). Firebase ID token is
// attached as `Authorization: Bearer <token>`.

const TOKEN_KEY = 'vidrank_token'
const ROLE_KEY = 'vidrank_role'
let _token = localStorage.getItem(TOKEN_KEY) || ''
let _role = localStorage.getItem(ROLE_KEY) || 'admin'

// Backend base. Set VITE_API_BACKEND at build time when the dashboard is
// served from a different origin than the backend (Pages). Empty = same-origin
// (vite dev proxy forwards /v1 and /admin locally).
const _BASE = (import.meta.env.VITE_API_BACKEND || 'https://vidrank-backend.fahad288ali.workers.dev').replace(/\/+$/, '')

// ---- admin login (password; optional username => sub-admin login) ----
export const adminLogin = (password, username = '') =>
  _json('/admin/login', 'POST', username ? { username, password } : { password })
export const setToken = (token) => {
  _token = (token || '').trim()
  if (_token) localStorage.setItem(TOKEN_KEY, _token)
  else localStorage.removeItem(TOKEN_KEY)
}
export const setRole = (role) => {
  _role = role === 'sub' ? 'sub' : 'admin'
  localStorage.setItem(ROLE_KEY, _role)
}
export const getRole = () => _role

export function getToken() {
  return _token
}

export function clearToken() {
  _token = ''
  _role = 'admin'
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(ROLE_KEY)
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

async function _req(path, options = {}) {
  const headers = { ...(options.headers || {}) }
  if (_token) headers['Authorization'] = `Bearer ${_token}`
  let resp
  try {
    resp = await fetch(_BASE + path, { ...options, headers })
  } catch {
    throw new ApiError('backend unreachable', 0)
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

const _get = (path) => _req(path)
const _json = (path, method, payload) =>
  _req(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })

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
export const setUserTier = (uid, tier) => _json(`/admin/users/${uid}`, 'PATCH', { tier })
export const setUserStatus = (uid, isActive) => _json(`/admin/users/${uid}`, 'PATCH', { is_active: isActive ? 1 : 0 })
export const approveUser = (uid) => setUserTier(uid, 'pro')
export const resetUserQuota = (uid) => _json(`/admin/users/${uid}/reset-quota`, 'POST')
export const setUserUsage = (uid, usageCount) => _json(`/admin/users/${uid}/set-usage`, 'POST', { usage_count: usageCount })
export const listPlans = () => _get('/admin/plans')
export const updatePlan = (payload) => _json('/admin/plans', 'PATCH', payload)
export const getPricing = () => _get('/admin/pricing')
export const getFreeQuota = () => _get('/admin/free-quota')
export const setFreeQuota = (payload) => _json('/admin/free-quota', 'PUT', payload)

// ---- /admin sub-admins (super admin only) ----
export const listSubAdmins = () => _get('/admin/sub-admins')
export const addSubAdmin = (username, password) => _json('/admin/sub-admins', 'POST', { username, password })
export const updateSubAdmin = (id, payload) => _json(`/admin/sub-admins/${id}`, 'PUT', payload)
export const deleteSubAdmin = (id) => _req(`/admin/sub-admins/${id}`, { method: 'DELETE' })

// ---- /admin stats ----
export const statsOverview = () => _get('/admin/stats/overview')
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
