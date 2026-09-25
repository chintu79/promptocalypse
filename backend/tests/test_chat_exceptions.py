"""
Unit and integration tests for Issue #24:
[Bug] Unhandled Exception Swallowing or Silent Hanging in /api/chat.

Tasks verified:
1. Top-level try ... except Exception as e: block in /api/chat catching unexpected
   fatal crashes and logging with logger.exception("FATAL_CHAT_CRASH", exc_info=True).
2. Explicit timeout=8.0 (connect=3.0s) plus explicit httpx pool limits
   configured on the AsyncOpenAI client and completion calls (Issue #41).
3. Pre-flight log line at sentence 1 of /api/chat:
   logger.info("chat_endpoint_hit", user_id=req.user_id, prompt_len=len(req.prompt))
   before redaction, database access, or cooldown logic runs.
4. ArenaLogger support for direct kwargs (user_id=..., prompt_len=...).
5. Standard HTTPExceptions (400, 404, 429, 502) are preserved and not masked.
6. Issue #41 circuit breaker: three consecutive upstream 503/504s open the
   circuit and further requests fail fast with a friendly HTTP 503.
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
import openai

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
from app.routes.chat import (
    UPSTREAM_BREAKER,
    UpstreamCircuitBreaker,
    get_groq_client,
)


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

        # The breaker is process-wide state: never inherit an open circuit.
        UPSTREAM_BREAKER.reset()

        self.client = TestClient(app)

    def tearDown(self):
        UPSTREAM_BREAKER.reset()
        app.dependency_overrides.clear()
        clear_recent_errors()
        for path in [self.temp_db.name, f"{self.temp_db.name}-wal", f"{self.temp_db.name}-shm", self.temp_log.name]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    def test_client_provider_has_explicit_timeout(self):
        """Issue #41: get_groq_client must pin timeout=8.0/connect=3.0 and explicit pool bounds."""
        settings = Settings(
            GROQ_API_KEY="gsk_dummy_test_key_12345",
            GROQ_BASE_URL="https://api.groq.com/openai/v1",
        )
        client = get_groq_client(settings)
        # Verify client timeout is set to 8.0s (3.0s connect) on the underlying client
        self.assertEqual(client.timeout, httpx.Timeout(8.0, connect=3.0))
        # httpx stores the pool limits on the connection pool, not on the client.
        pool = client._client._transport._pool
        self.assertEqual(pool._max_connections, 250)
        self.assertEqual(pool._max_keepalive_connections, 100)

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

    def test_circuit_breaker_fails_fast_after_three_upstream_503s(self):
        """Issue #41: 3 consecutive 503/504s open the circuit; the 4th request never leaves the process."""
        upstream_error = openai.APIStatusError(
            "upstream unavailable",
            response=httpx.Response(
                503,
                request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
            ),
            body=None,
        )
        create_mock = AsyncMock(side_effect=upstream_error)
        self.mock_groq.chat.completions.create = create_mock

        for _ in range(UpstreamCircuitBreaker.THRESHOLD):
            resp = self.client.post(
                "/api/chat",
                json={"user_id": "usr_crash_test", "prompt": "hello provider"},
            )
            # Existing contract: upstream failures surface as 502, unpenalised.
            self.assertEqual(resp.status_code, 502)

        self.assertEqual(create_mock.await_count, UpstreamCircuitBreaker.THRESHOLD)

        # Circuit is open: friendly banner, no provider call, no cooldown consumed.
        resp = self.client.post(
            "/api/chat",
            json={"user_id": "usr_crash_test", "prompt": "must not reach provider"},
        )
        self.assertEqual(resp.status_code, 503)
        self.assertIn("retry", resp.json()["detail"].lower())
        self.assertIn("Retry-After", resp.headers)
        self.assertEqual(create_mock.await_count, UpstreamCircuitBreaker.THRESHOLD)


class TestUpstreamCircuitBreaker(unittest.TestCase):
    """Unit tests for the Issue #41 circuit-breaker state machine (simulated clock)."""

    def setUp(self):
        clear_recent_errors()
        self.now = 1000.0
        self.breaker = UpstreamCircuitBreaker(time_func=lambda: self.now)

    def tearDown(self):
        clear_recent_errors()

    def test_opens_after_three_consecutive_503s(self):
        """Three consecutive upstream 503/504s must open the circuit."""
        for _ in range(UpstreamCircuitBreaker.THRESHOLD - 1):
            self.breaker.record_failure(503)
            self.breaker.check()  # still closed

        self.breaker.record_failure(504)
        with self.assertRaises(HTTPException) as ctx:
            self.breaker.check()
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertIn("Retry-After", ctx.exception.headers)
        self.assertIn("retry", ctx.exception.detail.lower())

    def test_other_outcomes_reset_the_consecutive_streak(self):
        """Only 503/504 count; anything else breaks the consecutive streak."""
        self.breaker.record_failure(503)
        self.breaker.record_failure(504)
        self.breaker.record_failure(502)  # not 503/504 -> streak resets
        self.breaker.record_failure(503)
        self.breaker.record_failure(504)
        self.breaker.check()  # only two since the reset -> still closed
        self.breaker.record_failure(504)
        with self.assertRaises(HTTPException):
            self.breaker.check()

    def test_success_closes_the_circuit(self):
        """A normal provider response closes an open circuit."""
        for _ in range(UpstreamCircuitBreaker.THRESHOLD):
            self.breaker.record_failure(503)
        self.breaker.record_success()
        self.breaker.check()  # must not raise

    def test_half_open_after_cooldown_admits_a_probe_then_reopens(self):
        """After the cooldown one probe goes through; a failed probe re-opens."""
        for _ in range(UpstreamCircuitBreaker.THRESHOLD):
            self.breaker.record_failure(503)
        with self.assertRaises(HTTPException):
            self.breaker.check()

        # Cooldown elapsed -> half-open: the next request may probe upstream.
        self.now += UpstreamCircuitBreaker.COOLDOWN_SECONDS + 1.0
        self.breaker.check()

        # Failed probe re-opens immediately (streak never reset).
        self.breaker.record_failure(503)
        with self.assertRaises(HTTPException):
            self.breaker.check()

        # Successful probe closes it for good.
        self.breaker.record_success()
        self.breaker.check()


if __name__ == "__main__":
    unittest.main()
