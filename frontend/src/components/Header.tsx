import { useState, useEffect, useMemo } from 'react'
import { setActiveLevel, fetchLeaderboard } from '../api/client'
import { saveSession } from '../utils/session'
import type { SessionState } from '../types'
import {
  calculateDynamicScore,
  calculatePromptPenalty,
  formatElapsedTime,
  loadSession,
  getOrCreateDefaultSession,
  SESSION_UPDATE_EVENT,
} from '../utils/session'
import './Header.css'

interface HeaderProps {
  /** Optional external session override (e.g. from parent state/context) */
  session?: SessionState | null
  onToggleLeaderboard?: () => void
}

export default function Header({ session: propSession, onToggleLeaderboard }: HeaderProps) {
  // Load and recover session from localStorage (th_session_v1)
  const [internalSession, setInternalSession] = useState<SessionState>(() => {
    return propSession || loadSession() || getOrCreateDefaultSession()
  })

  // Synchronize if prop changes
  useEffect(() => {
    if (propSession) {
      setInternalSession(propSession)
    }
  }, [propSession])

  // Listen for session updates (same-tab and multi-tab sync)
  useEffect(() => {
    const handleLocalUpdate = (e: Event) => {
      const customEvent = e as CustomEvent<SessionState | null>
      if (customEvent.detail) {
        setInternalSession(customEvent.detail)
      } else {
        setInternalSession(getOrCreateDefaultSession())
      }
    }

    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'th_session_v1') {
        const reloaded = loadSession()
        if (reloaded) {
          setInternalSession(reloaded)
        }
      }
    }

    window.addEventListener(SESSION_UPDATE_EVENT, handleLocalUpdate)
    window.addEventListener('storage', handleStorageChange)
    return () => {
      window.removeEventListener(SESSION_UPDATE_EVENT, handleLocalUpdate)
      window.removeEventListener('storage', handleStorageChange)
    }
  }, [])

  const activeLevel = internalSession.active_level ?? 1
  const clearedLevels = internalSession.cleared_levels ?? []
  const completed = Boolean(internalSession.completed)
  const totalPrompts = internalSession.total_prompts ?? 0
  const failedAttempts = internalSession.failed_attempts ?? 0

  // ── User Rank Fetching ──
  const [userRank, setUserRank] = useState<number | null>(null)
  useEffect(() => {
    if (!internalSession.username) return
    const fetchRank = async () => {
      try {
        const board = await fetchLeaderboard()
        const entry = board.find(b => b.username === internalSession.username)
        if (entry) setUserRank(entry.rank)
      } catch (e) {
        // ignore errors
      }
    }
    fetchRank()
    const intv = setInterval(fetchRank, 30000)
    return () => clearInterval(intv)
  }, [internalSession.username])

  // ── Stopwatch Timer counting elapsed time from start_time ──
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(() => {
    if (!internalSession.start_time) return 0
    const startMs = new Date(internalSession.start_time).getTime()
    return Math.max(0, Math.floor((Date.now() - startMs) / 1000))
  })

  const remainingSeconds = Math.max(0, 7200 - elapsedSeconds)

  useEffect(() => {
    if (remainingSeconds === 0 && !completed && internalSession.start_time) {
      const evt = new CustomEvent('ARENA_TIMEOUT');
      window.dispatchEvent(evt);
    }
  }, [remainingSeconds, completed, internalSession.start_time])

  useEffect(() => {
    // If completed or start_time is missing, don't run the ticker
    if (completed || !internalSession.start_time) {
      return
    }

    const startMs = new Date(internalSession.start_time).getTime()
    // Recalculate immediately
    setElapsedSeconds(Math.max(0, Math.floor((Date.now() - startMs) / 1000)))

    const timer = setInterval(() => {
      setElapsedSeconds(Math.max(0, Math.floor((Date.now() - startMs) / 1000)))
    }, 1000)

    return () => clearInterval(timer)
  }, [internalSession.start_time, completed])

  // ── Dynamic Score & Prompt Penalty Calculations ──
  const promptPenalty = useMemo(
    () => calculatePromptPenalty(totalPrompts),
    [totalPrompts]
  )

  const dynamicScore = useMemo(() => {
    if (completed && typeof internalSession.final_score === 'number') {
      return internalSession.final_score
    }
    return calculateDynamicScore({
      prompts: totalPrompts,
      elapsedSeconds,
      failedAttempts,
    })
  }, [
    completed,
    internalSession.final_score,
    totalPrompts,
    elapsedSeconds,
    failedAttempts,
  ])

  // ── Step Indicator Configurations ──
  const levels = [1, 2, 3]

  return (
    <header className="hud-header">
      {/* Brand & Participant Identity */}
      <div className="hud-brand">
        <span className="hud-logo">AI Jailbreak Arena</span>
        {internalSession.username && (
          <span
            className="hud-user-badge"
            title={internalSession.email ? `Email: ${internalSession.email}` : undefined}
          >
            AGENT: <strong>{internalSession.username}</strong>
            {internalSession.email && (
              <span style={{ opacity: 0.7, marginLeft: '0.35rem', fontSize: '0.7rem' }}>
                ({internalSession.email})
              </span>
            )}
          </span>
        )}
      </div>

      {/* Segmented Step Indicator: Level 1, 2, 3 + Leaderboard Toggle */}
      <nav aria-label="Level Progress" className="hud-steps">
        {levels.map((lvl) => {
          const isCompleted = completed || clearedLevels.includes(lvl)
          const isActive = !completed && activeLevel === lvl
          const isLocked = !completed && !clearedLevels.includes(lvl) && activeLevel !== lvl

          let stepClass = 'hud-step'
          let icon = '🔒'
          let ariaStatus = 'Locked'

          if (isCompleted) {
            stepClass += ' hud-step--completed'
            icon = '✓'
            ariaStatus = 'Completed'
          } else if (isActive) {
            stepClass += ' hud-step--active'
            icon = '●'
            ariaStatus = 'Active'
          } else if (isLocked) {
            stepClass += ' hud-step--locked'
            icon = '🔒'
            ariaStatus = 'Locked'
          }

          const targetNames = ["RefundBot", "SysAdmin", "Blackout"]
          return (
            <button
              key={lvl}
              className={stepClass}
              title={`Level ${lvl}: ${ariaStatus}`}
              aria-current={isActive ? 'step' : undefined}
              onClick={() => {
                if (!completed && internalSession.user_id && activeLevel !== lvl) {
                   setActiveLevel(internalSession.user_id, lvl)
                   const updated = { ...internalSession, active_level: lvl }
                   saveSession(updated)
                   setInternalSession(updated)
                }
              }}
              disabled={completed}
              style={{ background: 'transparent', border: 'none', cursor: completed ? 'default' : 'pointer' }}
            >
              <span className="hud-step__icon">{icon}</span>
              <span className="hud-step__label">Target {lvl}: {targetNames[lvl - 1]}</span>
            </button>
          )
        })}

        <button
          type="button"
          className="hud-step"
          onClick={onToggleLeaderboard}
          style={{ background: 'transparent', border: 'none', cursor: 'pointer', borderLeft: '1px solid var(--border)', marginLeft: '0.25rem', paddingLeft: '0.75rem' }}
        >
          <span className="hud-step__icon">🏆</span>
          <span className="hud-step__label">Leaderboard</span>
        </button>
      </nav>

      {/* Live Telemetry Bar */}
      <div className="hud-telemetry">
        {/* User Rank */}
        <div className="hud-metric">
          <span className="hud-metric__label">RANK:</span>
          <span className="hud-metric__value">
            {userRank !== null ? `#${userRank}` : '--'}
          </span>
        </div>

        {/* Stopwatch Timer */}
        <div className="hud-metric">
          <span className="hud-metric__label">TIME:</span>
          <span className={`hud-metric__value hud-metric__value--time ${
            remainingSeconds <= 300 
              ? 'hud-metric__value--time-danger' 
              : remainingSeconds <= 900 
                ? 'hud-metric__value--time-warning' 
                : ''
          }`}>
            {formatElapsedTime(remainingSeconds)}
          </span>
        </div>

        {/* Dynamic Prompt Count & Penalty Counter */}
        <div className="hud-metric">
          <span className="hud-metric__label">PROMPTS:</span>
          <span className="hud-metric__value">
            {totalPrompts}
            <span
              className={`hud-metric__penalty${promptPenalty > 0 ? ' hud-metric__penalty--active' : ''}`}
            >
              (-{promptPenalty} pts)
            </span>
          </span>
        </div>

        {/* Dynamic Live Score */}
        <div className="hud-metric">
          <span className="hud-metric__label">SCORE:</span>
          <span
            className={`hud-metric__value hud-metric__value--score${
              dynamicScore <= 500
                ? ' hud-metric__value--score-danger'
                : dynamicScore <= 800
                  ? ' hud-metric__value--score-warning'
                  : ''
            }`}
          >
            {Math.round(dynamicScore)}
          </span>
        </div>
      </div>
    </header>
  )
}
