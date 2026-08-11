import { useState } from 'react'
import { adminLogin, setToken, setRole, ApiError } from '../api.js'

export default function Login({ onAuthed }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState(null)
  const [checking, setChecking] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setErr(null)
    setChecking(true)
    if (!password) {
      setErr('Enter the admin password to continue.')
      setChecking(false)
      return
    }
    try {
      const res = await adminLogin(password, username.trim())
      setToken(res.token)
      setRole(res.role, res.username || username.trim())
      onAuthed()
    } catch (a) {
      if (a instanceof ApiError && (a.status === 401 || a.status === 406)) {
        setErr('Invalid credentials.')
        setPassword('')
      } else if (a instanceof ApiError && a.status === 0) {
        setErr('Backend unreachable. Is the worker / dev proxy running?')
      } else {
        setErr(a.message || 'Failed to log in.')
      }
    } finally {
      setChecking(false)
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <div className="brand login-brand">
          <span className="logo">▣</span> vidrank — router dashboard
        </div>
        <p className="login-sub">
          Admin sign in. Enter the admin password to unlock the control panel.
        </p>
        <form onSubmit={submit}>
          <label className="field">
            <span>Username (sub-admin only)</span>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="leave blank for super admin"
              disabled={checking}
            />
          </label>
          <label className="field">
            <span>Admin password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              disabled={checking}
              autoFocus
            />
          </label>
          {err && <div className="error">{err}</div>}
          <button className="btn primary" type="submit" disabled={checking}>
            {checking ? 'Logging in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}