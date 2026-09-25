import re

with open("frontend/src/components/Header.tsx", "r") as f:
    content = f.read()

import_stmt = "import { useState, useEffect, useMemo } from 'react'"
new_import_stmt = "import { useState, useEffect, useMemo } from 'react'\nimport { setActiveLevel } from '../api/client'\nimport { saveSession } from '../utils/session'"
content = content.replace(import_stmt, new_import_stmt)

# Update currentLevel -> activeLevel
content = content.replace("const currentLevel = internalSession.active_level ?? 1", "const activeLevel = internalSession.active_level ?? 1\n  const clearedLevels = internalSession.cleared_levels ?? []")
content = content.replace("currentLevel > lvl", "clearedLevels.includes(lvl)")
content = content.replace("currentLevel === lvl", "activeLevel === lvl")
content = content.replace("currentLevel < lvl", "!clearedLevels.includes(lvl) && activeLevel !== lvl")

# Update tabs rendering
old_nav = """          return (
            <div
              key={lvl}
              className={stepClass}
              title={`Level ${lvl}: ${ariaStatus}`}
              aria-current={isActive ? 'step' : undefined}
            >
              <span className="hud-step__icon">{icon}</span>
              <span className="hud-step__label">LVL {lvl}</span>
            </div>
          )"""

new_nav = """          const targetNames = ["RefundBot", "SysAdmin", "Blackout"]
          return (
            <button
              key={lvl}
              className={stepClass}
              title={`Level ${lvl}: ${ariaStatus}`}
              aria-current={isActive ? 'step' : undefined}
              onClick={() => {
                if (!completed && internalSession.user_id && activeLevel !== lvl) {
                   setActiveLevel(internalSession.user_id, lvl)
                   const updated = { ...internalSession, active_level: lvl }
                   saveSession(updated)
                   setInternalSession(updated)
                }
              }}
              disabled={completed}
              style={{ background: 'transparent', border: 'none', cursor: completed ? 'default' : 'pointer' }}
            >
              <span className="hud-step__icon">{icon}</span>
              <span className="hud-step__label">Target {lvl}: {targetNames[lvl - 1]}</span>
            </button>
          )"""

content = content.replace(old_nav, new_nav)

with open("frontend/src/components/Header.tsx", "w") as f:
    f.write(content)
