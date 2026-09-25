import re
import json

with open("backend/app/routes/auth.py", "r") as f:
    content = f.read()

old_res1 = """            return RegisterResponse(
                user_id=user_dict["id"],
                username=user_dict["username"],
                email=user_dict.get("email"),
                current_level=user_dict["current_level"],
                start_time=user_dict["start_time"],
                total_prompts=user_dict["total_prompts"],
                failed_attempts=user_dict["failed_attempts"],
                completed=user_dict.get("completed_at") is not None,
            )"""

new_res1 = """            import json
            cleared_levels_str = user_dict.get("cleared_levels", "[]")
            try:
                cleared_levels = json.loads(cleared_levels_str)
            except Exception:
                cleared_levels = []
                
            return RegisterResponse(
                user_id=user_dict["id"],
                username=user_dict["username"],
                email=user_dict.get("email"),
                active_level=user_dict["active_level"],
                cleared_levels=cleared_levels,
                start_time=user_dict["start_time"],
                total_prompts=user_dict["total_prompts"],
                failed_attempts=user_dict["failed_attempts"],
                completed=user_dict.get("completed_at") is not None,
            )"""

content = content.replace(old_res1, new_res1)

old_insert = """        # 4. Create new participant profile
        new_id = f"usr_{uuid.uuid4()}"
        await db.execute(
            \"\"\"
            INSERT INTO users (
                id, username, email, current_level, start_time,
                total_prompts, total_chars, failed_attempts,
                final_score, is_disqualified
            ) VALUES (?, ?, ?, 1, ?, 0, 0, 0, 0.0, 0)
            \"\"\",
            (new_id, clean_username, clean_email, now_iso),
        )"""

new_insert = """        # 4. Create new participant profile
        new_id = f"usr_{uuid.uuid4()}"
        await db.execute(
            \"\"\"
            INSERT INTO users (
                id, username, email, active_level, cleared_levels, start_time,
                total_prompts, total_chars, failed_attempts,
                final_score, is_disqualified
            ) VALUES (?, ?, ?, 1, '[]', ?, 0, 0, 0, 0.0, 0)
            \"\"\",
            (new_id, clean_username, clean_email, now_iso),
        )"""

content = content.replace(old_insert, new_insert)

old_res2 = """        return RegisterResponse(
            user_id=new_id,
            username=clean_username,
            email=clean_email,
            current_level=1,
            start_time=now_iso,
            total_prompts=0,
            failed_attempts=0,
            completed=False,
        )"""

new_res2 = """        return RegisterResponse(
            user_id=new_id,
            username=clean_username,
            email=clean_email,
            active_level=1,
            cleared_levels=[],
            start_time=now_iso,
            total_prompts=0,
            failed_attempts=0,
            completed=False,
        )"""

content = content.replace(old_res2, new_res2)

with open("backend/app/routes/auth.py", "w") as f:
    f.write(content)
