// vidrank API client. All calls are same-origin; vite dev proxy forwards
// /v1 and /admin to the backend (see vite.config.js). Firebase ID token is
// attached as `Authorization: Bearer <token>`.

const TOKEN_KEY = 'vidrank_token'
let _token = localStorage.getItem(TOKEN_KEY) || ''

// Backend base. Set VITE_API_BACKEND at build time when the dashboard is
// served from a different origin than the backend (Pages). Empty = same-origin
// (vite dev proxy forwards /v1 and /admin locally).
const _BASE = (import.meta.env.VITE_API_BACKEND || '').replace(/\/+$/, '')

// ---- admin login (password) ----
export const adminLogin = (password) => _json('/admin/login', 'POST', { password })
export const setToken = (token) => {
  _token = (token || '').trim()
  if (_token) localStorage.setItem(TOKEN_KEY, _token)
  else localStorage.removeItem(TOKEN_KEY)
}

export function getToken() {
  return _token
}

export function clearToken() {
  _token = ''
  localStorage.removeItem(TOKEN_KEY)
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

// ---- /admin users & plans ----
export const listUsers = (tier) => _get(tier ? `/admin/users?tier=${tier}` : '/admin/users')
export const setUserTier = (uid, tier) => _json(`/admin/users/${uid}`, 'PATCH', { tier })
export const listPlans = () => _get('/admin/plans')
export const updatePlan = (payload) => _json('/admin/plans', 'PATCH', payload)
export const getPricing = () => _get('/admin/pricing')

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
