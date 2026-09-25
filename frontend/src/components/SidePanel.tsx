import KeyVault from './KeyVault'
import ScenarioBriefing from './ScenarioBriefing'
import type { SubmitKeyResponse, SessionState } from '../types'
import { loadSession } from '../utils/session'

interface SidePanelProps {
  onVictory?: (response: SubmitKeyResponse) => void
  session?: SessionState | null
}

export default function SidePanel({ onVictory, session }: SidePanelProps) {
  const currentSession = session ?? loadSession()
  const currentLevel = currentSession?.active_level || 1

  return (
    <aside
      style={{
        flex: '0 0 20%',
        width: '20%',
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem',
        padding: '1rem',
        backgroundColor: '#12151f',
        overflowY: 'auto',
      }}
    >
      {/* Level Info */}
      <ScenarioBriefing currentLevel={currentLevel} />

      {/* Mission objective card */}
      <div
        style={{
          backgroundColor: '#1c2132',
          border: '1px solid #262d43',
          borderRadius: '4px',
          padding: '1rem',
        }}
      >
        <h3
          style={{
            color: '#00ff9d',
            fontSize: '0.95rem',
            marginBottom: '0.5rem',
            fontFamily: "'JetBrains Mono', monospace",
            textTransform: 'uppercase',
          }}
        >
          Mission Objective
        </h3>
        <p style={{ color: '#f0f4fc', fontSize: '0.85rem', lineHeight: '1.4' }}>
          Extract the secret key from the defense system without triggering security tripwires.
        </p>
      </div>

      {/* Key submission vault component */}
      <KeyVault onVictory={onVictory} />
    </aside>
  )
}
