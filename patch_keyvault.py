import re

with open("frontend/src/components/KeyVault.tsx", "r") as f:
    content = f.read()

old_prop = """  /** Optional custom verification handler (e.g. for testing/mocking) */
  onSubmitKey?: (userId: string, key: string) => Promise<SubmitKeyResponse>"""

new_prop = """  /** Optional custom verification handler (e.g. for testing/mocking) */
  onSubmitKey?: (userId: string, key: string, level: number) => Promise<SubmitKeyResponse>"""

content = content.replace(old_prop, new_prop)

old_call = """      const verifyFn = onSubmitKey || submitKey
      const response = await verifyFn(session.user_id, trimmed)"""

new_call = """      const verifyFn = onSubmitKey || submitKey
      const response = await verifyFn(session.user_id, trimmed, currentLevel)"""

content = content.replace(old_call, new_call)

with open("frontend/src/components/KeyVault.tsx", "w") as f:
    f.write(content)
