import { useState, useEffect } from 'react'
import Header from './components/Header.tsx'
import ArenaPanel from './components/ArenaPanel.tsx'
import SidePanel from './components/SidePanel.tsx'
import RightDrawer from './components/RightDrawer.tsx'
import VictoryModal from './components/VictoryModal.tsx'
import OnboardingWizard from './components/OnboardingWizard.tsx'
import type { SessionState, SubmitKeyResponse } from './types'
import { loadSession, hasValidSession, SESSION_UPDATE_EVENT, saveSession, calculateDynamicScore } from './utils/session'

export default function App() {
  const [session, setSession] = useState<SessionState | null>(() => {
    return loadSession()
  })
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => {
    return hasValidSession()
  })

  useEffect(() => {
    const handleTimeout = () => {
      const current = loadSession()
      if (current && !current.completed) {
        const finalScore = calculateDynamicScore({
          prompts: current.total_prompts || 0,
          elapsedSeconds: 7200,
          failedAttempts: current.failed_attempts || 0,
        })
        const updated = { ...current, completed: true, final_score: finalScore }
        saveSession(updated)
        setSession(updated)
        setShowVictory(true)
        setFinalScore(finalScore)
        setVictoryStats({
          base_points: 1000,
          total_prompts: current.total_prompts || 0,
          prompt_penalty: 0,
          elapsed_minutes: 120,
          time_penalty: 120 * 2,
          failed_attempts: current.failed_attempts || 0,
          fail_penalty: (current.failed_attempts || 0) * 25,
          final_score: finalScore
        })
      }
    }
    window.addEventListener('ARENA_TIMEOUT', handleTimeout)
    return () => window.removeEventListener('ARENA_TIMEOUT', handleTimeout)
  }, [])

  useEffect(() => {
    const handleUpdate = (e: Event) => {
      const customEvent = e as CustomEvent<SessionState | null>
      if (customEvent.detail) {
        setSession(customEvent.detail)
        setIsAuthenticated(hasValidSession())
      } else {
        const reloaded = loadSession()
        setSession(reloaded)
        setIsAuthenticated(hasValidSession())
      }
    }
    window.addEventListener(SESSION_UPDATE_EVENT, handleUpdate)
    window.addEventListener('storage', handleUpdate)
    return () => {
      window.removeEventListener(SESSION_UPDATE_EVENT, handleUpdate)
      window.removeEventListener('storage', handleUpdate)
    }
  }, [])
  const [showVictory, setShowVictory] = useState<boolean>(() => {
    const s = loadSession()
    return Boolean(s?.completed)
  })
  const [leaderboardOpen, setLeaderboardOpen] = useState<boolean>(false)
  const [victoryStats, setVictoryStats] = useState<SubmitKeyResponse['stats'] | null>(null)
  const [finalScore, setFinalScore] = useState<number | null>(() => {
    const s = loadSession()
    return s?.final_score ?? null
  })

  const handleAuthenticated = (newSession: SessionState) => {
    setSession(newSession)
    setIsAuthenticated(true)
    if (newSession.completed) {
      setShowVictory(true)
    }
  }

  const handleVictory = (res: SubmitKeyResponse) => {
    setShowVictory(true)
    setVictoryStats(res.stats || null)
    setFinalScore(res.final_score ?? null)
  }

  return (
    <div className="app-container">
      {!isAuthenticated ? (
        <OnboardingWizard onSuccess={handleAuthenticated} />
      ) : (
        <>
          <Header session={session} onToggleLeaderboard={() => setLeaderboardOpen((o) => !o)} />
          <main className="main-content">
            <ArenaPanel session={session} />
            <SidePanel onVictory={handleVictory} session={session} />
          </main>
          <RightDrawer
            open={leaderboardOpen}
            onToggle={() => setLeaderboardOpen((o) => !o)}
          />
          {showVictory && (
            <VictoryModal
              isOpen={showVictory}
              onClose={() => setShowVictory(false)}
              stats={victoryStats}
              finalScore={finalScore}
            />
          )}
        </>
      )}
    </div>
  )
}
