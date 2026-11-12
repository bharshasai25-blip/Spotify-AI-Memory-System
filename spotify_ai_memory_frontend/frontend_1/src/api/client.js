/**
 * Shared API helper for the frontend.
 *
 * This keeps all fetch logic, authorization headers, and error parsing in one place.
 * Components can then focus on rendering and user interaction instead of HTTP boilerplate.
 */

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export async function apiFetch(path, options = {}) {
  const token = localStorage.getItem('spotify_ai_token')

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  })

  const contentType = response.headers.get('content-type') || ''
  const data = contentType.includes('application/json') ? await response.json() : null

  if (!response.ok) {
    const error = new Error(data?.detail || data?.message || 'Request failed')
    error.status = response.status
    throw error
  }

  return data
}
