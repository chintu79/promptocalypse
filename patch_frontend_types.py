import re

with open("frontend/src/types/index.ts", "r") as f:
    content = f.read()

old_session = """export interface SessionState {
  user_id?: string
  username?: string
  email?: string | null
  current_level?: int
  start_time?: string
  total_prompts?: int
  failed_attempts?: int
  completed?: boolean
  final_score?: float | null
}"""

new_session = """export interface SessionState {
  user_id?: string
  username?: string
  email?: string | null
  active_level?: number
  cleared_levels?: number[]
  start_time?: string
  total_prompts?: number
  failed_attempts?: number
  completed?: boolean
  final_score?: number | null
}"""

# Handle potential "int" vs "number" in TypeScript
content = content.replace("current_level?: number", "active_level?: number\n  cleared_levels?: number[]")
content = content.replace("current_level: number", "active_level: number\n  cleared_levels: number[]")

with open("frontend/src/types/index.ts", "w") as f:
    f.write(content)
