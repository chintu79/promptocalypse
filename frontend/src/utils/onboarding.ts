import type { SessionState, User } from '../types'

export type OnboardingStep = 1 | 2 | 3

export type RegistrationHandler = (
  username: string,
  email?: string
) => Promise<User>

export const ONBOARDING_STEPS: ReadonlyArray<{
  id: OnboardingStep
  label: string
}> = [
  { id: 1, label: 'Identity' },
  { id: 2, label: 'Briefing' },
  { id: 3, label: 'Rules' },
]

export const ONBOARDING_TARGETS = [
  {
    name: 'RefundBot',
    description: 'Extract the secret from the refund assistant before it locks the account.',
  },
  {
    name: 'SysAdmin',
    description: 'Breach the system administrator layer and recover its protected flag.',
  },
  {
    name: 'Project Blackout',
    description: 'Navigate the blackout project and expose the final defense secret.',
  },
] as const

export const ONBOARDING_RULES = [
  {
    label: 'Time limit',
    value: '2 hours',
    detail: 'Complete the run before the two-hour arena clock expires.',
  },
  {
    label: 'Prompt cooldown',
    value: '3 seconds',
    detail: 'Wait three seconds between prompts before submitting another one.',
  },
  {
    label: 'Excess prompts',
    value: '-15 pts',
    detail: 'Each prompt beyond the three-prompt allowance costs 15 points.',
  },
  {
    label: 'Wrong keys',
    value: '-25 pts',
    detail: 'Each incorrect secret key costs 25 points.',
  },
] as const

export function validateOnboardingIdentity(
  username: string,
  email: string
): string | null {
  const cleanUsername = username.trim()
  if (cleanUsername.length < 2) {
    return 'Enter a participant handle with at least 2 characters.'
  }
  if (cleanUsername.length > 50) {
    return 'Participant handles must be 50 characters or fewer.'
  }
  if (!/^[a-zA-Z0-9_\- ]+$/.test(cleanUsername)) {
    return 'Use letters, numbers, spaces, underscores, or hyphens in your handle.'
  }

  const cleanEmail = email.trim()
  if (cleanEmail && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(cleanEmail)) {
    return 'Enter a valid email address or leave the optional field blank.'
  }

  return null
}

export function getNextOnboardingStep(
  step: OnboardingStep
): OnboardingStep | null {
  if (step === 1) return 2
  if (step === 2) return 3
  return null
}

export function getPreviousOnboardingStep(
  step: OnboardingStep
): OnboardingStep | null {
  if (step === 3) return 2
  if (step === 2) return 1
  return null
}

export function canSubmitOnboarding(step: OnboardingStep): boolean {
  return step === 3
}

export function createSessionFromUser(
  user: User,
  submittedEmail: string
): SessionState {
  const email = user.email || submittedEmail.trim().toLowerCase() || undefined

  return {
    user_id: user.user_id,
    username: user.username,
    email,
    current_level: user.current_level ?? 1,
    start_time: user.start_time,
    total_prompts: user.total_prompts ?? 0,
    failed_attempts: user.failed_attempts ?? 0,
    completed: Boolean(user.completed),
    cached_at: Date.now(),
  }
}

export async function submitOnboarding(
  step: OnboardingStep,
  username: string,
  email: string,
  register: RegistrationHandler
): Promise<SessionState | null> {
  if (!canSubmitOnboarding(step)) {
    return null
  }

  const validationError = validateOnboardingIdentity(username, email)
  if (validationError) {
    throw new Error(validationError)
  }

  const user = await register(
    username.trim(),
    email.trim().toLowerCase() || undefined
  )

  return createSessionFromUser(user, email)
}
