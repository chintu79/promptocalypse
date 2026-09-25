import { useState } from 'react'
import type { User, SessionState } from '../types'
import { registerUser } from '../api/client'
import { saveSession } from '../utils/session'
import './RegisterModal.css'

interface RegisterModalProps {
  /** Callback fired once participant successfully signs in */
  onSuccess: (session: SessionState) => void
}

export default function RegisterModal({ onSuccess }: RegisterModalProps) {
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setErrorMessage(null)

    const trimmedName = username.trim()
    const trimmedEmail = email.trim().toLowerCase()

    if (trimmedName.length < 2) {
      setErrorMessage('Please enter your full name or participant handle (min 2 chars).')
      return
    }

    if (!trimmedEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmedEmail)) {
      setErrorMessage('Please enter a valid email address (e.g. name@domain.com).')
      return
    }

    setIsLoading(true)

    try {
      const user: User = await registerUser(trimmedName, trimmedEmail)

      // Build session state payload for localStorage (th_session_v1)
      const sessionPayload: SessionState = {
        user_id: user.user_id,
        username: user.username,
        email: user.email || trimmedEmail,
        active_level: user.active_level || 1,
        start_time: user.start_time,
        total_prompts: user.total_prompts || 0,
        failed_attempts: user.failed_attempts || 0,
        completed: Boolean(user.completed),
        cached_at: Date.now(),
      }

      saveSession(sessionPayload)
      onSuccess(sessionPayload)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Sign-in failed. Please try again.'
      setErrorMessage(msg)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="auth-overlay" role="dialog" aria-modal="true" aria-labelledby="auth-title">
      <div className="auth-card">
        {/* Header */}
        <div className="auth-header">
          <h1 id="auth-title" className="auth-title">
            Promptocalypse
          </h1>
          <p className="auth-subtitle">AI JAILBREAK ARENA // PARTICIPANT ACCESS</p>
        </div>

        {/* Strict Email Warning */}
        <div className="auth-warning">
          <div className="auth-warning__title">
            <span>⚠️</span>
            <span>Important Verification Warning</span>
          </div>
          <div className="auth-warning__body">
            You must enter your <strong>own registered email address</strong>. Challenge
            progression, live leaderboard rankings, and final verification are directly
            bound to this address. Fake or proxy emails will lead to{' '}
            <strong>immediate disqualification</strong>.
          </div>
        </div>

        {/* Sign-in Form */}
        <form className="auth-form" onSubmit={handleSubmit}>
          <div className="auth-field">
            <label className="auth-label" htmlFor="auth-name">
              Full Name or Handle
            </label>
            <input
              id="auth-name"
              type="text"
              className="auth-input"
              placeholder="e.g. Neo or Alex Mercer"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={isLoading}
              autoFocus
              required
            />
          </div>

          <div className="auth-field">
            <label className="auth-label" htmlFor="auth-email">
              Registered Email ID
            </label>
            <input
              id="auth-email"
              type="email"
              className="auth-input"
              placeholder="e.g. participant@university.edu"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={isLoading}
              required
            />
          </div>

          {errorMessage && <div className="auth-error">{errorMessage}</div>}

          <button
            type="submit"
            className="auth-submit-btn"
            disabled={isLoading || !username.trim() || !email.trim()}
          >
            {isLoading ? 'AUTHENTICATING...' : 'ENTER ARENA SESSION'}
          </button>
        </form>

        <div className="auth-footer">
          Instant single-page sign-in • No OTP or passwords required
        </div>
      </div>
    </div>
  )
}
