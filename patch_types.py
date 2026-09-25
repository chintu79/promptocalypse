import re

with open("frontend/src/types/index.ts", "r") as f:
    content = f.read()

old_res = """export interface SubmitKeyResponse {
  status: 'correct' | 'incorrect' | 'completed' | string;
  unlocked_level?: number;
  message: string;
  penalty_points?: number;
  final_score?: number;
  completion_time?: string;
  stats?: {
    total_total_prompts: number;
    elapsed_minutes: number;
    failed_attempts: number;
  };
}"""

new_res = """export interface SubmitKeyResponse {
  status: 'correct' | 'incorrect' | 'completed' | string;
  unlocked_level?: number;
  cleared_levels?: number[];
  message: string;
  penalty_points?: number;
  final_score?: number;
  completion_time?: string;
  stats?: {
    total_total_prompts: number;
    elapsed_minutes: number;
    failed_attempts: number;
  };
}"""

content = content.replace(old_res, new_res)

with open("frontend/src/types/index.ts", "w") as f:
    f.write(content)
