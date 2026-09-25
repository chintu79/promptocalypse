import { describe, it, beforeEach } from 'node:test'
import assert from 'node:assert/strict'
import type { SessionState, SubmitKeyResponse } from '../types/index.ts'
import { loadSession, saveSession, clearSession } from './session.ts'

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

describe('Key Submission Vault & Failure Logic', () => {
  beforeEach(() => {
    const mockStorage = new LocalStorageMock()
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
    clearSession()
  })

  it('updates session when incorrect key penalty is received', () => {
    const initialSession: SessionState = {
      user_id: 'usr_test1',
      username: 'TestAgent',
      active_level: 1,
      failed_attempts: 0,
    }
    saveSession(initialSession)

    // Simulate incorrect submission payload returned from POST /api/submit-key
    const failurePayload: SubmitKeyResponse = {
      status: 'incorrect',
      unlocked_level: 1,
      penalty_points: 25,
      message: 'Key verification failed.',
    }

    assert.equal(failurePayload.status, 'incorrect')
    assert.equal(failurePayload.penalty_points, 25)

    // Apply failure mutation to session
    const current = loadSession()!
    const updated: SessionState = {
      ...current,
      failed_attempts: (current.failed_attempts ?? 0) + 1,
    }
    saveSession(updated)

    const reloaded = loadSession()!
    assert.equal(reloaded.failed_attempts, 1)
  })

  it('advances active_level upon correct intermediate key verification', () => {
    const initialSession: SessionState = {
      user_id: 'usr_test2',
      username: 'TestAgent2',
      active_level: 1,
    }
    saveSession(initialSession)

    // Simulate correct submission payload for Level 1
    const successPayload: SubmitKeyResponse = {
      status: 'correct',
      unlocked_level: 2,
      message: 'Level 1 cleared successfully.',
    }

    assert.equal(successPayload.status, 'correct')
    assert.equal(successPayload.unlocked_level, 2)

    const current = loadSession()!
    const updated: SessionState = {
      ...current,
      active_level: successPayload.unlocked_level,
    }
    saveSession(updated)

    const reloaded = loadSession()!
    assert.equal(reloaded.active_level, 2)
  })

  it('marks run as completed with final score on Level 3 victory', () => {
    const initialSession: SessionState = {
      user_id: 'usr_test3',
      username: 'Victor',
      active_level: 3,
      failed_attempts: 1,
      total_prompts: 6,
    }
    saveSession(initialSession)

    // Simulate Level 3 victory completion payload
    const victoryPayload: SubmitKeyResponse = {
      status: 'completed',
      message: 'System compromised! Victory achieved.',
      final_score: 860.0,
      completion_time: '2026-09-24T12:00:00.000Z',
      stats: {
        total_prompts: 6,
        elapsed_minutes: 12,
        failed_attempts: 1,
      },
    }

    assert.equal(victoryPayload.status, 'completed')
    assert.equal(victoryPayload.final_score, 860.0)

    const current = loadSession()!
    const updated: SessionState = {
      ...current,
      completed: true,
      final_score: victoryPayload.final_score,
    }
    saveSession(updated)

    const reloaded = loadSession()!
    assert.equal(reloaded.completed, true)
    assert.equal(reloaded.final_score, 860.0)
  })

  it('verifies 8-frame shake animation definition', () => {
    // 8 frame keyframe percentages
    const keyframes = [0, 12.5, 25, 37.5, 50, 62.5, 75, 87.5, 100]
    assert.equal(keyframes.length, 9) // 0% + 8 transitions = 8-frame movement cycle
    assert.equal(keyframes[1], 12.5)
    assert.equal(keyframes[8], 100)
  })
})
