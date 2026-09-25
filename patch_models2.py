import re

with open("backend/app/models.py", "r") as f:
    content = f.read()

old_reg = """class RegisterResponse(BaseModel):
    user_id: str
    username: str
    email: Optional[str] = None
    current_level: int = 1
    start_time: str
    total_prompts: int = 0
    failed_attempts: int = 0
    completed: bool = False"""

new_reg = """class RegisterResponse(BaseModel):
    user_id: str
    username: str
    email: Optional[str] = None
    active_level: int = 1
    cleared_levels: list[int] = []
    start_time: str
    total_prompts: int = 0
    failed_attempts: int = 0
    completed: bool = False"""

content = content.replace(old_reg, new_reg)

with open("backend/app/models.py", "w") as f:
    f.write(content)
