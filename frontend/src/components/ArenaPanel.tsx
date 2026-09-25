import ScenarioBriefing from "./ScenarioBriefing"
import ChatTerminal from './ChatTerminal'
import type { SessionState } from '../types'
import { loadSession } from '../utils/session'
import { sendPrompt } from '../api/client'

interface ArenaPanelProps {
  session?: SessionState | null
}

/**
 * ArenaPanel wraps the ChatTerminal and connects it to the backend chat API.
 */
export default function ArenaPanel({ session }: ArenaPanelProps) {
  const currentSession = session ?? loadSession()
  const userId = currentSession?.user_id || ''
  const currentLevel = currentSession?.active_level || 1

  const handleSendPrompt = async (prompt: string) => {
    if (!userId) {
      throw new Error('Authentication required: please register or sign in.')
    }
    return await sendPrompt(userId, prompt)
  }

  return (
    <div className="arena-panel-inner" style={{ display: 'flex', flexDirection: 'column', height: '100%', flex: 1 }}>
      <ScenarioBriefing currentLevel={currentLevel} />
      <div className="flex-1 min-h-0" style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
        <ChatTerminal
          userId={userId}
          currentLevel={currentLevel}
          onSendPrompt={handleSendPrompt}
        />
      </div>
    </div>
  )
}
