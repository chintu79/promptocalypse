"""
Participant authentication and session management.

Implements Issue #19: Single page sign-in storing userId and email.
References:
- docs/PRD.md §1.1
- docs/TECH-SPEC.md §2.1
- docs/FEATURES.md §1.1
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from app.database import get_db_context
from pydantic import BaseModel
class SetLevelRequest(BaseModel):
    user_id: str
    level: int

from app.models import RegisterRequest, RegisterResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse)
async def register(request: RegisterRequest) -> RegisterResponse:
    """
    Register a new participant or resume an existing user session by email or username.

    Stores participant userId, name/handle, and registered email address
    in the local database. If a user with the matching email (or username)
    already exists, recovers the existing participant session.
    """
    clean_username = request.username.strip()
    clean_email = request.email.strip().lower() if request.email else None

    if not clean_username:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Name/username cannot be empty",
        )

    now_iso = datetime.now(timezone.utc).isoformat()

    async with get_db_context() as db:
        existing_user = None

        # 1. Search by email first if provided (canonical registered email ID)
        if clean_email:
            cursor = await db.execute(
                "SELECT * FROM users WHERE email = ? COLLATE NOCASE",
                (clean_email,),
            )
            existing_user = await cursor.fetchone()

        # 2. Fall back to search by username if not found by email
        if not existing_user:
            cursor = await db.execute(
                "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
                (clean_username,),
            )
            existing_user = await cursor.fetchone()

        # 3. If user exists, resume and reconcile session
        if existing_user:
            user_dict = dict(existing_user)
            # Update email if missing on old record
            if clean_email and not user_dict.get("email"):
                await db.execute(
                    "UPDATE users SET email = ? WHERE id = ?",
                    (clean_email, user_dict["id"]),
                )
                await db.commit()
                user_dict["email"] = clean_email

            import json
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
            )

        # 4. Create new participant profile
        new_id = f"usr_{uuid.uuid4()}"
        await db.execute(
            """
            INSERT INTO users (
                id, username, email, active_level, cleared_levels, start_time,
                total_prompts, total_chars, failed_attempts,
                final_score, is_disqualified
            ) VALUES (?, ?, ?, 1, '[]', ?, 0, 0, 0, 0.0, 0)
            """,
            (new_id, clean_username, clean_email, now_iso),
        )
        await db.commit()

        return RegisterResponse(
            user_id=new_id,
            username=clean_username,
            email=clean_email,
            active_level=1,
            cleared_levels=[],
            start_time=now_iso,
            total_prompts=0,
            failed_attempts=0,
            completed=False,
        )

@router.put("/active-level")
async def set_active_level(request: SetLevelRequest):
    async with get_db_context() as db:
        await db.execute("UPDATE users SET active_level = ? WHERE id = ?", (request.level, request.user_id))
        await db.commit()
    return {"status": "ok"}
