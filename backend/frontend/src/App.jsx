import { useCallback, useEffect, useRef, useState } from 'react'
import { getToken, clearToken } from './api.js'
import Login from './pages/Login.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Accounts from './pages/Accounts.jsx'
import Tracing from './pages/Tracing.jsx'
import Users from './pages/Users.jsx'

const TABS = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'accounts', label: 'Accounts' },
  { id: 'tracing', label: 'Tracing / Analytics' },
  { id: 'users', label: 'Users' },
]

export default function App() {
  const [token, setTokenState] = useState(getToken())
  const [tab, setTab] = useState('dashboard')

  const logout = () => {
    clearToken()
    setTokenState('')
    setTab('dashboard')
  }

  if (!token) {
    return <Login onAuthed={() => setTokenState(getToken())} />
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">▣</span> vidrank
          <span className="tier-pill tier-admin">admin</span>
        </div>
        <nav className="tabs">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={`tab ${tab === t.id ? 'active' : ''}`}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </nav>
        <div className="topbar-right">
          <button className="btn ghost" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>
      <main className="content">
        {tab === 'dashboard' && <Dashboard />}
        {tab === 'accounts' && <Accounts />}
        {tab === 'tracing' && <Tracing />}
        {tab === 'users' && <Users />}
      </main>
    </div>
  )
}
