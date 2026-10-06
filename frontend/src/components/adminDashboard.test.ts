import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const read = (file: string) => readFileSync(new URL(file, import.meta.url), 'utf8')
const adminDashboard = read('./AdminDashboard.tsx')

describe('Admin Dashboard implementation', () => {
  it('handles authentication state securely', () => {
    // Should check token presence
    assert.match(adminDashboard, /localStorage\.getItem\('admin_token'\)/)
    assert.match(adminDashboard, /localStorage\.setItem\('admin_token'/)
    assert.match(adminDashboard, /localStorage\.removeItem\('admin_token'\)/)
  })

  it('provides a login fallback when unauthenticated', () => {
    assert.match(adminDashboard, /if \(!token\)/)
    assert.match(adminDashboard, /Admin Login/)
    assert.match(adminDashboard, /<form onSubmit=\{handleLogin\}/)
  })

  it('renders the authenticated dashboard components', () => {
    assert.match(adminDashboard, /<h2>Admin Dashboard<\/h2>/)
    assert.match(adminDashboard, /Logout/)
    assert.match(adminDashboard, /<table/)
    assert.match(adminDashboard, /\{users\.map/)
  })

  it('interacts with the correct API endpoints', () => {
    assert.match(adminDashboard, /\/admin\/login/)
    assert.match(adminDashboard, /\/admin\/users/)
    assert.match(adminDashboard, /Authorization: `Bearer \$\{authToken\}`/)
  })
})
