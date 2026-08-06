import { useEffect, useState } from 'react'

import logo from '../assets/logo.png'
import './Popup.css'

// Login is delegated to the background service worker (the single Firebase auth
// owner). Each extension page used to create its OWN Firebase app instance, but
// auth sessions are keyed per app name in IndexedDB ("firebase:authUser:<apiKey>:<appName>"),
// so the background could never see a popup-side session -> NOT_LOGGED_IN.
type Settings = {
  autoInsert: boolean
  hashtagMode: boolean
  maxTagsCount: number
  preferredSeparator: string
}

type LoginStage = 'opening' | null

const GOOGLE_ICON = (
  <svg width="18" height="18" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <path
      d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
      fill="#4285F4"
    />
    <path
      d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
      fill="#34A853"
    />
    <path
      d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
      fill="#FBBC05"
    />
    <path
      d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
      fill="#EA4335"
    />
  </svg>
)

export const Popup = () => {
  const [isLoggedIn, setIsLoggedIn] = useState(false)
  const [settings, setSettings] = useState<Settings>({
    autoInsert: true,
    hashtagMode: false,
    maxTagsCount: 35,
    preferredSeparator: ',',
  })
  const [loginStage, setLoginStage] = useState<LoginStage>(null)
  const [loginError, setLoginError] = useState('')

  useEffect(() => {
    chrome.storage.local.get({ isLoggedIn: false }, (data) => {
      setIsLoggedIn(data.isLoggedIn)
    })

    chrome.storage.sync.get(
      {
        autoGenerate: true,
        autoInsert: true,
        hashtagMode: false,
        maxTagsCount: 35,
        preferredSeparator: ',',
      },
      (s) => {
        setSettings({
          autoInsert: s.autoInsert,
          hashtagMode: s.hashtagMode,
          maxTagsCount: s.maxTagsCount,
          preferredSeparator: s.preferredSeparator,
        })
      },
    )
  }, [])

  // ─── Handle Login ───────────────────────────────────────────────────────────
  const handleLogin = () => {
    setLoginError('')
    setLoginStage('opening')

    chrome.runtime.sendMessage({ action: 'login' }, (response) => {
      setLoginStage(null)
      if (response && response.success) {
        setIsLoggedIn(true)
      } else {
        setLoginError((response && response.error) || 'Sign-in failed.')
      }
    })
  }

  const handleLogout = (e: React.MouseEvent) => {
    e.preventDefault()
    chrome.runtime.sendMessage({ action: 'logout' }, (response) => {
      if (response && response.success) {
        setIsLoggedIn(false)
      }
    })
  }

  const saveSetting = (patch: Partial<Settings>) => {
    setSettings((s) => ({ ...s, ...patch }))
    chrome.storage.sync.set(patch)
  }

  return (
    <div className="popup-container">
      {/* Header */}
      <header className="popup-header">
        <div className="logo-area">
          <img src={logo} width="24" height="24" alt="VidRank Logo" />
          <h1>VidRank</h1>
          <p style={{ fontSize: 10, color: '#aaaaaa', margin: '4px 0 0 0' }}>
            Optimize Every Video. Unlock Better YouTube Rankings.
          </p>
        </div>
        <a
          href="https://studio.youtube.com"
          target="_blank"
          rel="noreferrer"
          className="studio-link"
          title="Open YouTube Studio"
        >
          Studio ↗
        </a>
      </header>

      {/* Login View */}
      {!isLoggedIn ? (
        <main className="popup-main" style={{ textAlign: 'center', padding: '40px 20px' }}>
          <h2 style={{ marginBottom: 20, color: 'white' }}>Welcome to VidRank</h2>
          <p style={{ color: '#aaaaaa', marginBottom: 30 }}>
            Please sign in with Google to optimize your videos.
          </p>
          <button
            id="btn-google-login"
            onClick={handleLogin}
            disabled={loginStage !== null}
            style={{
              background: 'white',
              color: 'black',
              borderRadius: 8,
              padding: 12,
              width: '100%',
              border: 'none',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              justifyContent: 'center',
              alignItems: 'center',
              gap: 10,
              fontFamily: "'Outfit', sans-serif",
              fontSize: 14,
              opacity: loginStage !== null ? 0.7 : 1,
            }}
          >
            {GOOGLE_ICON}
            {loginStage === 'opening' ? 'Opening Google sign-in...' : 'Sign in with Google'}
          </button>
          {loginError && <div style={{ color: '#ff4444', marginTop: 15, fontSize: 12 }}>{loginError}</div>}
        </main>
      ) : (
        /* Settings Forms */
        <main className="popup-main">
          <section className="settings-section">
            <h2>Global Settings</h2>

            <div className="setting-item">
              <div className="setting-details">
                <span className="setting-title">Auto Insert</span>
                <span className="setting-desc">Insert tags directly into Tags input</span>
              </div>
              <label className="switch">
                <input
                  type="checkbox"
                  id="popup-toggle-insert"
                  checked={settings.autoInsert}
                  onChange={(e) => saveSetting({ autoInsert: e.target.checked })}
                />
                <span className="slider"></span>
              </label>
            </div>

            <div className="setting-item">
              <div className="setting-details">
                <span className="setting-title">Hashtag Mode</span>
                <span className="setting-desc">Remove spaces and prepend # to tags</span>
              </div>
              <label className="switch">
                <input
                  type="checkbox"
                  id="popup-toggle-hashtag"
                  checked={settings.hashtagMode}
                  onChange={(e) => saveSetting({ hashtagMode: e.target.checked })}
                />
                <span className="slider"></span>
              </label>
            </div>

            <div className="setting-item">
              <div className="setting-details">
                <span className="setting-title">Preferred Separator</span>
                <span className="setting-desc">Separation delimiter when copying</span>
              </div>
              <select
                id="popup-select-separator"
                className="form-select"
                value={settings.preferredSeparator}
                onChange={(e) => saveSetting({ preferredSeparator: e.target.value })}
              >
                <option value=",">Comma ( , )</option>
                <option value=";">Semicolon ( ; )</option>
                <option value={'\\n'}>Newline (Enter)</option>
              </select>
            </div>

            <div className="setting-item-column">
              <div className="setting-details-row">
                <span className="setting-title">Max Tag Count</span>
                <span className="setting-value" id="popup-tags-count-val">
                  {settings.maxTagsCount}
                </span>
              </div>
              <input
                type="range"
                id="popup-slider-tags-count"
                min="20"
                max="50"
                value={settings.maxTagsCount}
                onChange={(e) => saveSetting({ maxTagsCount: parseInt(e.target.value, 10) })}
                className="form-slider"
              />
            </div>
          </section>
        </main>
      )}

      {/* Footer */}
      <footer className="popup-footer">
        <span>Powered by VidRank</span>
        {isLoggedIn && (
          <a
            id="btn-logout"
            href="#"
            onClick={handleLogout}
            style={{ color: '#ff4444', textDecoration: 'none', fontSize: 12 }}
          >
            Sign Out
          </a>
        )}
      </footer>
    </div>
  )
}

export default Popup
