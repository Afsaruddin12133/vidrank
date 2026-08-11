import { useEffect, useState } from 'react'
import { getToken, getRole, clearToken } from './api.js'
import Login from './pages/Login.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Accounts from './pages/Accounts.jsx'
import Tracing from './pages/Tracing.jsx'
import Users from './pages/Users.jsx'
import SubAdmins from './pages/SubAdmins.jsx'
import Subscriptions from './pages/Subscriptions.jsx'

const TABS = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'accounts', label: 'Accounts' },
  { id: 'tracing', label: 'Tracing / Analytics' },
  { id: 'users', label: 'Users' },
  { id: 'subscriptions', label: 'Subscription Requests' },
]

export default function App() {
  const [token, setTokenState] = useState(getToken())
  const [role, setRoleState] = useState(getRole())
  const isSub = role === 'sub'
  const [tab, setTab] = useState(isSub ? 'users' : 'dashboard')

  useEffect(() => {
    if (isSub && (tab !== 'users' && tab !== 'subscriptions')) {
      setTab('users')
    }
  }, [isSub, tab])

  const logout = () => {
    clearToken()
    setTokenState('')
    setRoleState('admin')
    setTab('dashboard')
  }

  if (!token) {
    return (
      <Login
        onAuthed={() => {
          const r = getRole()
          setTokenState(getToken())
          setRoleState(r)
          setTab(r === 'sub' ? 'users' : 'dashboard')
        }}
      />
    )
  }

  const tabs = isSub
    ? [
        { id: 'users', label: 'Users' },
        { id: 'subscriptions', label: 'Subscription Requests' },
      ]
    : [...TABS, { id: 'subadmins', label: 'Sub Admins' }]

  const activeTab = isSub && tab !== 'subscriptions' ? 'users' : tab

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
              className={`tab ${activeTab === t.id ? 'active' : ''}`}
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
        {!isSub && activeTab === 'dashboard' && <Dashboard />}
        {!isSub && activeTab === 'accounts' && <Accounts />}
        {!isSub && activeTab === 'tracing' && <Tracing />}
        {activeTab === 'users' && <Users />}
        {activeTab === 'subscriptions' && <Subscriptions />}
        {!isSub && activeTab === 'subadmins' && <SubAdmins />}
      </main>
    </div>
  )
}
