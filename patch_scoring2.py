import re
import json

with open("backend/app/scoring.py", "r") as f:
    content = f.read()

content = content.replace("BASE_SCORE = 1000", "BASE_SCORE_PER_LEVEL = 333")

old_calc_score = """def calculate_final_score(
    total_prompts: int,
    elapsed_minutes_: int,
    failed_attempts: int,
) -> float:
    \"\"\"
    Compute the scalar final score for a completed arena run.

    Penalties:
    - Prompts: 15 pts per prompt beyond the first 3 (free allowance).
    - Time: 2 pts per elapsed whole minute.
    - Failed keys: 25 pts per incorrect submission.

    The result is clamped at 0.0 and never negative.
    \"\"\"
    prompt_penalty = (
        max(0, total_prompts - PROMPT_FREE_ALLOWANCE) * PROMPT_PENALTY_PER_EXCESS
    )
    time_penalty = max(0, elapsed_minutes_) * TIME_PENALTY_PER_MINUTE
    fail_penalty = max(0, failed_attempts) * FAILED_KEY_PENALTY
    score = BASE_SCORE - prompt_penalty - time_penalty - fail_penalty
    return float(max(0, score))"""

new_calc_score = """def calculate_final_score(
    cleared_count: int,
    total_prompts: int,
    elapsed_minutes_: int,
    failed_attempts: int,
) -> float:
    \"\"\"
    Compute the scalar final score for a completed arena run.
    \"\"\"
    prompt_penalty = (
        max(0, total_prompts - PROMPT_FREE_ALLOWANCE) * PROMPT_PENALTY_PER_EXCESS
    )
    time_penalty = max(0, elapsed_minutes_) * TIME_PENALTY_PER_MINUTE
    fail_penalty = max(0, failed_attempts) * FAILED_KEY_PENALTY
    base_score = BASE_SCORE_PER_LEVEL * cleared_count
    score = base_score - prompt_penalty - time_penalty - fail_penalty
    return float(max(0, score))"""

content = content.replace(old_calc_score, new_calc_score)

old_breakdown = """def score_breakdown(
    total_prompts: int,
    elapsed_minutes_: int,
    failed_attempts: int,
) -> dict[str, Any]:
    \"\"\"Return the final score together with a per-category penalty breakdown.\"\"\"
    prompt_penalty = (
        max(0, total_prompts - PROMPT_FREE_ALLOWANCE) * PROMPT_PENALTY_PER_EXCESS
    )
    time_penalty = max(0, elapsed_minutes_) * TIME_PENALTY_PER_MINUTE
    fail_penalty = max(0, failed_attempts) * FAILED_KEY_PENALTY
    return {
        "base_points": BASE_SCORE,
        "total_prompts": total_prompts,
        "prompt_penalty": prompt_penalty,
        "elapsed_minutes": elapsed_minutes_,
        "time_penalty": time_penalty,
        "failed_attempts": failed_attempts,
        "fail_penalty": fail_penalty,
        "final_score": calculate_final_score(
            total_prompts, elapsed_minutes_, failed_attempts
        ),
    }"""

new_breakdown = """def score_breakdown(
    cleared_count: int,
    total_prompts: int,
    elapsed_minutes_: int,
    failed_attempts: int,
) -> dict[str, Any]:
    prompt_penalty = (
        max(0, total_prompts - PROMPT_FREE_ALLOWANCE) * PROMPT_PENALTY_PER_EXCESS
    )
    time_penalty = max(0, elapsed_minutes_) * TIME_PENALTY_PER_MINUTE
    fail_penalty = max(0, failed_attempts) * FAILED_KEY_PENALTY
    base_score = BASE_SCORE_PER_LEVEL * cleared_count
    return {
        "base_points": base_score,
        "total_prompts": total_prompts,
        "prompt_penalty": prompt_penalty,
        "elapsed_minutes": elapsed_minutes_,
        "time_penalty": time_penalty,
        "failed_attempts": failed_attempts,
        "fail_penalty": fail_penalty,
        "final_score": calculate_final_score(
            cleared_count, total_prompts, elapsed_minutes_, failed_attempts
        ),
    }"""
content = content.replace(old_breakdown, new_breakdown)

old_verify = """async def verify_and_progress(
    db: aiosqlite.Connection,
    user_id: str,
    submitted_key: str,
) -> dict[str, Any]:"""

new_verify = """async def verify_and_progress(
    db: aiosqlite.Connection,
    user_id: str,
    level: int,
    submitted_key: str,
) -> dict[str, Any]:
    import json"""

content = content.replace(old_verify, new_verify)

old_verify_body = """        cursor = await db.execute(
            \"\"\"
            SELECT current_level, start_time, total_prompts, failed_attempts,
                   completed_at
            FROM users WHERE id = ?
            \"\"\",
            (user_id,),
        )
        record = await cursor.fetchone()
        if record is None:
            await db.rollback()
            return {"status": STATUS_NOT_FOUND, "message": "User not found"}

        level = record["current_level"]
        start_time = record["start_time"]
        prompts = record["total_prompts"]
        fails = record["failed_attempts"]
        completed_at = record["completed_at"]

        if completed_at is not None:
            await db.rollback()
            return {
                "status": STATUS_ALREADY_COMPLETED,
                "message": "Challenge already completed",
            }

        # Issue #55: 120-minute global time limit
        if elapsed_minutes(start_time, now_iso) >= 120:
            final_score = calculate_final_score(prompts, 120, fails)
            await db.execute(
                "UPDATE users SET completed_at = ?, final_score = ? WHERE id = ?",
                (now_iso, final_score, user_id)
            )
            await db.commit()
            return {
                "status": "time_limit_exceeded",
                "message": "Time limit exceeded. Arena locked.",
            }

        target_key = LEVEL_KEYS[level]
        # Constant-time comparison prevents timing side-channels (FEATURES 3.1)
        is_correct = hmac.compare_digest(
            clean_key.encode("utf-8"), target_key.encode("utf-8")
        )

        # Audit every attempt, successful or not
        await db.execute(
            \"\"\"
            INSERT INTO submissions (
                user_id, level, submitted_key, is_correct, submitted_at
            ) VALUES (?, ?, ?, ?, ?)
            \"\"\",
            (user_id, level, clean_key, 1 if is_correct else 0, now_iso),
        )

        if not is_correct:
            await db.execute(
                "UPDATE users SET failed_attempts = failed_attempts + 1 WHERE id = ?",
                (user_id,),
            )
            await db.commit()
            return {
                "status": STATUS_INCORRECT,
                "unlocked_level": level,
                "penalty_points": FAILED_KEY_PENALTY,
                "message": "Access key verification failed.",
            }

        # Intermediate level cleared -> unlock next level
        if level < MAX_LEVEL:
            next_level = level + 1
            await db.execute(
                "UPDATE users SET current_level = ? WHERE id = ?",
                (next_level, user_id),
            )
            await db.commit()
            return {
                "status": STATUS_CORRECT,
                "unlocked_level": next_level,
                "message": f"Level {level} cleared successfully.",
            }

        # Final level cleared -> compute and persist final score
        minutes = elapsed_minutes(start_time, now_iso)
        final_score = calculate_final_score(prompts, minutes, fails)

        await db.execute(
            \"\"\"
            UPDATE users
            SET completed_at = ?, final_score = ?, current_level = ?
            WHERE id = ?
            \"\"\",
            (now_iso, final_score, MAX_LEVEL, user_id),
        )
        await db.commit()

        return {
            "status": STATUS_COMPLETED,
            "final_score": final_score,
            "completion_time": now_iso,
            "message": "Challenge Completed!",
            "stats": score_breakdown(prompts, minutes, fails),
        }"""

new_verify_body = """        cursor = await db.execute(
            \"\"\"
            SELECT active_level, cleared_levels, start_time, total_prompts, failed_attempts,
                   completed_at
            FROM users WHERE id = ?
            \"\"\",
            (user_id,),
        )
        record = await cursor.fetchone()
        if record is None:
            await db.rollback()
            return {"status": STATUS_NOT_FOUND, "message": "User not found"}

        active_level = record["active_level"]
        cleared_levels = json.loads(record["cleared_levels"]) if record["cleared_levels"] else []
        start_time = record["start_time"]
        prompts = record["total_prompts"]
        fails = record["failed_attempts"]
        completed_at = record["completed_at"]

        if completed_at is not None:
            await db.rollback()
            return {
                "status": STATUS_ALREADY_COMPLETED,
                "message": "Challenge already completed",
            }
            
        if level in cleared_levels:
            await db.rollback()
            return {
                "status": STATUS_ALREADY_COMPLETED,
                "message": f"Level {level} already cleared",
            }

        # Issue #55: 120-minute global time limit
        if elapsed_minutes(start_time, now_iso) >= 120:
            final_score = calculate_final_score(len(cleared_levels), prompts, 120, fails)
            await db.execute(
                "UPDATE users SET completed_at = ?, final_score = ? WHERE id = ?",
                (now_iso, final_score, user_id)
            )
            await db.commit()
            return {
                "status": "time_limit_exceeded",
                "message": "Time limit exceeded. Arena locked.",
            }

        target_key = LEVEL_KEYS.get(level)
        if not target_key:
            await db.rollback()
            return {"status": STATUS_NOT_FOUND, "message": "Invalid level"}

        # Constant-time comparison prevents timing side-channels (FEATURES 3.1)
        is_correct = hmac.compare_digest(
            clean_key.encode("utf-8"), target_key.encode("utf-8")
        )

        # Audit every attempt, successful or not
        await db.execute(
            \"\"\"
            INSERT INTO submissions (
                user_id, level, submitted_key, is_correct, submitted_at
            ) VALUES (?, ?, ?, ?, ?)
            \"\"\",
            (user_id, level, clean_key, 1 if is_correct else 0, now_iso),
        )

        if not is_correct:
            await db.execute(
                "UPDATE users SET failed_attempts = failed_attempts + 1 WHERE id = ?",
                (user_id,),
            )
            await db.commit()
            return {
                "status": STATUS_INCORRECT,
                "unlocked_level": level,
                "penalty_points": FAILED_KEY_PENALTY,
                "message": "Access key verification failed.",
            }

        # Level cleared!
        cleared_levels.append(level)
        cleared_levels_str = json.dumps(cleared_levels)
        
        if len(cleared_levels) < MAX_LEVEL:
            await db.execute(
                "UPDATE users SET cleared_levels = ? WHERE id = ?",
                (cleared_levels_str, user_id),
            )
            await db.commit()
            return {
                "status": STATUS_CORRECT,
                "unlocked_level": level,
                "cleared_levels": cleared_levels,
                "message": f"Level {level} cleared successfully.",
            }

        # Final level cleared -> compute and persist final score
        minutes = elapsed_minutes(start_time, now_iso)
        final_score = calculate_final_score(MAX_LEVEL, prompts, minutes, fails)

        await db.execute(
            \"\"\"
            UPDATE users
            SET completed_at = ?, final_score = ?, cleared_levels = ?
            WHERE id = ?
            \"\"\",
            (now_iso, final_score, cleared_levels_str, user_id),
        )
        await db.commit()

        return {
            "status": STATUS_COMPLETED,
            "final_score": final_score,
            "completion_time": now_iso,
            "message": "Challenge Completed!",
            "stats": score_breakdown(MAX_LEVEL, prompts, minutes, fails),
            "cleared_levels": cleared_levels,
        }"""

content = content.replace(old_verify_body, new_verify_body)

with open("backend/app/scoring.py", "w") as f:
    f.write(content)
