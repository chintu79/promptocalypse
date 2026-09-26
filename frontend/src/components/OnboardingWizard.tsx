import { useRef, useState, type FormEvent } from 'react'
import { registerUser } from '../api/client'
import type { SessionState } from '../types'
import { saveSession } from '../utils/session'
import {
  canSubmitOnboarding,
  getNextOnboardingStep,
  getPreviousOnboardingStep,
  ONBOARDING_RULES,
  ONBOARDING_STEPS,
  ONBOARDING_TARGETS,
  submitOnboarding,
  validateOnboardingIdentity,
  type OnboardingStep,
} from '../utils/onboarding'
import './OnboardingWizard.css'

export interface OnboardingWizardProps {
  onSuccess: (session: SessionState) => void
}

export default function OnboardingWizard({
  onSuccess,
}: OnboardingWizardProps) {
  const [step, setStep] = useState<OnboardingStep>(1)
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const submissionInFlight = useRef(false)

  const handleNext = () => {
    if (isLoading) return

    const validationError = validateOnboardingIdentity(username, email)
    if (validationError) {
      setErrorMessage(validationError)
      return
    }

    const nextStep = getNextOnboardingStep(step)
    if (!nextStep) return

    setErrorMessage(null)
    setStep(nextStep)
  }

  const handleBack = () => {
    if (isLoading) return

    const previousStep = getPreviousOnboardingStep(step)
    if (!previousStep) return

    setErrorMessage(null)
    setStep(previousStep)
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    if (!canSubmitOnboarding(step) || submissionInFlight.current) {
      return
    }

    const validationError = validateOnboardingIdentity(username, email)
    if (validationError) {
      setErrorMessage(validationError)
      return
    }

    submissionInFlight.current = true
    setIsLoading(true)
    setErrorMessage(null)

    try {
      const sessionPayload = await submitOnboarding(
        step,
        username,
        email,
        registerUser
      )
      if (!sessionPayload) return

      saveSession(sessionPayload)
      onSuccess(sessionPayload)
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Registration failed. Please try again.'
      setErrorMessage(message)
    } finally {
      submissionInFlight.current = false
      setIsLoading(false)
    }
  }

  return (
    <div
      className="onboarding-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="onboarding-title"
      aria-describedby="onboarding-subtitle"
    >
      <div className="onboarding-card">
        <header className="onboarding-header">
          <h1 id="onboarding-title" className="onboarding-title">
            Promptocalypse
          </h1>
          <p id="onboarding-subtitle" className="onboarding-subtitle">
            AI JAILBREAK ARENA // PARTICIPANT ONBOARDING
          </p>
        </header>

        <nav aria-label="Onboarding progress" className="onboarding-progress">
          <ol className="onboarding-steps">
            {ONBOARDING_STEPS.map((onboardingStep) => {
              const isActive = step === onboardingStep.id
              const isComplete = step > onboardingStep.id
              const className = [
                'onboarding-step-indicator',
                isActive ? 'onboarding-step-indicator--active' : '',
                isComplete ? 'onboarding-step-indicator--complete' : '',
              ]
                .filter(Boolean)
                .join(' ')

              return (
                <li
                  key={onboardingStep.id}
                  className={className}
                  aria-current={isActive ? 'step' : undefined}
                >
                  <span className="onboarding-step-number">
                    {isComplete ? '✓' : onboardingStep.id}
                  </span>
                  <span>{onboardingStep.label}</span>
                </li>
              )
            })}
          </ol>
        </nav>

        <form className="onboarding-form" onSubmit={handleSubmit} noValidate>
          {step === 1 && (
            <section className="onboarding-step" aria-labelledby="identity-heading">
              <div className="onboarding-step-heading">
                <span className="onboarding-kicker">STEP 01 // IDENTITY</span>
                <h2 id="identity-heading">Choose your participant handle</h2>
                <p>
                  This handle identifies you on the leaderboard and in the arena
                  telemetry. Email is optional for registration.
                </p>
              </div>

              <div className="onboarding-field">
                <label className="onboarding-label" htmlFor="onboarding-username">
                  Participant username / handle
                </label>
                <input
                  id="onboarding-username"
                  type="text"
                  className="onboarding-input"
                  placeholder="e.g. Neo or Alex Mercer"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  disabled={isLoading}
                  autoFocus
                  autoComplete="username"
                  spellCheck={false}
                  maxLength={50}
                  required
                />
              </div>

              <div className="onboarding-field">
                <label className="onboarding-label" htmlFor="onboarding-email">
                  Email address <span>(optional)</span>
                </label>
                <input
                  id="onboarding-email"
                  type="email"
                  className="onboarding-input"
                  placeholder="participant@example.com"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  disabled={isLoading}
                  autoComplete="email"
                />
              </div>

              <p className="onboarding-note">
                You can continue with a handle alone. If supplied, use an email
                address you control.
              </p>
            </section>
          )}

          {step === 2 && (
            <section className="onboarding-step" aria-labelledby="briefing-heading">
              <div className="onboarding-step-heading">
                <span className="onboarding-kicker">STEP 02 // BRIEFING</span>
                <h2 id="briefing-heading">Three targets are in scope</h2>
                <p>
                  The arena contains 3 targets. You may attempt them in any
                  order, so choose the breach path that fits your approach.
                </p>
              </div>

              <ul className="onboarding-target-list">
                {ONBOARDING_TARGETS.map((target) => (
                  <li key={target.name} className="onboarding-target">
                    <strong>{target.name}</strong>
                    <span>{target.description}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {step === 3 && (
            <section className="onboarding-step" aria-labelledby="rules-heading">
              <div className="onboarding-step-heading">
                <span className="onboarding-kicker">STEP 03 // RULES</span>
                <h2 id="rules-heading">Rules of engagement</h2>
                <p>
                  Review these constraints before acknowledging the run. The
                  authoritative timer begins only after registration succeeds.
                </p>
              </div>

              <ul className="onboarding-rule-list">
                {ONBOARDING_RULES.map((rule) => (
                  <li key={rule.label} className="onboarding-rule">
                    <div className="onboarding-rule-header">
                      <strong>{rule.label}</strong>
                      <span>{rule.value}</span>
                    </div>
                    <p>{rule.detail}</p>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {errorMessage && (
            <div className="onboarding-error" role="alert">
              {errorMessage}
            </div>
          )}

          <div className="onboarding-actions">
            <button
              type="button"
              className="onboarding-button onboarding-button--secondary"
              onClick={handleBack}
              disabled={step === 1 || isLoading}
            >
              Back
            </button>
            {step < 3 ? (
              <button
                type="button"
                className="onboarding-button onboarding-button--primary"
                onClick={handleNext}
                disabled={isLoading}
              >
                Next
              </button>
            ) : (
              <button
                type="submit"
                className="onboarding-button onboarding-button--primary"
                disabled={isLoading || submissionInFlight.current}
              >
                {isLoading ? 'INITIALIZING SESSION...' : 'Acknowledge & Start Timer'}
              </button>
            )}
          </div>
        </form>

        <footer className="onboarding-footer">
          The arena remains locked until you acknowledge the rules.
        </footer>
      </div>
    </div>
  )
}
