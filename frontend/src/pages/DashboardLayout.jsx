import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { API_BASE_URL, apiFetch } from '../api/client'

const navigation = [
  { path: '/chat', label: 'Chat', icon: '◉', detail: 'Continue your conversation' },
  { path: '/preferences', label: 'My Preferences', icon: '♡', detail: 'Manage memory preferences' },
  { path: '/search', label: 'Search Music', icon: '⌕', detail: 'Browse artists and tracks' },
  { path: '/recommendations', label: 'Recommendations', icon: '♫', detail: 'Picked from your memories' },
  { path: '/memory-search', label: 'View Memories', icon: '▤', detail: 'Search and manage memories' },
  { path: '/memory-settings', label: 'Memory Settings', icon: '⚙', detail: 'Control personalization' },
  { path: '/profile', label: 'My Profile', icon: '◎', detail: 'Account details' },
]
function DashboardLayout({ session, logout }) {
  const location = useLocation()
  const navigate = useNavigate()
  const activePage = navigation.find((page) => page.path === location.pathname)
  const consentKey = `spotify_ai_memory_consent_${session.subject_id}`
  const consentStateKey = `spotify_ai_consent_state_${session.subject_id}`
  const [consentState, setConsentState] = useState(() => localStorage.getItem(consentStateKey) || (localStorage.getItem(consentKey) === 'true' ? 'opted_in' : 'opted_out'))
  const [consentLoading, setConsentLoading] = useState(false)
  const [consentError, setConsentError] = useState('')
  const [logoutError, setLogoutError] = useState('')
  const [profileMenuOpen, setProfileMenuOpen] = useState(false)
  useEffect(() => {
    let cancelled = false
    apiFetch('/v1/memory/control').then((result) => {
      if (cancelled || !result?.current_state) return
      const nextState = String(result.current_state).toLowerCase()
      setConsentState(nextState)
      localStorage.setItem(consentStateKey, nextState)
      localStorage.setItem(consentKey, nextState === 'opted_in' ? 'true' : 'false')
    }).catch(() => {})
    return () => { cancelled = true }
  }, [consentKey, consentStateKey])
  const memoryConsent = consentState === 'opted_in'
  const handleConsent = async (action) => {
    setConsentLoading(true); setConsentError('')
    try {
      const result = await apiFetch('/v1/memory/control', { method: 'POST', body: JSON.stringify({ schema_version: '1.0', action, metadata: { source: 'react-app', surface: 'account-controls' } }) })
      const nextState = result.current_state || ({ opt_in: 'opted_in', opt_out: 'opted_out', pause: 'paused', resume: 'opted_in' }[action])
      setConsentState(String(nextState).toLowerCase())
      localStorage.setItem(consentStateKey, String(nextState).toLowerCase())
      localStorage.setItem(consentKey, String(nextState).toLowerCase() === 'opted_in' ? 'true' : 'false')
    } catch (error) { setConsentError(error.message) } finally { setConsentLoading(false) }
  }
  const handleLogout = async () => {
    setLogoutError('')
    try {
      await logout()
      navigate('/login', { replace: true })
    } catch (error) { setLogoutError(error.message || 'Logout failed. Please try again.') }
  }
  return <div className="app-shell">
    <aside className="sidebar">
      <button type="button" onClick={() => navigate('/chat')} className="brand-lockup"><span className="brand-mark">♫</span><span><strong>Spotify AI</strong><small>MEMORY SYSTEM</small></span></button>
      <p className="sidebar-label">WORKSPACE</p>
      <nav aria-label="Main navigation" className="sidebar-nav">{navigation.map((page) => <NavLink key={page.path} to={page.path} className={({ isActive }) => `sidebar-link ${isActive ? 'sidebar-link-active' : ''}`}><span className="nav-icon">{page.icon}</span><span className="min-w-0"><span className="block font-semibold">{page.label}</span><span className="nav-detail">{page.detail}</span></span></NavLink>)}</nav>
      <div className="sidebar-bottom"><div className="privacy-note"><span className="privacy-dot"/><span><strong>Privacy controls</strong><small>Your memories stay under your control.</small></span></div><button type="button" onClick={() => setProfileMenuOpen((value) => !value)} className="profile-row"><span className="avatar">{(session.username || 'U').slice(0, 1).toUpperCase()}</span><span className="min-w-0 flex-1 text-left"><strong className="block truncate">{session.username}</strong><small>My account</small></span><span>⌄</span></button>{profileMenuOpen ? <div className="profile-menu"><button type="button" onClick={() => { navigate('/profile'); setProfileMenuOpen(false) }}>View profile</button><button type="button" onClick={handleLogout}>Log out</button></div> : null}</div>
    </aside>
    <main className="main-workspace">
      <header className="topbar"><div className="min-w-0"><p className="eyebrow">YOUR PERSONAL MUSIC SPACE</p><h1 className="topbar-title">{activePage?.label || (location.pathname === '/profile' ? 'My Profile' : 'Spotify AI Memory')}</h1></div><div className="account-controls"><div className="account-identity"><span className="avatar avatar-small">{(session.username || 'U').slice(0, 1).toUpperCase()}</span><span><strong>{session.username}</strong><small>Signed in</small></span></div><div className="account-actions"><button type="button" onClick={handleLogout} className="button-secondary logout-button">Log out ↗</button><div className="consent-control"><span className={`consent-status ${memoryConsent ? 'consent-on' : consentState === 'paused' ? 'consent-paused' : 'consent-off'}`}>{consentState === 'paused' ? 'Memory paused' : memoryConsent ? 'Memory opted in' : consentState === 'unknown' ? 'Consent not set' : 'Memory opted out'}</span><div className="flex flex-wrap gap-1.5">{consentState === 'paused' ? <button type="button" disabled={consentLoading} onClick={() => handleConsent('resume')} className="consent-button">Resume</button> : <><button type="button" disabled={consentLoading || memoryConsent} onClick={() => handleConsent('opt_in')} className={`consent-button ${memoryConsent ? 'consent-button-active' : ''}`}>Opt in</button><button type="button" disabled={consentLoading || consentState === 'opted_out'} onClick={() => handleConsent('opt_out')} className="consent-button">Opt out</button><button type="button" disabled={consentLoading} onClick={() => handleConsent('pause')} className="consent-button">Pause</button></>}</div>{consentError ? <p className="mt-1 max-w-64 text-xs text-rose-300">{consentError}</p> : null}{logoutError ? <p className="mt-1 max-w-64 text-xs text-rose-300">{logoutError}</p> : null}{consentLoading ? <p className="mt-1 text-xs text-muted">Updating…</p> : null}</div></div></div></header>
      <div className="workspace-content"><div className="mb-5 flex flex-wrap items-center justify-between gap-3"><div><p className="eyebrow">WORKSPACE</p><p className="mt-1 text-sm text-muted">Personalized music, guided by memories you control.</p></div><p className="text-xs text-muted">API <span className="text-spotify">{API_BASE_URL}</span></p></div><Outlet context={{ memoryConsent, consentState, onConsentChange: handleConsent, session }} /></div>
    </main>
  </div>
}
export default DashboardLayout