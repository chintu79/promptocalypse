import re

with open("frontend/src/components/KeyVault.tsx", "r") as f:
    content = f.read()

old_success = """      if (response.status === 'correct' && response.unlocked_level) {
        // Intermediate success
        const nextLevel = response.unlocked_level
        setStatusMessage({ text: response.message, type: 'success' })
        setTimeout(() => {
          setKeyInput('')
          setIsSubmitting(false)
          setStatusMessage(null)
          // Progress level
          saveSession({
            ...session,
            active_level: nextLevel,
          })
        }, 1500)
        return
      }

      if (response.status === 'completed' && typeof response.final_score === 'number') {
        // Final completion
        setStatusMessage({ text: response.message, type: 'success' })
        triggerVictoryConfetti()

        const updatedSession = {
          ...session,
          completed: true,
          active_level: 3,
          final_score: response.final_score,
        }"""

new_success = """      if (response.status === 'correct' && response.cleared_levels) {
        // Intermediate success
        setStatusMessage({ text: response.message, type: 'success' })
        setTimeout(() => {
          setKeyInput('')
          setIsSubmitting(false)
          setStatusMessage(null)
          // Progress level
          saveSession({
            ...session,
            cleared_levels: response.cleared_levels,
          })
        }, 1500)
        return
      }

      if (response.status === 'completed' && typeof response.final_score === 'number') {
        // Final completion
        setStatusMessage({ text: response.message, type: 'success' })
        triggerVictoryConfetti()

        const updatedSession = {
          ...session,
          completed: true,
          cleared_levels: response.cleared_levels || [1, 2, 3],
          final_score: response.final_score,
        }"""

content = content.replace(old_success, new_success)
content = content.replace("currentLevel: number", "activeLevel: number")

with open("frontend/src/components/KeyVault.tsx", "w") as f:
    f.write(content)
