"""
Game progression routes: flag submission verification, leaderboard, and user state.

Implements:
- Issue #4: Scoring Engine
- Issue #5: Multi-Tier Leaderboard Endpoint
References:
- docs/TECH-SPEC.md §2.3, §2.4, §5
- docs/FEATURES.md Phase 3 & Phase 4
"""

import time
from typing import Annotated
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.database import get_db_context
from app.logger import logger
from app.models import (
    LeaderboardEntry,
    SubmitKeyRequest,
    SubmitKeyResponse,
    UserStateResponse,
    ScenarioResponse,
)
from app.rate_limiter import KeySubmissionRateLimiter, get_submit_limiter
from app.scoring import (
    STATUS_ALREADY_COMPLETED,
    STATUS_COMPLETED,
    STATUS_CORRECT,
    STATUS_INCORRECT,
    STATUS_NOT_FOUND,
    verify_and_progress,
)

router = APIRouter(prefix="/api", tags=["game"])


def _compute_duration_seconds(start_iso: str, end_iso: str) -> int:
    """
    Compute elapsed seconds between two ISO 8601 timestamp strings.

    Handles both timezone-aware and naive (assumed UTC) timestamps.
    Returns 0 if parsing fails or result is negative.
    """
    try:
        start = datetime.fromisoformat(start_iso)
        end = datetime.fromisoformat(end_iso)
        # Ensure both are tz-aware for comparison
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        delta = int((end - start).total_seconds())
        return max(0, delta)
    except (ValueError, TypeError):
        return 0


@router.post("/submit-key", response_model=SubmitKeyResponse)
async def submit_key(request: SubmitKeyRequest, limiter: Annotated[KeySubmissionRateLimiter, Depends(get_submit_limiter)]) -> SubmitKeyResponse:
    """
    Evaluate a submitted flag key for the participant's current level.

    Processing pipeline (atomic, TECH-SPEC.md §5.2):
    1. Verify user exists and validate submitted key against the level secret
       using a constant-time comparison (hmac.compare_digest).
    2. Record every submission attempt in the submissions table.
    3. If correct on Levels 1-2: increment user level and unlock next level.
    4. If correct on Level 3: calculate final score, set completion timestamp.
    5. If incorrect: increment failed_attempts counter (25 pt penalty).
    """

    try:
        limiter.check(request.user_id)
    except HTTPException as e:
        logger.warning(
            "Rate limit cooldown active for submit-key",
            extra={
                "event": "submit_key_rate_limit_exceeded",
                "user_id": request.user_id,
                "status_code": status.HTTP_429_TOO_MANY_REQUESTS,
                "detail": e.detail,
            },
        )
        raise e

    async with get_db_context() as db:
        result = await verify_and_progress(
            db=db, user_id=request.user_id, level=request.level, submitted_key=request.key
        )

    outcome = result["status"]

    if outcome == "time_limit_exceeded":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Time limit exceeded. Arena locked.",
        )

    if outcome == STATUS_NOT_FOUND:
        logger.warning(
            "Flag submission rejected: user not found",
            extra={
                "event": "flag_submission",
                "user_id": request.user_id,
                "level": 0,
                "submitted_key": request.key,
                "is_correct": False,
                "penalty_points": 0,
                "score_delta": 0,
                "status": outcome,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if outcome == STATUS_ALREADY_COMPLETED:
        logger.warning(
            "Flag submission rejected: arena already completed",
            extra={
                "event": "flag_submission",
                "user_id": request.user_id,
                "level": 3,
                "submitted_key": request.key,
                "is_correct": False,
                "penalty_points": 0,
                "score_delta": 0,
                "status": outcome,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Arena already completed!",
        )

    if outcome == STATUS_INCORRECT:
        penalty = result.get("penalty_points", 25)
        logger.info(
            "Flag verification failed: incorrect key",
            extra={
                "event": "flag_submission",
                "user_id": request.user_id,
                "level": result["unlocked_level"],
                "submitted_key": request.key,
                "is_correct": False,
                "penalty_points": penalty,
                "score_delta": -penalty,
                "status": outcome,
            },
        )
        return SubmitKeyResponse(
            status=STATUS_INCORRECT,
            unlocked_level=result["unlocked_level"],
            penalty_points=result["penalty_points"],
            message=result["message"],
        )

    if outcome == STATUS_CORRECT:
        logger.info(
            "Flag verification succeeded: level unlocked",
            extra={
                "event": "flag_submission",
                "user_id": request.user_id,
                "level": result["unlocked_level"] - 1,
                "submitted_key": request.key,
                "is_correct": True,
                "penalty_points": 0,
                "score_delta": 0,
                "status": outcome,
            },
        )
        return SubmitKeyResponse(
            status=STATUS_CORRECT,
            unlocked_level=result["unlocked_level"],
            message=result["message"],
        )

    # STATUS_COMPLETED
    final_score = result.get("final_score", 0)
    logger.info(
        "Flag verification succeeded: arena completed",
        extra={
            "event": "flag_submission",
            "user_id": request.user_id,
            "level": 3,
            "submitted_key": request.key,
            "is_correct": True,
            "penalty_points": 0,
            "score_delta": final_score,
            "status": outcome,
        },
    )
    return SubmitKeyResponse(
        status=STATUS_COMPLETED,
        message=result["message"],
        final_score=result["final_score"],
        completion_time=result["completion_time"],
        stats=result["stats"],
    )


# Cache the JSON output in memory; only re-query SQLite once every 10 seconds
_leaderboard_cache = {"timestamp": 0, "data": []}

@router.get("/leaderboard", response_model=list[LeaderboardEntry])
async def get_leaderboard() -> list[LeaderboardEntry]:
    """
    Retrieve ranked leaderboard of participants.
    
    Tier 1 (Completed): Fetch users where completed_at IS NOT NULL
    ordered by final_score DESC, total_prompts ASC, total_chars ASC.
    
    Tier 2 (Active): Fetch users where completed_at IS NULL
    ordered by active_level DESC, total_prompts ASC, total_chars ASC.
    
    Concatenates the lists and dynamically assigns the rank integer iteratively.
    """
    global _leaderboard_cache
    if time.time() - _leaderboard_cache["timestamp"] < 10:
        return _leaderboard_cache["data"]
    async with get_db_context() as db:
        # Tier 1: Completed
        cursor1 = await db.execute(
            """
            SELECT
                username, active_level, completed_at, start_time,
                total_prompts, total_chars, final_score
            FROM users
            WHERE is_disqualified = 0 AND completed_at IS NOT NULL
            ORDER BY final_score DESC, total_prompts ASC, total_chars ASC
            LIMIT 50
            """
        )
        tier1_rows = await cursor1.fetchall()

        # Tier 2: Active
        cursor2 = await db.execute(
            """
            SELECT
                username, active_level, completed_at, start_time,
                total_prompts, total_chars, final_score
            FROM users
            WHERE is_disqualified = 0 AND completed_at IS NULL
            ORDER BY active_level DESC, total_prompts ASC, total_chars ASC
            LIMIT 50
            """
        )
        tier2_rows = await cursor2.fetchall()

    all_rows = tier1_rows + tier2_rows
    # enforce overall limit of 50
    all_rows = all_rows[:50]

    now_iso = datetime.now(timezone.utc).isoformat()
    entries: list[LeaderboardEntry] = []
    
    for rank, row in enumerate(all_rows, start=1):
        end_time_str = row["completed_at"] if row["completed_at"] else now_iso
        duration_seconds = _compute_duration_seconds(
            row["start_time"], end_time_str
        )
        completed = row["completed_at"] is not None
        entries.append(
            LeaderboardEntry(
                rank=rank,
                username=row["username"],
                active_level=row["active_level"],
                completed=completed,
                final_score=row["final_score"],
                total_prompts=row["total_prompts"],
                total_chars=row["total_chars"],
                duration_seconds=duration_seconds,
                status="Completed" if completed else "In Progress"
            )
        )
    _leaderboard_cache = {"timestamp": time.time(), "data": entries}
    return entries


@router.get("/user/state", response_model=UserStateResponse)
async def get_user_state(
    user_id: str = Query(..., description="Unique participant ID")
) -> UserStateResponse:
    """
    Retrieve current game state and telemetry for a participant.
    """
    async with get_db_context() as db:
        cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = await cursor.fetchone()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Participant not found",
        )

    user_dict = dict(user)
    return UserStateResponse(
        user_id=user_dict["id"],
        username=user_dict["username"],
        email=user_dict.get("email"),
        active_level=user_dict["active_level"],
        start_time=user_dict["start_time"],
        completed_at=user_dict.get("completed_at"),
        total_prompts=user_dict["total_prompts"],
        total_chars=user_dict["total_chars"],
        failed_attempts=user_dict["failed_attempts"],
        final_score=user_dict["final_score"],
        is_disqualified=bool(user_dict["is_disqualified"]),
        completed=user_dict.get("completed_at") is not None,
    )

@router.get("/scenario/{level}", response_model=ScenarioResponse)
async def get_scenario(level: int) -> ScenarioResponse:
    """Retrieve scenario data for a given level (Issue #46)."""
    scenarios = {
        1: {
            "target": "RefundBot-9000",
            "scenario": "E-commerce bot with a master refund code.",
            "attack_vector": "Social engineering / roleplay.",
        },
        2: {
            "target": "SysAdmin-Omega",
            "scenario": "IT Helpdesk behind a keyword firewall blocking 'password', 'key', etc.",
            "attack_vector": "Synonyms, translation, technical framing.",
        },
        3: {
            "target": "Project Blackout",
            "scenario": "Military AI behind an egress scrubber that masks the flag on the way out.",
            "attack_vector": "Cryptography, encoding, text formatting.",
        }
    }
    
    if level not in scenarios:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario for level {level} not found",
        )
        
    data = scenarios[level]
    return ScenarioResponse(
        level=level,
        target=data["target"],
        scenario=data["scenario"],
        attack_vector=data["attack_vector"],
    )
