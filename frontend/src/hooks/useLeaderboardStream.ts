import { useState, useEffect } from 'react';
import type { LeaderboardEntry } from '../types';
import { API_BASE } from '../api/client';

export function useLeaderboardStream(enabled: boolean = true) {
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);

  useEffect(() => {
    if (!enabled) return;

    const eventSource = new EventSource(`${API_BASE}/leaderboard/stream`);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setLeaderboard(data);
      } catch (err) {
        console.error('Failed to parse leaderboard SSE data', err);
      }
    };

    eventSource.onerror = (err) => {
      console.error('SSE Error:', err);
      // EventSource auto-reconnects
    };

    return () => {
      eventSource.close();
    };
  }, [enabled]);

  return leaderboard;
}
