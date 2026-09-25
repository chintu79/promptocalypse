export interface User {
  user_id: string;
  username: string;
  email?: string;
  active_level: number
  cleared_levels: number[];
  start_time: string;
  total_prompts: number;
  failed_attempts: number;
  completed: boolean;
  status?: string;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant' | 'system_alert' | 'bot' | 'system';
  content: string;
  text?: string;
  timestamp: string | number;
  latency_ms?: number;
  status?: 'success' | 'blocked' | 'error';
  isBlocked?: boolean;
  level?: number;
}

export interface LeaderboardEntry {
  rank: number;
  username: string;
  active_level: number
  cleared_levels: number[];
  final_score: number;
  total_prompts: number;
  total_chars: number;
  completed: boolean;
  status?: string;
}

export interface SessionState {
  user_id: string;
  username: string;
  email?: string;
  active_level: number
  cleared_levels: number[];
  active_cooldown_until?: number | null;
  local_chat_history?: Record<string, ChatMessage[]>;
  start_time?: string;
  total_prompts?: number;
  total_chars?: number;
  failed_attempts?: number;
  completed?: boolean;
  final_score?: number;
  cached_at?: number;
}

export interface SubmitKeyResponse {
  status: 'correct' | 'incorrect' | 'completed' | string;
  unlocked_level?: number;
  cleared_levels?: number[];
  message: string;
  penalty_points?: number;
  final_score?: number;
  completion_time?: string;
  stats?: {
    total_prompts: number;
    elapsed_minutes: number;
    failed_attempts: number;
  };
}

