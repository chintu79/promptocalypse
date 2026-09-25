"""
Sliding-window rate limiter for AI Jailbreak Arena.

Implements Issue #3: [Backend] Sliding-Window 3-Second Rate Limiter.
Issue #40 moves the cooldown state into the shared ``rate_limits`` SQLite
table, because an in-memory dictionary exists once per Uvicorn worker process
and let a participant fan requests across workers to bypass the cooldown.
References:
- docs/PRD.md §4 (Rate Limiting & Protections) & §6 (Complete Backend Implementation)
- docs/SAD.md §2.2 (Per-Host Throttling)
- docs/TECH-SPEC.md §1.1 (Sequence Diagram) & §2.2 (Status Codes)
"""

import time
from typing import Annotated, Callable, Optional

import aiosqlite
from fastapi import Depends, HTTPException, status

from app.config import Settings, get_settings
from app.database import get_db_context


def _cooldown_exception(remaining: float) -> HTTPException:
    """Build the HTTP 429 raised while a participant is inside the cooldown window."""
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Rate limit: Wait {remaining:.1f}s",
        headers={"Retry-After": str(max(1, int(round(remaining))))},
    )


class SlidingWindowRateLimiter:
    """
    Per-user sliding-window rate limiter enforcing a cooldown between requests.

    Last-accepted request timestamps live in the shared ``rate_limits`` table
    instead of process memory, so all Uvicorn workers enforce one window.
    Rejects requests arriving within < cooldown_seconds with HTTP 429.
    """

    def __init__(
        self,
        cooldown_seconds: float = 3.0,
        time_func: Callable[[], float] = time.time,
    ) -> None:
        self.cooldown_seconds = cooldown_seconds
        # Wall clock, not monotonic: timestamps are persisted and compared
        # across worker processes (monotonic is meaningless across restarts).
        self.time_func = time_func

    async def check(self, user_id: str) -> None:
        """
        Check if the participant is on cooldown.

        Raises HTTPException(429) if elapsed time since last accepted request < cooldown_seconds.
        Does not mutate the timestamp so that rejected requests do not penalize the user
        or reset the cooldown timer.
        """
        async with get_db_context() as db:
            last_time = await self._last_stamp(db, user_id)
        if last_time is None:
            return
        elapsed = self.time_func() - last_time
        if elapsed < self.cooldown_seconds:
            raise _cooldown_exception(self.cooldown_seconds - elapsed)

    async def update(self, user_id: str) -> None:
        """Record current timestamp as the user's latest accepted request."""
        async with get_db_context() as db:
            await self._stamp(db, user_id, self.time_func())
            await db.commit()

    async def check_and_update(self, user_id: str) -> None:
        """
        Atomic check and update for a user request.

        BEGIN IMMEDIATE serializes concurrent callers across event loops and
        worker processes, so N simultaneous requests admit exactly one instead
        of each worker trusting its own view of the window (Issue #40).
        """
        now = self.time_func()
        async with get_db_context() as db:
            try:
                await db.execute("BEGIN IMMEDIATE")
                last_time = await self._last_stamp(db, user_id)
                if last_time is not None and (now - last_time) < self.cooldown_seconds:
                    raise _cooldown_exception(self.cooldown_seconds - (now - last_time))
                await self._stamp(db, user_id, now)
                await db.commit()
            except BaseException:
                # A rejected request must leave no stamp behind.
                await db.rollback()
                raise

    async def get_remaining(self, user_id: str) -> float:
        """Return remaining cooldown seconds for user, or 0.0 if not on cooldown."""
        async with get_db_context() as db:
            last_time = await self._last_stamp(db, user_id)
        if last_time is None:
            return 0.0
        elapsed = self.time_func() - last_time
        return max(0.0, self.cooldown_seconds - elapsed)

    async def reset(self, user_id: Optional[str] = None) -> None:
        """Reset rate limiter state for a specific user, or all users if None."""
        async with get_db_context() as db:
            if user_id is not None:
                await db.execute(
                    "DELETE FROM rate_limits WHERE user_id = ?", (user_id,)
                )
            else:
                await db.execute("DELETE FROM rate_limits")
            await db.commit()

    async def _last_stamp(
        self, db: aiosqlite.Connection, user_id: str
    ) -> Optional[float]:
        cursor = await db.execute(
            "SELECT last_request_at FROM rate_limits WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return float(row[0]) if row else None

    async def _stamp(self, db: aiosqlite.Connection, user_id: str, now: float) -> None:
        await db.execute(
            """
            INSERT INTO rate_limits (user_id, last_request_at) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET last_request_at = excluded.last_request_at
            """,
            (user_id, now),
        )
        # ponytail: prune is an unindexed O(n) scan of rate_limits, which stays
        # bounded to participants active in the last 2x cooldown (~seconds of
        # rows). Add an index on last_request_at if the user count ever grows
        # past thousands.
        await db.execute(
            "DELETE FROM rate_limits WHERE last_request_at < ?",
            (now - (self.cooldown_seconds * 2),),
        )


_global_limiter: Optional[SlidingWindowRateLimiter] = None


def get_rate_limiter(
    settings: Annotated[Optional[Settings], Depends(get_settings)] = None,
) -> SlidingWindowRateLimiter:
    """FastAPI dependency providing the active SlidingWindowRateLimiter."""
    global _global_limiter
    cooldown = settings.COOLDOWN_SECONDS if settings else 3.0
    if _global_limiter is None:
        _global_limiter = SlidingWindowRateLimiter(cooldown_seconds=cooldown)
    elif settings and _global_limiter.cooldown_seconds != settings.COOLDOWN_SECONDS:
        _global_limiter.cooldown_seconds = settings.COOLDOWN_SECONDS
    return _global_limiter

class KeySubmissionRateLimiter:
    """
    Independent rate-limiter for /api/submit-key (Issue #43).
    - Base cooldown: 2.0 seconds between any submission attempts.
    - Escalating penalty: After 3 failed key submissions in a row, enforces a 30-second lockout.
    """

    def __init__(
        self,
        base_cooldown: float = 2.0,
        lockout_duration: float = 30.0,
        max_failures: int = 3,
        time_func: Callable[[], float] = time.monotonic,
    ) -> None:
        self.base_cooldown = base_cooldown
        self.lockout_duration = lockout_duration
        self.max_failures = max_failures
        self.time_func = time_func
        # user_id -> (last_attempt_timestamp, consecutive_failures)
        self._state: dict[str, tuple[float, int]] = {}

    def check(self, user_id: str) -> None:
        if user_id not in self._state:
            return
            
        last_time, failures = self._state[user_id]
        now = self.time_func()
        elapsed = now - last_time
        
        current_cooldown = self.lockout_duration if failures >= self.max_failures else self.base_cooldown
        
        if elapsed < current_cooldown:
            remaining = current_cooldown - elapsed
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many attempts. Wait {remaining:.1f}s",
                headers={"Retry-After": str(max(1, int(round(remaining))))},
            )

    def record_attempt(self, user_id: str, is_correct: bool) -> None:
        now = self.time_func()
        failures = 0
        
        if user_id in self._state:
            _, old_failures = self._state[user_id]
            if not is_correct:
                failures = old_failures + 1
            else:
                failures = 0
        else:
            failures = 1 if not is_correct else 0
            
        self._state[user_id] = (now, failures)

        if len(self._state) > 1000:
            self._prune(now)

    def _prune(self, now: float) -> None:
        cutoff = now - max(self.base_cooldown, self.lockout_duration) * 2
        stale_keys = [k for k, (last_time, _) in self._state.items() if last_time < cutoff]
        for k in stale_keys:
            del self._state[k]

    def reset(self, user_id: Optional[str] = None) -> None:
        if user_id is not None:
            self._state.pop(user_id, None)
        else:
            self._state.clear()


_submit_limiter: Optional[KeySubmissionRateLimiter] = None

def get_submit_limiter() -> KeySubmissionRateLimiter:
    global _submit_limiter
    if _submit_limiter is None:
        _submit_limiter = KeySubmissionRateLimiter()
    return _submit_limiter
