import re

with open("backend/app/models.py", "r") as f:
    content = f.read()

old_session = """class SessionResponse(BaseModel):
    user_id: str
    username: str
    email: str | None = None
    current_level: int
    start_time: str
    total_prompts: int
    failed_attempts: int
    completed: bool
    final_score: float | None = None"""

new_session = """class SessionResponse(BaseModel):
    user_id: str
    username: str
    email: str | None = None
    active_level: int
    cleared_levels: list[int]
    start_time: str
    total_prompts: int
    failed_attempts: int
    completed: bool
    final_score: float | None = None"""

content = content.replace(old_session, new_session)

old_key_req = """class KeySubmissionRequest(BaseModel):
    key: str"""

new_key_req = """class KeySubmissionRequest(BaseModel):
    level: int
    key: str"""

content = content.replace(old_key_req, new_key_req)

with open("backend/app/models.py", "w") as f:
    f.write(content)
