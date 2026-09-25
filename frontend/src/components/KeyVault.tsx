import { useState, useRef } from 'react'
import type { SessionState, SubmitKeyResponse } from '../types'
import { submitKey } from '../api/client'
import { loadSession, saveSession, getOrCreateDefaultSession } from '../utils/session'
import { triggerVictoryConfetti } from '../utils/confetti'
import './KeyVault.css'

interface KeyVaultProps {
  /** Optional callback fired when Level 3 is completed */
  onVictory?: (response: SubmitKeyResponse) => void
  /** Optional custom verification handler (e.g. for testing/mocking) */
  onSubmitKey?: (userId: string, key: string, level: number) => Promise<SubmitKeyResponse>
}

export default function KeyVault({ onVictory, onSubmitKey }: KeyVaultProps) {
  const [keyInput, setKeyInput] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isShaking, setIsShaking] = useState(false)
  const [statusMessage, setStatusMessage] = useState<{
    text: string
    type: 'error' | 'success' | 'info'
  } | null>(null)

  const shakeTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const borderTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  const session = loadSession() || getOrCreateDefaultSession()
  const isCompleted = Boolean(session.completed)
  const currentLevel = session.active_level ?? 1

  const handleVerify = async () => {
    const trimmed = keyInput.trim()
    if (!trimmed || isSubmitting || isCompleted) return

    setIsSubmitting(true)
    setStatusMessage(null)

    try {
      const verifyFn = onSubmitKey || submitKey
      const response = await verifyFn(session.user_id, trimmed, currentLevel)

      if (response.status === 'incorrect') {
        // Trigger 8-frame shake animation + 2s alert state
        setIsShaking(true)
        setStatusMessage({
          text: `Invalid Key. Penalty: -${response.penalty_points ?? 25} Pts`,
          type: 'error',
        })

        // Update failed_attempts in local session to sync HUD immediately
        const updatedSession: SessionState = {
          ...session,
          failed_attempts: (session.failed_attempts ?? 0) + 1,
        }
        saveSession(updatedSession)

        if (shakeTimeoutRef.current) clearTimeout(shakeTimeoutRef.current)
        if (borderTimeoutRef.current) clearTimeout(borderTimeoutRef.current)

        shakeTimeoutRef.current = setTimeout(() => {
          setIsShaking(false)
        }, 400) // Duration of the 8-frame shake animation

        borderTimeoutRef.current = setTimeout(() => {
          setStatusMessage((prev) => (prev?.type === 'error' ? null : prev))
        }, 2000) // 2-second alert red window per TECH-SPEC §3.1
      } else if (response.status === 'correct') {
        // Unlocked intermediate level (1 -> 2 or 2 -> 3)
        const nextLevel = response.unlocked_level ?? currentLevel + 1
        const updatedSession: SessionState = {
          ...session,
          active_level: nextLevel,
        }
        saveSession(updatedSession)
        setKeyInput('')
        setStatusMessage({
          text: response.message || `Level ${currentLevel} cleared! Unlocking Level ${nextLevel}...`,
          type: 'success',
        })
      } else if (response.status === 'completed') {
        // Level 3 Solved -> Trigger Confetti & Victory Modal
        triggerVictoryConfetti()

        const updatedSession: SessionState = {
          ...session,
          active_level: 3,
          completed: true,
          final_score: response.final_score,
        }
        saveSession(updatedSession)
        setKeyInput('')
        setStatusMessage({
          text: 'Victory! All defense layers breached.',
          type: 'success',
        })

        if (onVictory) {
          onVictory(response)
        }
      }
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : 'Verification request failed'
      // If error occurs, trigger shake and error badge
      setIsShaking(true)
      setStatusMessage({
        text: errorMsg,
        type: 'error',
      })
      setTimeout(() => setIsShaking(false), 400)
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleVerify()
    }
  }

  return (
    <div className="vault-card">
      <div className="vault-header">
        <h3 className="vault-title">Vault Key Submission</h3>
        <span className="vault-level-badge">
          LEVEL: <strong>{isCompleted ? 'COMPLETED' : currentLevel}</strong>
        </span>
      </div>

      <div className="vault-input-group">
        <input
          type="text"
          className={`vault-input${isShaking ? ' vault-input--shake' : ''}`}
          aria-label="Secret Flag Key"
          placeholder={isCompleted ? 'Arena Cleared' : 'FLAG{...}'}
          value={keyInput}
          onChange={(e) => setKeyInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isSubmitting || isCompleted}
          autoComplete="off"
          spellCheck="false"
        />

        <button
          className="vault-btn"
          onClick={handleVerify}
          disabled={isSubmitting || isCompleted || !keyInput.trim()}
        >
          {isCompleted
            ? 'COMPLETED ✓'
            : isSubmitting
              ? 'VERIFYING...'
              : 'VERIFY KEY'}
        </button>
      </div>

      {statusMessage && (
        <div className={`vault-status vault-status--${statusMessage.type}`}>
          {statusMessage.text}
        </div>
      )}
    </div>
  )
}
