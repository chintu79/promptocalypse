import type { SubmitKeyResponse, User } from '../types'
import type { ChatFailureKind } from '../utils/chatFeedback'

export const API_BASE =
  (import.meta.env?.VITE_API_BASE as string | undefined) || '/api';

export async function registerUser(
  username: string,
  email?: string
): Promise<User> {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, email }),
  })
  if (!res.ok) {
    const errorData = (await res.json().catch(() => ({}))) as {
      detail?: string
    }
    throw new Error(errorData.detail || 'Sign-in failed')
  }
  return (await res.json()) as User
}

/** Chat API response body (upstream/main). */
export interface ChatApiResponse {
  reply: string;
  status?: 'success' | 'blocked' | string;
  latency_ms?: number;
  cooldown_seconds?: number;
}

export interface ChatPromptResponse extends ChatApiResponse {
  /**
   * Round-trip latency in ms parsed from the X-Process-Time response header.
   * null when the header is absent — the value is never fabricated.
   */
  latencyMs: number | null
}

/**
 * Typed failure for POST /api/chat:
 * - HTTP 429 → kind 'rate_limit' (submission stays disabled for the cooldown),
 * - HTTP 502 / network transport failure → kind 'gateway' (user may retry).
 */
export class ChatPromptError extends Error {
  readonly kind: ChatFailureKind
  readonly status?: number
  readonly latencyMs?: number | null

  constructor(
    message: string,
    kind: ChatFailureKind,
    options: { status?: number; latencyMs?: number | null } = {}
  ) {
    super(message)
    this.name = 'ChatPromptError'
    this.kind = kind
    this.status = options.status
    this.latencyMs = options.latencyMs
  }
}

// Backend middleware sends X-Process-Time as "<value>ms" (e.g. "420.31ms").
const PROCESS_TIME_PATTERN = /^(\d+(?:\.\d+)?)\s*ms$/i

/**
 * Parses the X-Process-Time response header into milliseconds.
 * Returns null when the header is missing or unparseable (no fabrication).
 */
export function parseProcessTime(headerValue: string | null): number | null {
  if (!headerValue) {
    return null
  }
  const match = PROCESS_TIME_PATTERN.exec(headerValue.trim())
  if (!match) {
    return null
  }
  const ms = Number(match[1])
  return Number.isFinite(ms) ? ms : null
}

export async function sendPrompt(
  userId: string,
  prompt: string
): Promise<ChatPromptResponse> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, prompt }),
    })
  } catch {
    // Transport-level network failure: no HTTP response was received.
    throw new ChatPromptError(
      'Network failure while contacting the inference gateway',
      'gateway'
    )
  }

  const latencyMs = parseProcessTime(res.headers.get('X-Process-Time'))

  if (res.status === 400) {
    const errorData = (await res.json().catch(() => ({}))) as {
      detail?: string
    }
    const detail = errorData.detail || ''
    if (detail.includes('Ingress inspection')) {
      return {
        reply: detail,
        status: 'blocked',
        latencyMs,
      }
    }
    const err = new Error(detail || 'Chat request failed with status 400') as Error & {
      status?: number
      detail?: string
    }
    err.status = 400
    err.detail = detail
    throw err
  }
  if (res.status === 429) {
    throw new ChatPromptError('Rate limit active', 'rate_limit', {
      status: 429,
      latencyMs,
    })
  }
  if (res.status === 502) {
    throw new ChatPromptError('Inference gateway timeout', 'gateway', {
      status: 502,
      latencyMs,
    })
  }
  if (!res.ok) {
    const errorData = (await res.json().catch(() => ({}))) as {
      detail?: string
    }
    // Preserve upstream's status/detail attachment so formatErrorAlert can
    // still classify non-429/502 HTTP failures (404, 400, ...).
    const err = new Error(
      errorData.detail || `Chat request failed with status ${res.status}`
    ) as Error & { status?: number; detail?: string }
    err.status = res.status
    err.detail = errorData.detail
    throw err
  }

  const data = (await res.json()) as ChatApiResponse
  return { ...data, latencyMs }
}

export async function submitKey(
  userId: string,
  key: string,
  level: number
): Promise<SubmitKeyResponse> {
  const res = await fetch(`${API_BASE}/submit-key`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, key, level }),
  })
  if (!res.ok) {
    const errorData = (await res.json().catch(() => ({}))) as {
      detail?: string
    }
    throw new Error(errorData.detail || 'Key submission failed')
  }
  return (await res.json()) as SubmitKeyResponse
}

export async function fetchLeaderboard(): Promise<import('../types').LeaderboardEntry[]> {
  const res = await fetch(`${API_BASE}/leaderboard`);
  if (!res.ok) {
    const errorData = (await res.json().catch(() => ({}))) as {
      detail?: string
    }
    throw new Error(errorData.detail || 'Failed to fetch leaderboard');
  }
  return (await res.json()) as import('../types').LeaderboardEntry[];
}

export async function fetchUserState(userId: string): Promise<User> {
  const res = await fetch(
    `${API_BASE}/user/state?user_id=${encodeURIComponent(userId)}`
  )
  if (!res.ok) {
    const errorData = (await res.json().catch(() => ({}))) as {
      detail?: string
    }
    throw new Error(errorData.detail || 'Failed to fetch user state')
  }
  return (await res.json()) as User
}

export interface ScenarioData {
  level: number;
  target: string;
  scenario: string;
  attack_vector: string;
}

export async function fetchScenario(level: number): Promise<ScenarioData> {
  const res = await fetch(`${API_BASE}/scenario/${level}`);
  if (!res.ok) {
    const errorData = (await res.json().catch(() => ({}))) as {
      detail?: string
    }
    throw new Error(errorData.detail || `Failed to fetch scenario for level ${level}`);
  }
  return (await res.json()) as ScenarioData;
}

export async function setActiveLevel(userId: string, level: number): Promise<void> {
  const res = await fetch(`${API_BASE}/auth/active-level`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, level }),
  })
  if (!res.ok) {
    console.error('Failed to set active level')
  }
}
