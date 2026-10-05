import { useState, useEffect } from 'react'
import { API_BASE } from '../api/client'

export default function AdminDashboard() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [token, setToken] = useState(localStorage.getItem('admin_token') || '')
  const [users, setUsers] = useState<any[]>([])
  const [error, setError] = useState('')

  const fetchUsers = async (authToken: string) => {
    try {
      const res = await fetch(`${API_BASE}/admin/users`, {
        headers: { Authorization: `Bearer ${authToken}` }
      })
      if (res.ok) {
        const data = await res.json()
        setUsers(data)
      } else {
        setError('Failed to fetch users')
        setToken('')
        localStorage.removeItem('admin_token')
      }
    } catch (e) {
      setError('Network error')
    }
  }

  useEffect(() => {
    if (token) {
      fetchUsers(token)
    }
  }, [token])

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    try {
      const res = await fetch(`${API_BASE}/admin/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      })
      if (res.ok) {
        const data = await res.json()
        setToken(data.token)
        localStorage.setItem('admin_token', data.token)
      } else {
        setError('Invalid credentials')
      }
    } catch (e) {
      setError('Network error')
    }
  }

  if (!token) {
    return (
      <div style={{ padding: '2rem', maxWidth: '400px', margin: '0 auto', color: 'var(--text)' }}>
        <h2>Admin Login</h2>
        {error && <div style={{ color: 'var(--warning)', marginBottom: '1rem' }}>{error}</div>}
        <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <input 
            type="text" 
            placeholder="Username" 
            value={username} 
            onChange={(e) => setUsername(e.target.value)} 
            style={{ padding: '0.5rem', background: 'var(--bg-secondary)', color: 'var(--text)', border: '1px solid var(--border)' }}
          />
          <input 
            type="password" 
            placeholder="Password" 
            value={password} 
            onChange={(e) => setPassword(e.target.value)}
            style={{ padding: '0.5rem', background: 'var(--bg-secondary)', color: 'var(--text)', border: '1px solid var(--border)' }}
          />
          <button type="submit" style={{ padding: '0.5rem', background: 'var(--accent)', color: '#000', border: 'none', cursor: 'pointer', fontWeight: 'bold' }}>
            Login
          </button>
        </form>
      </div>
    )
  }

  return (
    <div style={{ padding: '2rem', color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2>Admin Dashboard</h2>
        <button 
          onClick={() => { setToken(''); localStorage.removeItem('admin_token'); }}
          style={{ padding: '0.5rem 1rem', background: 'var(--bg-secondary)', color: 'var(--text)', border: '1px solid var(--border)', cursor: 'pointer' }}
        >
          Logout
        </button>
      </div>
      
      <table style={{ width: '100%', marginTop: '2rem', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ borderBottom: '2px solid var(--border)', textAlign: 'left' }}>
            <th style={{ padding: '0.5rem' }}>Rank</th>
            <th style={{ padding: '0.5rem' }}>Username</th>
            <th style={{ padding: '0.5rem' }}>Email</th>
            <th style={{ padding: '0.5rem' }}>Score</th>
            <th style={{ padding: '0.5rem' }}>Prompts</th>
            <th style={{ padding: '0.5rem' }}>Cleared Levels</th>
          </tr>
        </thead>
        <tbody>
          {users.map((user, i) => (
            <tr key={user.id} style={{ borderBottom: '1px solid var(--border)' }}>
              <td style={{ padding: '0.5rem' }}>{i + 1}</td>
              <td style={{ padding: '0.5rem' }}>{user.username}</td>
              <td style={{ padding: '0.5rem' }}>{user.email || 'N/A'}</td>
              <td style={{ padding: '0.5rem' }}>{user.final_score}</td>
              <td style={{ padding: '0.5rem' }}>{user.total_prompts}</td>
              <td style={{ padding: '0.5rem' }}>{user.cleared_levels}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
