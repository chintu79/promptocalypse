import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const wizard = readFileSync(
  new URL('./OnboardingWizard.tsx', import.meta.url),
  'utf8'
)
const app = readFileSync(new URL('../App.tsx', import.meta.url), 'utf8')

describe('OnboardingWizard interaction contract', () => {
  it('renders clear step navigation and the exact final action', () => {
    assert.match(wizard, /aria-label="Onboarding progress"/)
    assert.match(wizard, /Back\s*</)
    assert.match(wizard, /Next\s*</)
    assert.match(wizard, /Acknowledge & Start Timer/)
  })

  it('keeps registration out of the Next handler and in the final submit path', () => {
    const nextStart = wizard.indexOf('const handleNext')
    const backStart = wizard.indexOf('const handleBack')
    const submitStart = wizard.indexOf('const handleSubmit')
    assert.ok(nextStart >= 0)
    assert.ok(backStart > nextStart)
    assert.ok(submitStart > backStart)

    const nextHandler = wizard.slice(nextStart, backStart)
    assert.doesNotMatch(nextHandler, /submitOnboarding|registerUser/)
    assert.match(wizard.slice(submitStart), /submitOnboarding/)
    assert.match(wizard.slice(submitStart), /submissionInFlight\.current/)
  })

  it('exposes loading and API error states', () => {
    assert.match(wizard, /setIsLoading\(true\)/)
    assert.match(wizard, /INITIALIZING SESSION\.\.\./)
    assert.match(wizard, /setErrorMessage\(message\)/)
    assert.match(wizard, /role="alert"/)
  })

  it('mounts the arena and timer only inside the authenticated branch', () => {
    assert.match(
      app,
      /!isAuthenticated \? \(\s*<OnboardingWizard[\s\S]*?\) : \(\s*<>\s*<Header session=\{session\} \/>/
    )
    assert.doesNotMatch(app, /getOrCreateDefaultSession/)
  })
})
