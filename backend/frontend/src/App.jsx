import { useCallback, useEffect, useRef, useState } from 'react'
import { getToken, getRole, clearToken } from './api.js'
import Login from './pages/Login.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Accounts from './pages/Accounts.jsx'
import Tracing from './pages/Tracing.jsx'
import Users from './pages/Users.jsx'
import SubAdmins from './pages/SubAdmins.jsx'

const TABS = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'accounts', label: 'Accounts' },
  { id: 'tracing', label: 'Tracing / Analytics' },
  { id: 'users', label: 'Users' },
]

export default function App() {
  const [token, setTokenState] = useState(getToken())
  const [role, setRoleState] = useState(getRole())
  const [tab, setTab] = useState('dashboard')

  const logout = () => {
    clearToken()
    setTokenState('')
    setRoleState('admin')
    setTab('dashboard')
  }

  if (!token) {
    return <Login onAuthed={() => { setTokenState(getToken()); setRoleState(getRole()) }} />
  }

  const isSub = role === 'sub'
  const tabs = isSub
    ? TABS.filter((t) => t.id === 'users')
    : [...TABS, { id: 'subadmins', label: 'Sub Admins' }]

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">▣</span> vidrank
          <span className={`tier-pill ${isSub ? 'tier-free' : 'tier-admin'}`}>
            {isSub ? 'sub-admin' : 'admin'}
          </span>
        </div>
        <nav className="tabs">
          {tabs.map((t) => (
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
        {tab === 'subadmins' && <SubAdmins />}
      </main>
    </div>
  )
}
