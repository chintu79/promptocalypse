import { useEffect, useState } from 'react'
import type { LeaderboardEntry } from '../types'
import { fetchLeaderboard } from '../api/client'
import './RightDrawer.css'

interface RightDrawerProps {
  open: boolean
  onToggle: () => void
}

// Issue #57: poll only while the drawer is open — each open fetches fresh ranks,
// so a closed drawer costs zero leaderboard requests.
const POLL_MS = 10000

export default function RightDrawer({ open, onToggle }: RightDrawerProps) {
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([])

  useEffect(() => {
    if (!open) return
    let timeoutId: ReturnType<typeof setTimeout>

    const poll = () => {
      fetchLeaderboard().then(setLeaderboard).catch(console.error)
      const jitter = Math.random() * 5000
      timeoutId = setTimeout(poll, POLL_MS + jitter)
    }

    poll()

    return () => clearTimeout(timeoutId)
  }, [open])

  return (
    <aside
      id="leaderboard-drawer"
      className={`right-drawer${open ? ' right-drawer--open' : ''}`}
      aria-hidden={!open}
    >
      <div className="right-drawer__header">
        <h3 className="right-drawer__title">Leaderboard</h3>
        <button
          type="button"
          onClick={onToggle}
          style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '1.2rem', lineHeight: '1' }}
          aria-label="Close Leaderboard"
        >
          &times;
        </button>
      </div>

      <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem', fontFamily: "'JetBrains Mono', monospace", marginTop: '1rem' }}>
        {leaderboard.length === 0 ? (
          <p>No entries loaded.</p>
        ) : (
          <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {leaderboard.map(entry => (
              <li key={entry.username} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem', paddingBottom: '0.5rem', borderBottom: '1px solid var(--border)' }}>
                <span>
                  <strong>{entry.rank}. {entry.username}</strong>
                  <span style={{ marginLeft: '0.5rem', fontSize: '0.75rem', color: entry.completed ? 'var(--accent)' : 'var(--warning)', border: `1px solid ${entry.completed ? 'var(--accent)' : 'var(--warning)'}`, padding: '2px 4px', borderRadius: '4px' }}>
                    {entry.status || (entry.completed ? 'Completed' : 'In Progress')}
                  </span>
                </span>
                <span>{entry.final_score} pts</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  )
}
