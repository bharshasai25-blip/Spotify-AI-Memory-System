import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AuthPanel from '../components/AuthPanel'

function AuthPage({ mode, authenticate }) {
  const navigate = useNavigate()
  const [authForm, setAuthForm] = useState({ username: '', password: '' })
  const [authError, setAuthError] = useState('')

  const handleSubmit = async (event) => {
    event.preventDefault()
    setAuthError('')
    try {
      await authenticate(mode, authForm.username, authForm.password)
      navigate('/chat', { replace: true })
    } catch (error) {
      setAuthError(error.message)
    }
  }

  return (
    <AuthPanel
      authMode={mode}
      authForm={authForm}
      setAuthForm={setAuthForm}
      authError={authError}
      onSubmit={handleSubmit}
      onNavigate={(nextMode) => navigate(`/${nextMode}`)}
    />
  )
}

export default AuthPage
