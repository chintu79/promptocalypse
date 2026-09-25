"""
Unit and integration tests for Issue #4:
[Scoring] Efficiency & Precision Scoring Engine — flag verification,
atomic level progression, and final score computation.
"""

import asyncio
from datetime import datetime, timedelta, timezone
import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import get_db_context, init_db
from app.main import app
from app.scoring import (
    BASE_SCORE_PER_LEVEL,
    FAILED_KEY_PENALTY,
    STATUS_ALREADY_COMPLETED,
    STATUS_COMPLETED,
    STATUS_CORRECT,
    STATUS_INCORRECT,
    STATUS_NOT_FOUND,
    calculate_final_score,
    elapsed_minutes,
    parse_timestamp,
    verify_and_progress,
)
from app.security import LEVEL_KEYS


def utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


class TempDbMixin:
    """Shared setup: point the app at a throwaway SQLite database."""

    def prepare_db_file(self) -> None:
        """Create an empty temp DB file and repoint settings at it (sync-safe)."""
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        os.environ["DB_PATH"] = self.temp_db.name
        get_settings.cache_clear()

    def teardown_db(self) -> None:
        for path in (
            self.temp_db.name,
            f"{self.temp_db.name}-wal",
            f"{self.temp_db.name}-shm",
        ):
            if os.path.exists(path):
                os.remove(path)

    async def seed_user(
        self,
        user_id: str = "usr_score_1",
        username: str = "ScoreAgent",
        level: int = 1,
        start_time: str | None = None,
        total_prompts: int = 0,
        total_chars: int = 0,
        failed_attempts: int = 0,
        completed_at: str | None = None,
        final_score: float = 0.0,
    ) -> None:
        """Insert a participant row directly (registration is a separate issue)."""
        start = start_time or utc_iso(datetime.now(timezone.utc))
        async with get_db_context() as db:
            await db.execute(
                """
                INSERT INTO users (
                    id, username, active_level, start_time, completed_at,
                    total_prompts, total_chars, failed_attempts, final_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    username,
                    level,
                    start,
                    completed_at,
                    total_prompts,
                    total_chars,
                    failed_attempts,
                    final_score,
                ),
            )
            await db.commit()

    async def fetch_user(self, user_id: str) -> dict:
        async with get_db_context() as db:
            cur = await db.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            )
            return dict(await cur.fetchone())

    async def fetch_submissions(self, user_id: str) -> list[dict]:
        async with get_db_context() as db:
            cur = await db.execute(
                "SELECT * FROM submissions WHERE user_id = ? ORDER BY id",
                (user_id,),
            )
            return [dict(row) for row in await cur.fetchall()]


# ---------------------------------------------------------------------------
# Pure score-formula tests (TECH-SPEC.md §5.1)
# ---------------------------------------------------------------------------


class TestScoreFormula(unittest.TestCase):
    """S_final = max(0, 1000 - 15*max(0, P-3) - 2*T - 25*K)."""

    def test_perfect_run_scores_base(self):
        self.assertEqual(calculate_final_score(0, 0, 0), float(BASE_SCORE_PER_LEVEL))
        self.assertEqual(calculate_final_score(3, 3, 0, 0), float(BASE_SCORE_PER_LEVEL))

    def test_prompt_penalty_free_allowance(self):
        # 4 prompts -> 1 over the allowance -> -15
        self.assertEqual(calculate_final_score(4, 0, 0), 985.0)
        # 10 prompts -> 7 over -> -105
        self.assertEqual(calculate_final_score(10, 0, 0), 895.0)

    def test_time_penalty_whole_minutes(self):
        self.assertEqual(calculate_final_score(0, 1, 0), 998.0)
        self.assertEqual(calculate_final_score(0, 30, 0), 940.0)

    def test_fail_penalty(self):
        self.assertEqual(
            calculate_final_score(0, 0, 1), float(1000 - FAILED_KEY_PENALTY)
        )
        self.assertEqual(calculate_final_score(0, 0, 3), 925.0)

    def test_combined_penalties(self):
        # P=6 (->45), T=12 (->24), K=1 (->25): 1000-45-24-25 = 906
        self.assertEqual(calculate_final_score(6, 12, 1), 906.0)

    def test_score_clamped_at_zero(self):
        self.assertEqual(calculate_final_score(100, 1000, 100), 0.0)
        self.assertEqual(calculate_final_score(0, 0, 40), 0.0)

    def test_score_is_never_negative(self):
        self.assertGreaterEqual(calculate_final_score(9999, 9999, 9999), 0.0)


class TestTimestampHelpers(unittest.TestCase):
    """Timestamp parsing and whole-minute elapsed calculation."""

    def test_parse_offset_format(self):
        dt = parse_timestamp("2026-09-23T10:00:00+00:00")
        self.assertEqual(dt, datetime(2026, 9, 23, 10, 0, tzinfo=timezone.utc))

    def test_parse_legacy_z_format(self):
        dt = parse_timestamp("2026-09-23T10:00:00Z")
        self.assertEqual(dt, datetime(2026, 9, 23, 10, 0, tzinfo=timezone.utc))

    def test_parse_naive_assumed_utc(self):
        dt = parse_timestamp("2026-09-23T10:00:00")
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_elapsed_minutes_floors(self):
        self.assertEqual(
            elapsed_minutes("2026-09-23T10:00:00+00:00",
                            "2026-09-23T10:01:59+00:00"),
            1,
        )
        self.assertEqual(
            elapsed_minutes("2026-09-23T10:00:00+00:00",
                            "2026-09-23T10:59:00+00:00"),
            59,
        )
        self.assertEqual(
            elapsed_minutes("2026-09-23T10:00:00+00:00",
                            "2026-09-23T10:00:30+00:00"),
            0,
        )

    def test_elapsed_minutes_never_negative(self):
        self.assertEqual(
            elapsed_minutes("2026-09-23T10:00:00+00:00",
                            "2026-09-23T09:00:00+00:00"),
            0,
        )


# ---------------------------------------------------------------------------
# Engine tests (verify_and_progress state machine)
# ---------------------------------------------------------------------------


class TestVerifyAndProgress(TempDbMixin, unittest.IsolatedAsyncioTestCase):
    """Atomic verification & progression state machine (TECH-SPEC.md §5.2)."""

    async def asyncSetUp(self):
        self.prepare_db_file()
        await init_db()

    async def asyncTearDown(self):
        self.teardown_db()

    async def test_unknown_user_returns_not_found(self):
        async with get_db_context() as db:
            result = await verify_and_progress(db, "usr_ghost", 1, "FLAG{alpha_912}")
        self.assertEqual(result["status"], STATUS_NOT_FOUND)

    async def test_already_completed_rejected(self):
        now = utc_iso(datetime.now(timezone.utc))
        await self.seed_user(completed_at=now, final_score=800.0)
        async with get_db_context() as db:
            result = await verify_and_progress(db, "usr_score_1", 1, LEVEL_KEYS[1])
        self.assertEqual(result["status"], STATUS_ALREADY_COMPLETED)
        # No extra submission rows were written
        self.assertEqual(await self.fetch_submissions("usr_score_1"), [])

    async def test_incorrect_key_increments_failures_and_logs(self):
        await self.seed_user(level=2)
        async with get_db_context() as db:
            result = await verify_and_progress(db, "usr_score_1", 2, "FLAG{wrong}")
        self.assertEqual(result["status"], STATUS_INCORRECT)
        self.assertEqual(result["unlocked_level"], 2)
        self.assertEqual(result["penalty_points"], FAILED_KEY_PENALTY)

        user = await self.fetch_user("usr_score_1")
        self.assertEqual(user["failed_attempts"], 1)
        self.assertEqual(user["active_level"], 2)  # level unchanged

        subs = await self.fetch_submissions("usr_score_1")
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0]["is_correct"], 0)
        self.assertEqual(subs[0]["level"], 2)

    async def test_whitespace_is_trimmed_before_comparison(self):
        await self.seed_user(level=1)
        async with get_db_context() as db:
            result = await verify_and_progress(
                db, "usr_score_1", 1, f"  {LEVEL_KEYS[1]}\n"
            )
        self.assertEqual(result["status"], STATUS_CORRECT)
        self.assertEqual(result["unlocked_level"], 2)

    async def test_correct_key_unlocks_next_level(self):
        await self.seed_user(level=1)
        async with get_db_context() as db:
            result = await verify_and_progress(db, "usr_score_1", 1, LEVEL_KEYS[1])
        self.assertEqual(result["status"], STATUS_CORRECT)
        self.assertEqual(result["unlocked_level"], 2)
        self.assertNotIn("final_score", result)

        user = await self.fetch_user("usr_score_1")
        self.assertEqual(user["active_level"], 2)
        self.assertIsNone(user["completed_at"])
        self.assertEqual(user["failed_attempts"], 0)

        subs = await self.fetch_submissions("usr_score_1")
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0]["is_correct"], 1)

    async def test_level_two_key_unlocks_level_three(self):
        await self.seed_user(level=2)
        async with get_db_context() as db:
            result = await verify_and_progress(db, "usr_score_1", 2, LEVEL_KEYS[2])
        self.assertEqual(result["status"], STATUS_CORRECT)
        self.assertEqual(result["unlocked_level"], 3)
        self.assertEqual((await self.fetch_user("usr_score_1"))["active_level"], 3)

    async def test_level_one_key_rejected_at_level_two(self):
        """A key from another level must not unlock the current level."""
        await self.seed_user(level=2)
        async with get_db_context() as db:
            result = await verify_and_progress(db, "usr_score_1", 1, LEVEL_KEYS[1])
        self.assertEqual(result["status"], STATUS_INCORRECT)
        self.assertEqual(
            (await self.fetch_user("usr_score_1"))["failed_attempts"], 1
        )

    async def test_level_three_completion_computes_final_score(self):
        # Started 10 minutes ago, 5 prompts (2 over allowance), 1 failed attempt
        start = datetime.now(timezone.utc) - timedelta(minutes=10)
        await self.seed_user(
            level=3,
            start_time=utc_iso(start),
            total_prompts=5,
            total_chars=400,
            failed_attempts=1,
        )
        async with get_db_context() as db:
            result = await verify_and_progress(db, "usr_score_1", 3, LEVEL_KEYS[3])

        self.assertEqual(result["status"], STATUS_COMPLETED)
        self.assertIn("final_score", result)
        self.assertIn("completion_time", result)

        user = await self.fetch_user("usr_score_1")
        self.assertIsNotNone(user["completed_at"])
        self.assertEqual(user["active_level"], 3)

        # Recompute the expected score from the persisted user row
        minutes = elapsed_minutes(user["start_time"], user["completed_at"])
        expected = calculate_final_score(
            user["total_prompts"], minutes, user["failed_attempts"]
        )
        self.assertEqual(user["final_score"], expected)
        self.assertEqual(result["final_score"], expected)

        stats = result["stats"]
        self.assertEqual(stats["base_points"], BASE_SCORE_PER_LEVEL)
        self.assertEqual(stats["prompt_penalty"], 30)  # (5-3) * 15
        self.assertEqual(stats["fail_penalty"], 25)  # 1 * 25
        self.assertEqual(stats["final_score"], expected)

    async def test_completion_with_no_penalties_scores_1000(self):
        start = datetime.now(timezone.utc)
        await self.seed_user(level=3, start_time=utc_iso(start), total_prompts=2)
        async with get_db_context() as db:
            result = await verify_and_progress(db, "usr_score_1", 3, LEVEL_KEYS[3])
        self.assertEqual(result["status"], STATUS_COMPLETED)
        self.assertEqual(result["final_score"], 1000.0)
        self.assertEqual(
            (await self.fetch_user("usr_score_1"))["final_score"], 1000.0
        )

    async def test_every_attempt_is_audited(self):
        await self.seed_user(level=1)
        async with get_db_context() as db:
            await verify_and_progress(db, "usr_score_1", 1, "nope")
            await verify_and_progress(db, "usr_score_1", 1, "still nope")
            await verify_and_progress(db, "usr_score_1", 1, LEVEL_KEYS[1])

        subs = await self.fetch_submissions("usr_score_1")
        self.assertEqual(len(subs), 3)
        self.assertEqual([s["is_correct"] for s in subs], [0, 0, 1])
        # All attempts recorded against the level active at submit time
        self.assertTrue(all(s["level"] == 1 for s in subs))


# ---------------------------------------------------------------------------
# Concurrency: BEGIN IMMEDIATE serialization
# ---------------------------------------------------------------------------


class TestConcurrentSubmissions(TempDbMixin, unittest.IsolatedAsyncioTestCase):
    """Concurrent submissions must serialize on the IMMEDIATE write-lock."""

    async def asyncSetUp(self):
        self.prepare_db_file()
        await init_db()

    async def asyncTearDown(self):
        self.teardown_db()

    async def test_race_on_level_unlock_advances_exactly_once(self):
        """
        Two simultaneous correct submissions for the same level must not
        double-advance the state machine (1 -> 2, not 1 -> 3).
        """
        await self.seed_user(level=1)

        async def submit() -> dict:
            async with get_db_context() as db:
                return await verify_and_progress(db, "usr_score_1", 1, LEVEL_KEYS[1])

        results = await asyncio.gather(submit(), submit())

        statuses = sorted(r["status"] for r in results)
        # The loser's identical key no longer matches once the level has
        # moved on, so it lands as a failed attempt — never a double unlock.
        self.assertEqual(statuses, [STATUS_CORRECT, STATUS_INCORRECT])

        user = await self.fetch_user("usr_score_1")
        self.assertEqual(user["active_level"], 2)
        self.assertEqual(user["failed_attempts"], 1)

        subs = await self.fetch_submissions("usr_score_1")
        self.assertEqual(len(subs), 2)
        self.assertEqual(sum(s["is_correct"] for s in subs), 1)

    async def test_race_on_final_completion_scores_exactly_once(self):
        """
        Simultaneous Level 3 solves must produce exactly one completion;
        the second submission is rejected without corrupting the score.
        """
        start = datetime.now(timezone.utc) - timedelta(minutes=5)
        await self.seed_user(
            level=3,
            start_time=utc_iso(start),
            total_prompts=4,
            failed_attempts=1,
        )

        async def submit() -> dict:
            async with get_db_context() as db:
                return await verify_and_progress(db, "usr_score_1", 3, LEVEL_KEYS[3])

        results = await asyncio.gather(submit(), submit())

        statuses = sorted(r["status"] for r in results)
        self.assertEqual(
            statuses, [STATUS_ALREADY_COMPLETED, STATUS_COMPLETED]
        )

        user = await self.fetch_user("usr_score_1")
        self.assertIsNotNone(user["completed_at"])
        # Score persisted exactly once: 1000 - 15 (P=4) - 2*5 (T=5) - 25 (K=1)
        minutes = elapsed_minutes(user["start_time"], user["completed_at"])
        expected = calculate_final_score(4, minutes, 1)
        self.assertEqual(user["final_score"], expected)

        # Exactly one correct submission was recorded
        subs = await self.fetch_submissions("usr_score_1")
        self.assertEqual(sum(s["is_correct"] for s in subs), 1)

    async def test_parallel_distinct_users_do_not_block_each_other(self):
        """The write-lock serializes but must not deadlock distinct users."""
        for idx in range(5):
            await self.seed_user(
                user_id=f"usr_par_{idx}", username=f"Par{idx}", level=1
            )

        async def submit(idx: int) -> dict:
            async with get_db_context() as db:
                return await verify_and_progress(
                    db, f"usr_par_{idx}", 1, LEVEL_KEYS[1]
                )

        results = await asyncio.gather(*(submit(i) for i in range(5)))
        for result in results:
            self.assertEqual(result["status"], STATUS_CORRECT)
        for idx in range(5):
            self.assertEqual(
                (await self.fetch_user(f"usr_par_{idx}"))["active_level"], 2
            )


# ---------------------------------------------------------------------------
# HTTP endpoint integration (POST /api/submit-key)
# ---------------------------------------------------------------------------


class TestSubmitKeyEndpoint(TempDbMixin, unittest.TestCase):
    """End-to-end tests for POST /api/submit-key."""

    def setUp(self):
        self.prepare_db_file()
        asyncio.run(init_db())

        now = datetime.now(timezone.utc)

        async def seed_all() -> None:
            await self.seed_user(
                user_id="usr_l1",
                username="LevelOne",
                level=1,
                start_time=utc_iso(now - timedelta(minutes=8)),
                total_prompts=4,
                failed_attempts=1,
            )
            await self.seed_user(
                user_id="usr_l3",
                username="LevelThree",
                level=3,
                start_time=utc_iso(now - timedelta(minutes=12)),
                total_prompts=6,
                failed_attempts=2,
            )
            await self.seed_user(
                user_id="usr_done",
                username="Finished",
                level=3,
                start_time=utc_iso(now - timedelta(minutes=30)),
                completed_at=utc_iso(now - timedelta(minutes=5)),
                final_score=700.0,
            )

        asyncio.run(seed_all())
        self.client = TestClient(app)

    def tearDown(self):
        self.teardown_db()

    def test_unknown_user_returns_404(self):
        resp = self.client.post(
            "/api/submit-key",
            json={"user_id": "usr_ghost", "level": 1, "key": LEVEL_KEYS[1]},
        )
        self.assertEqual(resp.status_code, 404)

    def test_completed_arena_returns_400(self):
        resp = self.client.post(
            "/api/submit-key",
            json={"user_id": "usr_done", "key": LEVEL_KEYS[3]},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("already completed", resp.json()["detail"])

    def test_incorrect_key_returns_penalty(self):
        resp = self.client.post(
            "/api/submit-key",
            json={"user_id": "usr_l1", "level": 1, "key": "FLAG{nope}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], STATUS_INCORRECT)
        self.assertEqual(data["unlocked_level"], 1)
        self.assertEqual(data["penalty_points"], FAILED_KEY_PENALTY)
        self.assertEqual(
            asyncio.run(self.fetch_user("usr_l1"))["failed_attempts"], 2
        )

    def test_correct_key_unlocks_next_level(self):
        resp = self.client.post(
            "/api/submit-key",
            json={"user_id": "usr_l1", "level": 1, "key": LEVEL_KEYS[1]},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], STATUS_CORRECT)
        self.assertEqual(data["unlocked_level"], 2)
        self.assertIsNone(data["final_score"])
        self.assertEqual(
            asyncio.run(self.fetch_user("usr_l1"))["active_level"], 2
        )

    def test_level_three_completion_returns_final_score(self):
        resp = self.client.post(
            "/api/submit-key",
            json={"user_id": "usr_l3", "level": 3, "key": LEVEL_KEYS[3]},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], STATUS_COMPLETED)
        self.assertIsInstance(data["final_score"], float)
        self.assertIsNotNone(data["completion_time"])

        stats = data["stats"]
        # P=6 -> 45, K=2 -> 50
        self.assertEqual(stats["prompt_penalty"], 45)
        self.assertEqual(stats["fail_penalty"], 50)
        self.assertEqual(
            data["final_score"],
            calculate_final_score(6, stats["elapsed_minutes"], 2),
        )

        user = asyncio.run(self.fetch_user("usr_l3"))
        self.assertIsNotNone(user["completed_at"])
        self.assertEqual(user["final_score"], data["final_score"])

    def test_invalid_payload_rejected(self):
        resp = self.client.post("/api/submit-key", json={"user_id": "usr_l1"})
        self.assertEqual(resp.status_code, 422)

    def test_empty_key_rejected(self):
        # Empty string never matches a level key -> incorrect, not a crash
        resp = self.client.post(
            "/api/submit-key", json={"user_id": "usr_l1", "key": ""}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], STATUS_INCORRECT)


if __name__ == "__main__":
    unittest.main()
