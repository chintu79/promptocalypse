import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import type { User } from '../types/index.ts'
import {
  canSubmitOnboarding,
  createSessionFromUser,
  getNextOnboardingStep,
  getPreviousOnboardingStep,
  ONBOARDING_RULES,
  ONBOARDING_STEPS,
  ONBOARDING_TARGETS,
  submitOnboarding,
  validateOnboardingIdentity,
} from './onboarding.ts'

const registeredUser: User = {
  user_id: 'usr_54',
  username: 'Neo',
  current_level: 1,
  start_time: '2026-09-25T12:00:00.000Z',
  total_prompts: 0,
  failed_attempts: 0,
  completed: false,
}

describe('interactive onboarding sequence', () => {
  it('exposes the three ordered onboarding steps', () => {
    assert.deepEqual(
      ONBOARDING_STEPS.map(({ id, label }) => ({ id, label })),
      [
        { id: 1, label: 'Identity' },
        { id: 2, label: 'Briefing' },
        { id: 3, label: 'Rules' },
      ]
    )
    assert.equal(getNextOnboardingStep(1), 2)
    assert.equal(getNextOnboardingStep(2), 3)
    assert.equal(getNextOnboardingStep(3), null)
    assert.equal(getPreviousOnboardingStep(3), 2)
    assert.equal(getPreviousOnboardingStep(2), 1)
    assert.equal(getPreviousOnboardingStep(1), null)
  })

  it('defines all targets and the any-order briefing rule', () => {
    assert.deepEqual(
      ONBOARDING_TARGETS.map((target) => target.name),
      ['RefundBot', 'SysAdmin', 'Project Blackout']
    )
    assert.equal(ONBOARDING_TARGETS.length, 3)
  })

  it('defines every required arena rule and penalty', () => {
    assert.deepEqual(
      ONBOARDING_RULES.map((rule) => [rule.label, rule.value]),
      [
        ['Time limit', '2 hours'],
        ['Prompt cooldown', '3 seconds'],
        ['Excess prompts', '-15 pts'],
        ['Wrong keys', '-25 pts'],
      ]
    )
  })

  it('accepts a handle without email and rejects malformed optional email', () => {
    assert.equal(validateOnboardingIdentity('Neo', ''), null)
    assert.match(
      validateOnboardingIdentity('Neo', 'not-an-email') ?? '',
      /valid email/
    )
    assert.match(validateOnboardingIdentity('N', '') ?? '', /at least 2/)
  })

  it('does not invoke registration during identity or briefing', async () => {
    let calls = 0
    const register = async (): Promise<User> => {
      calls += 1
      return registeredUser
    }

    assert.equal(await submitOnboarding(1, 'Neo', '', register), null)
    assert.equal(await submitOnboarding(2, 'Neo', '', register), null)
    assert.equal(calls, 0)
    assert.equal(canSubmitOnboarding(1), false)
    assert.equal(canSubmitOnboarding(2), false)
  })

  it('calls registration exactly once on final submission and maps the session', async () => {
    let calls = 0
    let receivedUsername = ''
    let receivedEmail: string | undefined
    const register = async (
      username: string,
      email?: string
    ): Promise<User> => {
      calls += 1
      receivedUsername = username
      receivedEmail = email
      return registeredUser
    }

    const session = await submitOnboarding(3, '  Neo  ', '', register)

    assert.equal(calls, 1)
    assert.equal(receivedUsername, 'Neo')
    assert.equal(receivedEmail, undefined)
    assert.ok(session)
    assert.equal(session?.user_id, 'usr_54')
    assert.equal(session?.username, 'Neo')
    assert.equal(session?.start_time, registeredUser.start_time)
    assert.equal(session?.total_prompts, 0)
    assert.equal(session?.current_level, 1)
  })

  it('preserves the authoritative response session values', () => {
    const session = createSessionFromUser(
      {
        ...registeredUser,
        current_level: 2,
        start_time: '2026-09-25T12:34:56.000Z',
        total_prompts: 4,
        failed_attempts: 2,
        completed: true,
        email: 'canonical@example.com',
      },
      'submitted@example.com'
    )

    assert.deepEqual(session, {
      user_id: 'usr_54',
      username: 'Neo',
      email: 'canonical@example.com',
      current_level: 2,
      start_time: '2026-09-25T12:34:56.000Z',
      total_prompts: 4,
      failed_attempts: 2,
      completed: true,
      cached_at: session.cached_at,
    })
  })

  it('propagates registration failures for the wizard to display', async () => {
    await assert.rejects(
      () =>
        submitOnboarding(3, 'Neo', '', async () => {
          throw new Error('Registration service unavailable')
        }),
      /Registration service unavailable/
    )
  })
})
