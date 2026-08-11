import { useEffect, useState } from 'react'
import { getToken, getRole, clearToken, getAdminUser } from './api.js'
import Login from './pages/Login.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Accounts from './pages/Accounts.jsx'
import Tracing from './pages/Tracing.jsx'
import Users from './pages/Users.jsx'
import SubAdmins from './pages/SubAdmins.jsx'
import Subscriptions from './pages/Subscriptions.jsx'

// SVG Icons matching user's reference dashboard design
function IconDashboard() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
    </svg>
  )
}

function IconUsers() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  )
}

function IconSubscription() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="1" y="4" width="22" height="16" rx="2.5" ry="2.5" />
      <line x1="1" y1="10" x2="23" y2="10" />
    </svg>
  )
}

function IconKey() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="16 18 22 12 16 6" />
      <polyline points="8 6 2 12 8 18" />
    </svg>
  )
}

function IconShield() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  )
}

function IconAnalytics() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  )
}

function IconBell() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  )
}

function IconLogout() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" y1="12" x2="9" y2="12" />
    </svg>
  )
}

function IconMenu() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="3" y1="12" x2="21" y2="12" />
      <line x1="3" y1="6" x2="21" y2="6" />
      <line x1="3" y1="18" x2="21" y2="18" />
    </svg>
  )
}

const TABS = [
  { id: 'dashboard', label: 'Dashboard', icon: IconDashboard },
  { id: 'users', label: 'Users', icon: IconUsers },
  { id: 'subscriptions', label: 'Subscription', icon: IconSubscription },
  { id: 'accounts', label: 'API Key', icon: IconKey },
  { id: 'subadmins', label: 'Admin Management', icon: IconShield },
  { id: 'tracing', label: 'Tracing / Analytics', icon: IconAnalytics },
]

export default function App() {
  const [token, setTokenState] = useState(getToken())
  const [role, setRoleState] = useState(getRole())
  const isSub = role === 'sub'
  const [tab, setTab] = useState(isSub ? 'users' : 'dashboard')
  const [sidebarOpen, setSidebarOpen] = useState(false)

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
        { id: 'users', label: 'Users', icon: IconUsers },
        { id: 'subscriptions', label: 'Subscription', icon: IconSubscription },
      ]
    : TABS

  const activeTab = isSub && tab !== 'subscriptions' ? 'users' : tab
  const activeTabInfo = tabs.find((t) => t.id === activeTab) || tabs[0]

  return (
    <div className="app-container">
      {/* Mobile Drawer Overlay */}
      <div
        className={`sidebar-overlay ${sidebarOpen ? 'open' : ''}`}
        onClick={() => setSidebarOpen(false)}
      />

      {/* Left Sidebar */}
      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-header">
          <div className="sidebar-brand-logo">▷</div>
          <span className="sidebar-brand-text">VidRank</span>
        </div>

        <nav className="sidebar-nav">
          {tabs.map((t) => {
            const Icon = t.icon
            const isActive = activeTab === t.id
            return (
              <button
                key={t.id}
                className={`sidebar-nav-item ${isActive ? 'active' : ''}`}
                onClick={() => {
                  setTab(t.id)
                  setSidebarOpen(false)
                }}
              >
                <Icon />
                <span>{t.label}</span>
              </button>
            )
          })}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-user-card">
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: '50%',
                background: isSub ? '#7c3aed' : '#4f46e5',
                color: '#fff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontWeight: 600,
                fontSize: 13,
                flexShrink: 0,
              }}
            >
              {isSub ? 'S' : 'A'}
            </div>
            <div className="sidebar-user-info">
              <span className="sidebar-user-name">{isSub ? (getAdminUser() !== 'Super Admin' ? getAdminUser() : 'Sub Admin') : 'Super Admin'}</span>
              <span className="sidebar-user-role">{isSub ? 'Sub Admin' : 'Firebase Admin'}</span>
            </div>
            <button className="sidebar-logout-btn" onClick={logout} title="Sign Out">
              <IconLogout />
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="main-wrapper">
        {/* Mobile Top Navigation Bar */}
        <div className="mobile-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div className="sidebar-brand-logo" style={{ width: 28, height: 28, fontSize: 14 }}>▷</div>
            <span className="sidebar-brand-text" style={{ fontSize: 16 }}>VidRank</span>
          </div>
          <button
            className="icon-btn"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            aria-label="Toggle Navigation Menu"
          >
            <IconMenu />
          </button>
        </div>

        {/* Desktop Header */}
        <header className="top-header">
          <div className="top-header-title-group">
            <h1 className="top-header-title">{activeTabInfo.label}</h1>
            <span className="connected-badge">
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#10b981', display: 'inline-block' }} />
              Firebase Realtime Connected
            </span>
          </div>

          <div className="top-header-actions">
            <button className="icon-btn" title="Notifications">
              <IconBell />
            </button>
            <button className="quick-action-btn">
              <span>+ Quick Actions</span>
            </button>
          </div>
        </header>

        <main className="content" style={{ maxWidth: '100%', padding: '24px 28px' }}>
          {!isSub && activeTab === 'dashboard' && <Dashboard />}
          {!isSub && activeTab === 'accounts' && <Accounts />}
          {!isSub && activeTab === 'tracing' && <Tracing />}
          {activeTab === 'users' && <Users />}
          {activeTab === 'subscriptions' && <Subscriptions />}
          {!isSub && activeTab === 'subadmins' && <SubAdmins />}
        </main>
      </div>
    </div>
  )
}
