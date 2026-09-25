import re

with open("backend/app/routes/game.py", "r") as f:
    content = f.read()

old_call = """        result = await verify_and_progress(
            db=db, user_id=request.user_id, submitted_key=request.key
        )"""

new_call = """        result = await verify_and_progress(
            db=db, user_id=request.user_id, level=request.level, submitted_key=request.key
        )"""

content = content.replace(old_call, new_call)

with open("backend/app/routes/game.py", "w") as f:
    f.write(content)
