import type { SessionState } from '../types'

export const SESSION_STORAGE_KEY = 'th_session_v1'
export const SESSION_UPDATE_EVENT = 'th_session_update'

/**
 * Calculates prompt penalty points: 15 pts per prompt after the 3rd prompt.
 * Formula: max(0, prompts - 3) * 15
 * E.g., prompts = 5 -> (5 - 3) * 15 = 30 pts.
 */
export function calculatePromptPenalty(prompts: number): number {
  return Math.max(0, prompts - 3) * 15
}

/**
 * Calculates current dynamic score based on TECH-SPEC §5.1 formula:
 * S = max(0, 1000 - 15 * max(0, P - 3) - 2 * T - 25 * K)
 */
export function calculateDynamicScore({
  prompts = 0,
  elapsedSeconds = 0,
  failedAttempts = 0,
  baseScore = 1000,
}: {
  prompts?: number
  elapsedSeconds?: number
  failedAttempts?: number
  baseScore?: number
}): number {
  const promptPenalty = calculatePromptPenalty(prompts)
  const elapsedMinutes = Math.floor(Math.max(0, elapsedSeconds) / 60)
  const timePenalty = elapsedMinutes * 2
  const failPenalty = Math.max(0, failedAttempts) * 25

  return Math.max(0, baseScore - promptPenalty - timePenalty - failPenalty)
}

/**
 * Formats elapsed seconds into MM:SS (or HH:MM:SS if >= 1 hour).
 */
export function formatElapsedTime(totalSeconds: number): string {
  const secs = Math.max(0, Math.floor(totalSeconds))
  const hours = Math.floor(secs / 3600)
  const minutes = Math.floor((secs % 3600) / 60)
  const remainingSecs = secs % 60

  const pad = (n: number) => n.toString().padStart(2, '0')

  return `${pad(hours)}:${pad(minutes)}:${pad(remainingSecs)}`
}

/**
 * Recover session state from localStorage (th_session_v1).
 */
export function loadSession(): SessionState | null {
  if (typeof window === 'undefined' || !window.localStorage) {
    return null
  }
  try {
    const raw = localStorage.getItem(SESSION_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as SessionState
    if (parsed && typeof parsed.active_level === 'number') {
      return parsed
    }
    return null
  } catch (err) {
    console.warn('Failed to parse session from localStorage:', err)
    return null
  }
}

/**
 * Save session state to localStorage (th_session_v1) and notify listeners.
 */
export function saveSession(session: SessionState): void {
  if (typeof window === 'undefined' || !window.localStorage) {
    return
  }
  try {
    const payload = {
      ...session,
      cached_at: Date.now(),
    }
    localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(payload))
    window.dispatchEvent(
      new CustomEvent(SESSION_UPDATE_EVENT, { detail: payload })
    )
  } catch (err) {
    console.warn('Failed to save session to localStorage:', err)
  }
}

/**
 * Clears current session from localStorage.
 */
export function clearSession(): void {
  if (typeof window === 'undefined' || !window.localStorage) {
    return
  }
  try {
    localStorage.removeItem(SESSION_STORAGE_KEY)
    window.dispatchEvent(new CustomEvent(SESSION_UPDATE_EVENT, { detail: null }))
  } catch (err) {
    console.warn('Failed to clear session from localStorage:', err)
  }
}

/**
 * Checks if a participant is authenticated with a registered profile.
 */
export function hasValidSession(): boolean {
  const session = loadSession()
  return Boolean(session && session.user_id && (session.email || session.username !== 'GhostRunner'))
}

/**
 * Returns existing session or creates and persists a default session.
 */
export function getOrCreateDefaultSession(): SessionState {
  const existing = loadSession()
  if (existing) {
    return existing
  }
  const defaultSession: SessionState = {
    user_id: `usr_${Date.now()}`,
    username: 'GhostRunner',
    active_level: 1,
    start_time: new Date().toISOString(),
    total_prompts: 0,
    failed_attempts: 0,
    completed: false,
    final_score: 1000,
    cached_at: Date.now(),
  }
  saveSession(defaultSession)
  return defaultSession
}
