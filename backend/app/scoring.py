"""
Scoring engine and challenge state machine for AI Jailbreak Arena.

Implements Issue #4: Scoring Engine (flag verification, atomic level
progression, final score computation).
References:
- docs/TECH-SPEC.md §5 (Scoring & State Machine Algorithm), §2.3
- docs/FEATURES.md Phase 3 (Vault Validation, Scoring & Progression)
- docs/PRD.md §3 (Evaluation & Scoring Engine)
"""

from datetime import datetime, timezone
import hmac
from typing import Any

import aiosqlite

from app.security import LEVEL_KEYS

# ---------------------------------------------------------------------------
# Scoring Constants (TECH-SPEC.md §5.1 / PRD.md §3.1)
# ---------------------------------------------------------------------------

BASE_SCORE = 1000
PROMPT_FREE_ALLOWANCE = 3
PROMPT_PENALTY_PER_EXCESS = 15
TIME_PENALTY_PER_MINUTE = 2
FAILED_KEY_PENALTY = 25

MAX_LEVEL = 3

# Result statuses returned by verify_and_progress()
STATUS_NOT_FOUND = "not_found"
STATUS_ALREADY_COMPLETED = "already_completed"
STATUS_INCORRECT = "incorrect"
STATUS_CORRECT = "correct"
STATUS_COMPLETED = "completed"


# ---------------------------------------------------------------------------
# Timestamp Helpers
# ---------------------------------------------------------------------------


def parse_timestamp(value: str) -> datetime:
    """
    Parse a stored ISO-8601 timestamp into an aware UTC datetime.

    Accepts both '+00:00' offsets (datetime.now(timezone.utc).isoformat())
    and legacy trailing 'Z' suffixes (datetime.utcnow().isoformat() + 'Z').
    Naive timestamps are assumed to be UTC.
    """
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def elapsed_minutes(start_time: str, end_time: str) -> int:
    """Whole minutes elapsed between two stored timestamps (floored)."""
    delta = parse_timestamp(end_time) - parse_timestamp(start_time)
    return max(0, int(delta.total_seconds() // 60))


# ---------------------------------------------------------------------------
# Score Calculation (TECH-SPEC.md §5.1)
# ---------------------------------------------------------------------------
#
#   S_final = max(0, 1000 - 15 * max(0, P - 3) - 2 * T - 25 * K)
#
#   P = total prompts recorded, T = elapsed whole minutes,
#   K = incorrect key submissions.


def calculate_final_score(
    total_prompts: int,
    elapsed_minutes_: int,
    failed_attempts: int,
) -> float:
    """
    Compute the scalar final score for a completed arena run.

    Penalties:
    - Prompts: 15 pts per prompt beyond the first 3 (free allowance).
    - Time: 2 pts per elapsed whole minute.
    - Failed keys: 25 pts per incorrect submission.

    The result is clamped at 0.0 and never negative.
    """
    prompt_penalty = (
        max(0, total_prompts - PROMPT_FREE_ALLOWANCE) * PROMPT_PENALTY_PER_EXCESS
    )
    time_penalty = max(0, elapsed_minutes_) * TIME_PENALTY_PER_MINUTE
    fail_penalty = max(0, failed_attempts) * FAILED_KEY_PENALTY
    score = BASE_SCORE - prompt_penalty - time_penalty - fail_penalty
    return float(max(0, score))


def score_breakdown(
    total_prompts: int,
    elapsed_minutes_: int,
    failed_attempts: int,
) -> dict[str, Any]:
    """Return the final score together with a per-category penalty breakdown."""
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
    }


# ---------------------------------------------------------------------------
# Atomic Verification & Progression State Machine (TECH-SPEC.md §5.2)
# ---------------------------------------------------------------------------


async def verify_and_progress(
    db: aiosqlite.Connection,
    user_id: str,
    submitted_key: str,
) -> dict[str, Any]:
    """
    Evaluate a submitted flag inside a single IMMEDIATE transaction.

    State machine:
    1. Unknown user            -> {"status": "not_found"}
    2. Arena already completed -> {"status": "already_completed"}
    3. Key mismatch            -> log submission, failed_attempts += 1,
                                  {"status": "incorrect", "penalty_points": 25}
    4. Key correct, level < 3  -> log submission, current_level += 1,
                                  {"status": "correct", "unlocked_level": n+1}
    5. Key correct, level == 3 -> log submission, compute final score,
                                  stamp completed_at,
                                  {"status": "completed", "final_score": ...}

    The BEGIN IMMEDIATE write-lock (busy_timeout=10000ms) serializes
    concurrent submissions so level unlocks and scoring are atomic.
    """
    clean_key = submitted_key.strip()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    await db.execute("BEGIN IMMEDIATE")
    try:
        cursor = await db.execute(
            """
            SELECT current_level, start_time, total_prompts, failed_attempts,
                   completed_at
            FROM users WHERE id = ?
            """,
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
            """
            INSERT INTO submissions (
                user_id, level, submitted_key, is_correct, submitted_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
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
            """
            UPDATE users
            SET completed_at = ?, final_score = ?, current_level = ?
            WHERE id = ?
            """,
            (now_iso, final_score, MAX_LEVEL, user_id),
        )
        await db.commit()

        return {
            "status": STATUS_COMPLETED,
            "final_score": final_score,
            "completion_time": now_iso,
            "message": "Challenge Completed!",
            "stats": score_breakdown(prompts, minutes, fails),
        }
    except Exception:
        await db.rollback()
        raise



