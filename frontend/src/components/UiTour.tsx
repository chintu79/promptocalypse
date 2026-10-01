import { useEffect, useRef } from 'react'
import { driver, type DriveStep } from 'driver.js'
import 'driver.js/dist/driver.css'
import './UiTour.css'

const TOUR_STORAGE_KEY = 'th_tour_completed'

/**
 * Curated tour steps targeting existing CSS selectors in the arena UI.
 * Each step highlights a key region and explains its purpose.
 */
const TOUR_STEPS: DriveStep[] = [
  {
    element: '.hud-header',
    popover: {
      title: '🖥️ Command HUD',
      description:
        'This is your Heads-Up Display. It shows your identity, level selector, and live telemetry — everything you need at a glance.',
      side: 'bottom',
      align: 'center',
    },
  },
  {
    element: '.hud-steps',
    popover: {
      title: '🎯 Level Selector',
      description:
        'Three AI targets are in scope. Click any target to switch between them — you can tackle them in any order. A ✓ appears once a level is cleared.',
      side: 'bottom',
      align: 'center',
    },
  },
  {
    element: '.hud-telemetry',
    popover: {
      title: '📊 Live Telemetry',
      description:
        'Track your RANK, remaining TIME (120 min limit), PROMPT count, and live SCORE. Fewer prompts + faster time = higher score.',
      side: 'bottom',
      align: 'center',
    },
  },
  {
    element: '.chat-terminal',
    popover: {
      title: '💬 Chat Terminal',
      description:
        'This is where you interact with the AI target. The conversation history shows your prompts and the AI\'s responses. Watch for firewall intercepts and leak detections!',
      side: 'left',
      align: 'start',
    },
  },
  {
    element: '.chat-terminal__input-area',
    popover: {
      title: '⌨️ Prompt Input',
      description:
        'Type your attack prompt here. Press Enter or click Send. There\'s a 3-second cooldown between prompts, and each prompt after the 3rd costs 15 score points.',
      side: 'top',
      align: 'center',
    },
  },
  {
    element: '.scenario-briefing',
    popover: {
      title: '📋 Scenario Intel',
      description:
        'Read the briefing for each target — it reveals the target name, scenario context, and attack vector hint. This intel updates when you switch levels.',
      side: 'left',
      align: 'start',
    },
  },
  {
    element: '.vault-card',
    popover: {
      title: '🔐 Vault Key Submission',
      description:
        'Once you extract a secret key (FLAG{...}) from the AI, paste it here and click VERIFY KEY. Correct keys clear the level. Wrong keys cost 25 points each.',
      side: 'left',
      align: 'start',
    },
  },
]

export const TOUR_EVENT = 'th_replay_tour'

interface UiTourProps {
  /** Whether to auto-start the tour (only on first visit). */
  autoStart?: boolean
}

/**
 * UiTour — driver.js interactive walkthrough for the arena UI.
 *
 * Auto-starts once after registration. Can be replayed via the help button
 * which dispatches a custom `th_replay_tour` event.
 */
export default function UiTour({ autoStart = true }: UiTourProps) {
  const driverRef = useRef<ReturnType<typeof driver> | null>(null)

  useEffect(() => {
    // Create the driver instance
    driverRef.current = driver({
      showProgress: true,
      showButtons: ['next', 'previous', 'close'],
      steps: TOUR_STEPS,
      progressText: '{{current}} of {{total}}',
      nextBtnText: 'Next →',
      prevBtnText: '← Back',
      doneBtnText: 'Start Hacking!',
      onDestroyed: () => {
        // Mark tour as completed so it doesn't auto-replay
        localStorage.setItem(TOUR_STORAGE_KEY, '1')
      },
    })

    // Auto-start only if never completed before
    if (autoStart && !localStorage.getItem(TOUR_STORAGE_KEY)) {
      // Small delay to let all components mount and render
      const startTimer = setTimeout(() => {
        driverRef.current?.drive()
      }, 600)
      return () => clearTimeout(startTimer)
    }
  }, [autoStart])

  // Listen for replay events (from the "?" help button)
  useEffect(() => {
    const handleReplay = () => {
      driverRef.current?.drive()
    }
    window.addEventListener(TOUR_EVENT, handleReplay)
    return () => window.removeEventListener(TOUR_EVENT, handleReplay)
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      driverRef.current?.destroy()
    }
  }, [])

  // This component renders nothing — it's purely side-effect driven
  return null
}
