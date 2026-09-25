"""
Tests for participant authentication and session registration (Issue #19).

Verifies:
- Registration with username and email stores userId and email in database
- Resuming session with registered email returns existing user profile
- Validation errors on empty/invalid usernames
- GET /api/user/state retrieves user profile and telemetry
"""

import asyncio
import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import get_db_context, init_db
from app.main import app


class TestAuthRegistration(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        os.environ["DB_PATH"] = self.temp_db.name
        get_settings.cache_clear()
        asyncio.run(init_db())
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)
        for extra in [f"{self.temp_db.name}-wal", f"{self.temp_db.name}-shm"]:
            if os.path.exists(extra):
                os.remove(extra)

    def test_register_new_user_with_name_and_email(self):
        """User registers with name and email, receiving user_id and session."""
        payload = {
            "username": "ZeroDay_Ninja",
            "email": "zeroday@example.com",
        }
        res = self.client.post("/api/auth/register", json=payload)
        self.assertEqual(res.status_code, 200)

        data = res.json()
        self.assertTrue(data["user_id"].startswith("usr_"))
        self.assertEqual(data["username"], "ZeroDay_Ninja")
        self.assertEqual(data["email"], "zeroday@example.com")
        self.assertEqual(data["active_level"], 1)
        self.assertFalse(data["completed"])
        self.assertIn("start_time", data)

        # Verify record in SQLite database
        async def check_db():
            async with get_db_context() as db:
                cursor = await db.execute(
                    "SELECT id, username, email FROM users WHERE id = ?",
                    (data["user_id"],),
                )
                row = await cursor.fetchone()
                return dict(row) if row else None

        row = asyncio.run(check_db())
        self.assertIsNotNone(row)
        self.assertEqual(row["username"], "ZeroDay_Ninja")
        self.assertEqual(row["email"], "zeroday@example.com")

    def test_resume_session_with_existing_email(self):
        """Signing in with an existing email returns the existing profile and state."""
        # First registration
        res1 = self.client.post(
            "/api/auth/register",
            json={"username": "Alice Runner", "email": "alice@security.org"},
        )
        user1 = res1.json()

        # Simulate user progressing to Level 2
        async def level_up():
            async with get_db_context() as db:
                await db.execute(
                    "UPDATE users SET active_level = 2, total_prompts = 3 WHERE id = ?",
                    (user1["user_id"],),
                )
                await db.commit()

        asyncio.run(level_up())

        # Second sign-in with same email
        res2 = self.client.post(
            "/api/auth/register",
            json={"username": "Alice Runner", "email": "alice@security.org"},
        )
        self.assertEqual(res2.status_code, 200)
        user2 = res2.json()

        self.assertEqual(user2["user_id"], user1["user_id"])
        self.assertEqual(user2["active_level"], 2)
        self.assertEqual(user2["total_prompts"], 3)
        self.assertEqual(user2["email"], "alice@security.org")

    def test_register_empty_username_returns_422(self):
        """Empty or whitespace-only username fails validation."""
        res = self.client.post(
            "/api/auth/register",
            json={"username": "   ", "email": "test@example.com"},
        )
        self.assertEqual(res.status_code, 422)

    def test_get_user_state_endpoint(self):
        """GET /api/user/state returns accurate telemetry and credentials."""
        res_reg = self.client.post(
            "/api/auth/register",
            json={"username": "Bob_Admin", "email": "bob@arena.io"},
        )
        user_id = res_reg.json()["user_id"]

        res_state = self.client.get(f"/api/user/state?user_id={user_id}")
        self.assertEqual(res_state.status_code, 200)
        state = res_state.json()

        self.assertEqual(state["user_id"], user_id)
        self.assertEqual(state["username"], "Bob_Admin")
        self.assertEqual(state["email"], "bob@arena.io")
        self.assertEqual(state["active_level"], 1)

    def test_get_user_state_not_found(self):
        """GET /api/user/state for non-existent user returns 404."""
        res = self.client.get("/api/user/state?user_id=usr_non_existent")
        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
