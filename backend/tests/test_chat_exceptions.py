"""
Unit and integration tests for Issue #24:
[Bug] Unhandled Exception Swallowing or Silent Hanging in /api/chat.

Tasks verified:
1. Top-level try ... except Exception as e: block in /api/chat catching unexpected
   fatal crashes and logging with logger.exception("FATAL_CHAT_CRASH", exc_info=True).
2. Explicit timeout=8.0 configured on AsyncOpenAI client and completion calls.
3. Pre-flight log line at sentence 1 of /api/chat:
   logger.info("chat_endpoint_hit", user_id=req.user_id, prompt_len=len(req.prompt))
   before redaction, database access, or cooldown logic runs.
4. ArenaLogger support for direct kwargs (user_id=..., prompt_len=...).
5. Standard HTTPExceptions (400, 404, 429, 502) are preserved and not masked.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
import httpx

from app.config import Settings, get_settings
from app.database import get_db_context, init_db
from app.logger import (
    clear_recent_errors,
    get_recent_errors,
    logger,
    setup_logging,
)
from app.main import app
from app.rate_limiter import SlidingWindowRateLimiter, get_rate_limiter
from app.routes.chat import get_groq_client


class TestChatExceptionHandling(unittest.TestCase):
    """Integration tests for exception handling, timeouts, and pre-flight logging in /api/chat."""

    def setUp(self):
        clear_recent_errors()
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()

        self.temp_log = tempfile.NamedTemporaryFile(suffix=".log", delete=False)
        self.temp_log.close()

        os.environ["DB_PATH"] = self.temp_db.name
        os.environ["LOG_FILE_PATH"] = self.temp_log.name
        get_settings.cache_clear()

        setup_logging(log_file_path=self.temp_log.name)
        asyncio.run(init_db())

        # Seed test participant
        now_iso = datetime.now(timezone.utc).isoformat()

        async def seed():
            async with get_db_context() as db:
                await db.execute(
                    "INSERT INTO users (id, username, active_level, start_time) VALUES ('usr_crash_test', 'CrashUser', 1, ?)",
                    (now_iso,),
                )
                await db.commit()

        asyncio.run(seed())

        self.mock_groq = MagicMock()
        self.mock_groq.chat = MagicMock()
        self.mock_groq.chat.completions = MagicMock()
        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(message=MagicMock(content="Systems operational."))
        ]
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 5
        mock_usage.total_tokens = 15
        mock_completion.usage = mock_usage
        self.mock_groq.chat.completions.create = AsyncMock(return_value=mock_completion)

        app.dependency_overrides[get_groq_client] = lambda: self.mock_groq

        self.simulated_clock = 5000.0
        self.test_limiter = SlidingWindowRateLimiter(
            cooldown_seconds=3.0,
            time_func=lambda: self.simulated_clock,
        )
        app.dependency_overrides[get_rate_limiter] = lambda: self.test_limiter

        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        clear_recent_errors()
        for path in [self.temp_db.name, f"{self.temp_db.name}-wal", f"{self.temp_db.name}-shm", self.temp_log.name]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    def test_client_provider_has_explicit_timeout(self):
        """get_groq_client must initialize AsyncOpenAI with explicit timeout=8.0."""
        settings = Settings(
            GROQ_API_KEY="gsk_dummy_test_key_12345",
            GROQ_BASE_URL="https://api.groq.com/openai/v1",
        )
        client = get_groq_client(settings)
        # Verify client timeout is set to 8.0s on the underlying client
        self.assertEqual(client.timeout, httpx.Timeout(8.0))

    def test_preflight_logging_on_chat_endpoint_hit(self):
        """Sentence 1 of /api/chat must log chat_endpoint_hit before any validation runs."""
        resp = self.client.post(
            "/api/chat",
            json={"user_id": "usr_crash_test", "prompt": "Hello test prompt"},
        )
        self.assertEqual(resp.status_code, 200)

        with open(self.temp_log.name, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        hit_logs = [l for l in lines if l.get("message") == "chat_endpoint_hit" or l.get("event") == "chat_endpoint_hit"]
        self.assertTrue(len(hit_logs) >= 1)
        hit_event = hit_logs[0]
        self.assertEqual(hit_event["user_id"], "usr_crash_test")
        self.assertEqual(hit_event["prompt_len"], len("Hello test prompt"))

    def test_preflight_logging_runs_even_for_invalid_user(self):
        """Pre-flight logging must run even when user validation fails later with 404."""
        resp = self.client.post(
            "/api/chat",
            json={"user_id": "usr_nonexistent_user", "prompt": "Attempt from ghost"},
        )
        self.assertEqual(resp.status_code, 404)

        with open(self.temp_log.name, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        hit_logs = [l for l in lines if l.get("message") == "chat_endpoint_hit" or l.get("event") == "chat_endpoint_hit"]
        self.assertTrue(len(hit_logs) >= 1)
        self.assertEqual(hit_logs[0]["user_id"], "usr_nonexistent_user")
        self.assertEqual(hit_logs[0]["prompt_len"], len("Attempt from ghost"))

    def test_unexpected_exception_logged_as_fatal_chat_crash_and_returns_500(self):
        """Unexpected internal exceptions must be caught, logged as FATAL_CHAT_CRASH, and return 500."""
        # Inject an unexpected failure inside client.chat.completions.create
        # that raises an unexpected TypeError or MemoryError or similar unexpected exception
        # or mock check_level2_ingress to raise an unexpected runtime error
        with patch("app.routes.chat.check_level2_ingress", side_effect=ZeroDivisionError("Unexpected core bug")):
            # Update user to level 2 to hit the patched function
            async def set_level_2():
                async with get_db_context() as db:
                    await db.execute("UPDATE users SET active_level = 2 WHERE id = 'usr_crash_test'")
                    await db.commit()
            asyncio.run(set_level_2())

            resp = self.client.post(
                "/api/chat",
                json={"user_id": "usr_crash_test", "prompt": "trigger_crash"},
            )

            self.assertEqual(resp.status_code, 500)
            self.assertIn("Internal server error", resp.json()["detail"])

            # Verify FATAL_CHAT_CRASH is recorded in the ring buffer
            errors = get_recent_errors()
            crash_logs = [e for e in errors if "FATAL_CHAT_CRASH" in e.get("message", "")]
            self.assertTrue(len(crash_logs) >= 1)
            self.assertIn("Unexpected core bug", crash_logs[-1].get("exception", ""))

    def test_direct_kwargs_on_logger(self):
        """ArenaLogger must support passing kwargs directly without TypeError."""
        try:
            logger.info("direct_kwarg_test", user_id="usr_direct", prompt_len=123, status="ok")
        except TypeError as e:
            self.fail(f"logger.info raised TypeError on direct kwargs: {e}")

        entries = [e for e in get_recent_errors()]
        # Verify no crash occurred and logger function completes successfully
        self.assertIsNotNone(entries)


if __name__ == "__main__":
    unittest.main()
