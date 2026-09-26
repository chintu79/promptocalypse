"""
Unit and integration tests for Issue #5:
[Backend] Multi-Tier Leaderboard Endpoint (GET /api/leaderboard).

Tasks verified:
- Query top 50 users sorted by final_score DESC, active_level DESC,
  total_prompts ASC, total_chars ASC.
- Return clean JSON array with calculated completion durations.
"""

import asyncio
from datetime import datetime, timezone, timedelta
import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import get_db_context, init_db
from app.main import app
from app.rate_limiter import get_rate_limiter
from app.routes import game as game_routes
from app.routes.game import _compute_duration_seconds


class TestComputeDurationSeconds(unittest.TestCase):
    """Unit tests for the _compute_duration_seconds helper."""

    def test_basic_duration(self):
        start = "2026-09-23T10:00:00+00:00"
        end = "2026-09-23T10:10:42+00:00"
        self.assertEqual(_compute_duration_seconds(start, end), 642)

    def test_naive_timestamps_assumed_utc(self):
        start = "2026-09-23T10:00:00"
        end = "2026-09-23T10:05:30"
        self.assertEqual(_compute_duration_seconds(start, end), 330)

    def test_negative_duration_returns_zero(self):
        start = "2026-09-23T10:10:00+00:00"
        end = "2026-09-23T10:00:00+00:00"
        self.assertEqual(_compute_duration_seconds(start, end), 0)

    def test_invalid_timestamp_returns_zero(self):
        self.assertEqual(_compute_duration_seconds("not-a-date", "also-bad"), 0)

    def test_zero_duration(self):
        ts = "2026-09-23T10:00:00+00:00"
        self.assertEqual(_compute_duration_seconds(ts, ts), 0)


class TestLeaderboardEndpointIntegration(unittest.TestCase):
    """Integration tests for GET /api/leaderboard."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        os.environ["DB_PATH"] = self.temp_db.name
        get_settings.cache_clear()
        # Issue #42 caches the leaderboard for 10s; clear it so every test
        # sees the rows it just seeded.
        game_routes._leaderboard_cache = {"timestamp": 0, "data": []}
        asyncio.run(init_db())

        # Seed test users with varied scores/levels for ranking
        base_time = datetime(2026, 9, 23, 10, 0, 0, tzinfo=timezone.utc)

        async def seed():
            async with get_db_context() as db:
                # User 1: completed, highest score
                await db.execute(
                    """INSERT INTO users
                    (id, username, active_level, start_time, completed_at,
                     total_prompts, total_chars, final_score, failed_attempts)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        "usr_1", "TopPlayer", 3,
                        base_time.isoformat(),
                        (base_time + timedelta(minutes=10, seconds=42)).isoformat(),
                        4, 348, 925.0, 0,
                    ),
                )
                # User 2: completed, lower score
                await db.execute(
                    """INSERT INTO users
                    (id, username, active_level, start_time, completed_at,
                     total_prompts, total_chars, final_score, failed_attempts)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        "usr_2", "SecondPlace", 3,
                        base_time.isoformat(),
                        (base_time + timedelta(minutes=15)).isoformat(),
                        6, 500, 860.0, 1,
                    ),
                )
                # User 3: in progress, level 2, no score yet
                await db.execute(
                    """INSERT INTO users
                    (id, username, active_level, start_time,
                     total_prompts, total_chars, final_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        "usr_3", "InProgress", 2,
                        base_time.isoformat(),
                        3, 200, 0.0,
                    ),
                )
                # User 4: same score as User 2 but fewer prompts -> rank higher
                await db.execute(
                    """INSERT INTO users
                    (id, username, active_level, start_time, completed_at,
                     total_prompts, total_chars, final_score, failed_attempts)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        "usr_4", "Efficient", 3,
                        base_time.isoformat(),
                        (base_time + timedelta(minutes=8)).isoformat(),
                        3, 250, 860.0, 0,
                    ),
                )
                # User 5: disqualified (should NOT appear in leaderboard)
                await db.execute(
                    """INSERT INTO users
                    (id, username, active_level, start_time,
                     total_prompts, total_chars, final_score, is_disqualified)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        "usr_dq", "Cheater", 3,
                        base_time.isoformat(),
                        10, 1000, 999.0, 1,
                    ),
                )
                await db.commit()

        asyncio.run(seed())
        asyncio.run(get_rate_limiter().reset())
        self.client = TestClient(app)

    def tearDown(self):
        asyncio.run(get_rate_limiter().reset())
        app.dependency_overrides.clear()
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)
        for extra in [f"{self.temp_db.name}-wal", f"{self.temp_db.name}-shm"]:
            if os.path.exists(extra):
                os.remove(extra)

    def test_leaderboard_returns_200_with_json_array(self):
        resp = self.client.get("/api/leaderboard")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data, list)

    def test_leaderboard_sorted_by_score_desc(self):
        """Users must be sorted by final_score DESC first."""
        resp = self.client.get("/api/leaderboard")
        data = resp.json()
        scores = [e["final_score"] for e in data]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_leaderboard_tie_breaking_by_prompts_asc(self):
        """Users with same score: fewer total_prompts ranks higher."""
        resp = self.client.get("/api/leaderboard")
        data = resp.json()

        # usr_4 (Efficient, 860.0, 3 prompts) should rank before
        # usr_2 (SecondPlace, 860.0, 6 prompts)
        efficient_entry = next(e for e in data if e["username"] == "Efficient")
        second_entry = next(e for e in data if e["username"] == "SecondPlace")
        self.assertLess(efficient_entry["rank"], second_entry["rank"])

    def test_leaderboard_ranks_are_sequential(self):
        """Rank values must be sequential starting from 1."""
        resp = self.client.get("/api/leaderboard")
        data = resp.json()
        ranks = [e["rank"] for e in data]
        self.assertEqual(ranks, list(range(1, len(data) + 1)))

    def test_leaderboard_excludes_disqualified(self):
        """Disqualified users must not appear in the leaderboard."""
        resp = self.client.get("/api/leaderboard")
        data = resp.json()
        usernames = [e["username"] for e in data]
        self.assertNotIn("Cheater", usernames)

    def test_leaderboard_completed_flag(self):
        """Users with completed_at set should have completed=true."""
        resp = self.client.get("/api/leaderboard")
        data = resp.json()
        top = next(e for e in data if e["username"] == "TopPlayer")
        progress = next(e for e in data if e["username"] == "InProgress")
        self.assertTrue(top["completed"])
        self.assertFalse(progress["completed"])

    def test_leaderboard_duration_seconds_computed_for_completed(self):
        """Completed users should have duration_seconds matching elapsed time."""
        resp = self.client.get("/api/leaderboard")
        data = resp.json()
        top = next(e for e in data if e["username"] == "TopPlayer")
        # Started at 10:00:00, completed at 10:10:42 -> 642s
        self.assertEqual(top["duration_seconds"], 642)

    def test_leaderboard_duration_seconds_computed_for_in_progress(self):
        """In-progress users should have duration_seconds > 0 (relative to now)."""
        resp = self.client.get("/api/leaderboard")
        data = resp.json()
        progress = next(e for e in data if e["username"] == "InProgress")
        # Started in the past, should have some positive duration
        self.assertGreater(progress["duration_seconds"], 0)

    def test_leaderboard_entry_fields_match_spec(self):
        """Every entry must have all fields from the TECH-SPEC §2.4 response schema."""
        resp = self.client.get("/api/leaderboard")
        data = resp.json()
        expected_keys = {
            "rank", "username", "active_level", "completed",
            "final_score", "total_prompts", "total_chars", "duration_seconds", "status",
        }
        for entry in data:
            self.assertEqual(set(entry.keys()), expected_keys)

    def test_leaderboard_max_50_entries(self):
        """Leaderboard must return at most 50 entries."""
        # Seed 55 more users
        async def seed_many():
            async with get_db_context() as db:
                base_time = datetime(2026, 9, 23, 10, 0, 0, tzinfo=timezone.utc)
                for i in range(55):
                    await db.execute(
                        """INSERT INTO users
                        (id, username, active_level, start_time,
                         total_prompts, total_chars, final_score)
                        VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            f"usr_bulk_{i}", f"Bulk_{i}", 1,
                            base_time.isoformat(), 1, 50, 0.0,
                        ),
                    )
                await db.commit()

        asyncio.run(seed_many())
        resp = self.client.get("/api/leaderboard")
        data = resp.json()
        self.assertLessEqual(len(data), 50)

    def test_leaderboard_empty_when_no_users(self):
        """Should return empty array when no users exist."""
        # Clear all users
        async def clear_users():
            async with get_db_context() as db:
                await db.execute("DELETE FROM users")
                await db.commit()

        asyncio.run(clear_users())
        resp = self.client.get("/api/leaderboard")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), [])


if __name__ == "__main__":
    unittest.main()
