import re

with open("frontend/src/api/client.ts", "r") as f:
    content = f.read()

old_func = """export async function submitKey(
  userId: string,
  key: string
): Promise<SubmitKeyResponse> {
  const res = await fetch(`${API_BASE}/submit-key`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, key }),
  })"""

new_func = """export async function submitKey(
  userId: string,
  key: string,
  level: number
): Promise<SubmitKeyResponse> {
  const res = await fetch(`${API_BASE}/submit-key`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, key, level }),
  })"""

content = content.replace(old_func, new_func)

with open("frontend/src/api/client.ts", "w") as f:
    f.write(content)
