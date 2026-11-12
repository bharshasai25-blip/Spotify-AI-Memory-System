import { useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import AuthPage from './pages/AuthPage'
import ChatPage from './pages/ChatPage'
import DashboardLayout from './pages/DashboardLayout'
import EventIngestionPage from './pages/EventIngestionPage'
import MemorySearchPage from './pages/MemorySearchPage'
import RecommendationsPage from './pages/RecommendationsPage'
import CatalogSearchPage from './pages/CatalogSearchPage'
import MemorySettingsPage from './pages/MemorySettingsPage'
import ProfilePage from './pages/ProfilePage'
import { apiFetch } from './api/client'

function ProtectedRoutes({ session, authenticate, logout }) {
  return <Routes>
    <Route path="/login" element={session ? <Navigate to="/chat" replace /> : <AuthPage mode="login" authenticate={authenticate} />} />
    <Route path="/register" element={session ? <Navigate to="/chat" replace /> : <AuthPage mode="register" authenticate={authenticate} />} />
    <Route element={session ? <DashboardLayout session={session} logout={logout} /> : <Navigate to="/login" replace />}>
      <Route index element={<Navigate to="/chat" replace />} />
      <Route path="/chat" element={<ChatPage session={session} />} />
      <Route path="/preferences" element={<EventIngestionPage session={session} />} />
      <Route path="/events" element={<Navigate to="/preferences" replace />} />
      <Route path="/search" element={<CatalogSearchPage session={session} />} />
      <Route path="/recommendations" element={<RecommendationsPage session={session} />} />
      <Route path="/memory-search" element={<MemorySearchPage session={session} />} />
      <Route path="/memory-settings" element={<MemorySettingsPage session={session} />} />
      <Route path="/profile" element={<ProfilePage session={session} />} />
    </Route>
    <Route path="*" element={<Navigate to={session ? '/chat' : '/login'} replace />} />
  </Routes>
}
export default function AppRoutes() {
  const [session, setSession] = useState(() => {
    try { return JSON.parse(localStorage.getItem('spotify_ai_session') || 'null') } catch { return null }
  })
  useEffect(() => {
    if (session) { localStorage.setItem('spotify_ai_session', JSON.stringify(session)); localStorage.setItem('spotify_ai_token', session.access_token) }
    else { localStorage.removeItem('spotify_ai_session'); localStorage.removeItem('spotify_ai_token') }
  }, [session])
  const authenticate = async (mode, username, password) => {
    const result = await apiFetch(`/v1/auth/${mode}`, { method: 'POST', body: JSON.stringify({ schema_version: '1.0', username, password, metadata: { source: 'react-app' } }) })
    setSession(result)
  }
  const logout = async () => {
    if (session?.access_token) {
      try { await apiFetch('/v1/auth/logout', { method: 'POST', body: JSON.stringify({ schema_version: '1.0', metadata: { source: 'react-app' } }) }) }
      catch (error) { if (error.status !== 401) throw error }
    }
    setSession(null)
  }
  return <ProtectedRoutes session={session} authenticate={authenticate} logout={logout} />
}
