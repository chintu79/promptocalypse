import re

with open("backend/app/routes/chat.py", "r") as f:
    content = f.read()

old_query = """                "SELECT current_level, completed_at, start_time, total_prompts, failed_attempts FROM users WHERE id = ?","""
new_query = """                "SELECT active_level, cleared_levels, completed_at, start_time, total_prompts, failed_attempts FROM users WHERE id = ?","""
content = content.replace(old_query, new_query)

old_time_check = """            if elapsed_minutes(user_row["start_time"], now_iso) >= 120:
                final_score = calculate_final_score(
                    user_row["total_prompts"], 120, user_row["failed_attempts"]
                )
                await db.execute(
                    "UPDATE users SET completed_at = ?, final_score = ? WHERE id = ?",
                    (now_iso, final_score, request.user_id)
                )
                await db.commit()
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Time limit exceeded. Arena locked.",
                )

            level = user_row["current_level"]"""

new_time_check = """            import json
            cleared_levels = json.loads(user_row["cleared_levels"]) if user_row["cleared_levels"] else []
            if elapsed_minutes(user_row["start_time"], now_iso) >= 120:
                final_score = calculate_final_score(
                    len(cleared_levels), user_row["total_prompts"], 120, user_row["failed_attempts"]
                )
                await db.execute(
                    "UPDATE users SET completed_at = ?, final_score = ? WHERE id = ?",
                    (now_iso, final_score, request.user_id)
                )
                await db.commit()
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Time limit exceeded. Arena locked.",
                )

            level = user_row["active_level"]"""

content = content.replace(old_time_check, new_time_check)

with open("backend/app/routes/chat.py", "w") as f:
    f.write(content)
