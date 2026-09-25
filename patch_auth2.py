import re

with open("backend/app/routes/auth.py", "r") as f:
    content = f.read()

from_import = "from app.models import RegisterRequest, RegisterResponse"
new_from_import = """from pydantic import BaseModel
class SetLevelRequest(BaseModel):
    user_id: str
    level: int

from app.models import RegisterRequest, RegisterResponse"""

content = content.replace(from_import, new_from_import)

new_endpoint = """@router.put("/active-level")
async def set_active_level(request: SetLevelRequest):
    async with get_db_context() as db:
        await db.execute("UPDATE users SET active_level = ? WHERE id = ?", (request.level, request.user_id))
        await db.commit()
    return {"status": "ok"}
"""

content = content + "\n" + new_endpoint

with open("backend/app/routes/auth.py", "w") as f:
    f.write(content)
