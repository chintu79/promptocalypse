import { describe, it, beforeEach } from 'node:test'
import assert from 'node:assert/strict'
import {
  calculatePromptPenalty,
  calculateDynamicScore,
  formatElapsedTime,
  loadSession,
  saveSession,
  clearSession,
  getOrCreateDefaultSession,
  hasValidSession,
} from './session.ts'
import type { SessionState } from '../types/index.ts'

// In-memory mock localStorage for Node testing
class LocalStorageMock implements Partial<Storage> {
  private store: Record<string, string> = {}
  getItem(key: string): string | null {
    return this.store[key] ?? null
  }
  setItem(key: string, value: string): void {
    this.store[key] = String(value)
  }
  removeItem(key: string): void {
    delete this.store[key]
  }
  clear(): void {
    this.store = {}
  }
}

describe('Cyberpunk HUD & Session Logic', () => {
  describe('calculatePromptPenalty', () => {
    it('returns 0 penalty for 0 to 3 prompts (base prompt allowance)', () => {
      assert.equal(calculatePromptPenalty(0), 0)
      assert.equal(calculatePromptPenalty(1), 0)
      assert.equal(calculatePromptPenalty(2), 0)
      assert.equal(calculatePromptPenalty(3), 0)
    })

    it('applies 15 points per prompt beyond the 3rd prompt', () => {
      assert.equal(calculatePromptPenalty(4), 15)
      // Exactly matching the task specification: "Prompts: 5 (-30 pts)"
      assert.equal(calculatePromptPenalty(5), 30)
      assert.equal(calculatePromptPenalty(6), 45)
      assert.equal(calculatePromptPenalty(10), 105)
    })
  })

  describe('calculateDynamicScore', () => {
    it('returns base score of 1000 for fresh run', () => {
      const score = calculateDynamicScore({
        prompts: 0,
        elapsedSeconds: 0,
        failedAttempts: 0,
      })
      assert.equal(score, 1000)
    })

    it('deducts prompt penalty, elapsed time (2 pts/min), and failed attempts (25 pts/fail)', () => {
      // 5 prompts: (5 - 3) * 15 = 30 pts
      // 120s elapsed: 2 minutes * 2 = 4 pts
      // 1 failed attempt: 1 * 25 = 25 pts
      // Total: 1000 - 30 - 4 - 25 = 941 pts
      const score = calculateDynamicScore({
        prompts: 5,
        elapsedSeconds: 120,
        failedAttempts: 1,
      })
      assert.equal(score, 941)
    })

    it('floors score at 0', () => {
      const score = calculateDynamicScore({
        prompts: 100,
        elapsedSeconds: 36000,
        failedAttempts: 50,
      })
      assert.equal(score, 0)
    })
  })

  describe('formatElapsedTime', () => {
    it('formats seconds to MM:SS', () => {
      assert.equal(formatElapsedTime(0), '00:00')
      assert.equal(formatElapsedTime(9), '00:09')
      assert.equal(formatElapsedTime(65), '01:05')
      assert.equal(formatElapsedTime(599), '09:59')
      assert.equal(formatElapsedTime(600), '10:00')
    })

    it('formats hours to HH:MM:SS if >= 3600', () => {
      assert.equal(formatElapsedTime(3600), '01:00:00')
      assert.equal(formatElapsedTime(3665), '01:01:05')
    })
  })

  describe('localStorage session persistence (th_session_v1)', () => {
    beforeEach(() => {
      const mockStorage = new LocalStorageMock()
      // Setup mock global window and localStorage
      const mockWindow = {
        localStorage: mockStorage as unknown as Storage,
        dispatchEvent: () => true,
        addEventListener: () => {},
        removeEventListener: () => {},
      }
      Object.defineProperty(globalThis, 'window', {
        value: mockWindow,
        writable: true,
        configurable: true,
      })
      Object.defineProperty(globalThis, 'localStorage', {
        value: mockStorage as unknown as Storage,
        writable: true,
        configurable: true,
      })
    })

    it('saves and recovers session accurately', () => {
      const sampleSession: SessionState = {
        user_id: 'usr_abc123',
        username: 'CyberRunner',
        active_level: 2,
        start_time: '2026-09-24T10:00:00.000Z',
        total_prompts: 5,
        failed_attempts: 1,
        completed: false,
      }

      saveSession(sampleSession)
      const loaded = loadSession()

      assert.ok(loaded !== null)
      if (loaded) {
        assert.equal(loaded.user_id, 'usr_abc123')
        assert.equal(loaded.username, 'CyberRunner')
        assert.equal(loaded.active_level, 2)
        assert.equal(loaded.total_prompts, 5)
        assert.equal(loaded.failed_attempts, 1)
        assert.equal(loaded.completed, false)
        assert.ok(loaded.cached_at)
      }
    })

    it('returns null when no session is stored', () => {
      clearSession()
      assert.equal(loadSession(), null)
    })

    it('getOrCreateDefaultSession initializes a default session when none exists', () => {
      clearSession()
      const session = getOrCreateDefaultSession()
      assert.ok(session)
      assert.equal(session.active_level, 1)
      assert.equal(session.total_prompts, 0)
      assert.ok(session.start_time)
      assert.ok(session.user_id.startsWith('usr_'))

      // Second call returns existing session
      const secondCall = getOrCreateDefaultSession()
      assert.equal(secondCall.user_id, session.user_id)
    })

    it('hasValidSession correctly identifies registered sessions with email', () => {
      clearSession()
      assert.equal(hasValidSession(), false)

      // GhostRunner dummy session without email is not considered authenticated
      saveSession({
        user_id: 'usr_guest',
        username: 'GhostRunner',
        active_level: 1,
      })
      assert.equal(hasValidSession(), false)

      // Registered user with email is authenticated
      saveSession({
        user_id: 'usr_real',
        username: 'RealUser',
        email: 'real@domain.com',
        active_level: 1,
      })
      assert.equal(hasValidSession(), true)
    })
  })
})

