import re

with open("backend/app/models.py", "r") as f:
    content = f.read()

old_skr = """class SubmitKeyRequest(BaseModel):
    user_id: str = Field(..., description="Unique participant ID")
    key: str = Field(..., description="Extracted secret flag key")"""

new_skr = """class SubmitKeyRequest(BaseModel):
    user_id: str = Field(..., description="Unique participant ID")
    level: int = Field(..., description="The level this key is for")
    key: str = Field(..., description="Extracted secret flag key")"""

content = content.replace(old_skr, new_skr)

with open("backend/app/models.py", "w") as f:
    f.write(content)
