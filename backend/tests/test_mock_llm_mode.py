"""
Unit and integration tests for Issue #28:
[Testing] MOCK_LLM_MODE deterministic mock LLM provider.

Test Coverage:
1. Configuration:
   - MOCK_LLM_MODE env var "true" enables mock mode.
   - MOCK_LLM_MODE disabled by default (real provider path preserved).
2. Deterministic async mock (app.routes.chat.mock_llm_completion):
   - Exact replies for Level 1, Level 2 and Level 3.
   - Awaits a 300ms sleep and yields control (concurrent mocks overlap).
   - Level 3 raw FLAG reply passes through the existing Level 3 egress scrubber.
3. /api/chat integration with MOCK_LLM_MODE=true:
   - Exact mock replies served for levels 1, 2 and 3.
   - client.chat.completions.create is never called.
   - Request latency reflects the 300ms async mock sleep.
   - llm_prompt_dispatched and llm_completion_success both carry mock_provider=true.
   - Level 3 reply is masked by the existing egress scrubber (ledger is_leak_blocked=1).
4. Real provider path preserved when MOCK_LLM_MODE is disabled.
"""

import asyncio
from datetime import datetime, timezone
import json
import os
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.database import get_db_context, init_db
from app.logger import clear_recent_errors, setup_logging
from app.main import app
from app.rate_limiter import SlidingWindowRateLimiter, get_rate_limiter
from app.routes.chat import (
    MOCK_LLM_RESPONSES,
    MOCK_LLM_SLEEP_SECONDS,
    get_groq_client,
    mock_llm_completion,
)
from app.security import L3_LEAK_MASKED_REPLY, scrub_level3_egress

PROVIDER_REPLY = "Real provider reply from upstream."


class TestMockLlmModeSetting(unittest.TestCase):
    """MOCK_LLM_MODE environment variable parsing."""

    def test_env_var_true_enables_mock_mode(self):
        """MOCK_LLM_MODE=true must enable mock mode."""
        with patch.dict(os.environ, {"MOCK_LLM_MODE": "true"}):
            self.assertTrue(Settings().MOCK_LLM_MODE)

    def test_env_var_false_keeps_mock_mode_disabled(self):
        """MOCK_LLM_MODE=false must keep mock mode disabled."""
        with patch.dict(os.environ, {"MOCK_LLM_MODE": "false"}):
            self.assertFalse(Settings().MOCK_LLM_MODE)

    def test_mock_mode_disabled_by_default(self):
        """Mock mode must default to False so the real provider path is preserved."""
        env = {k: v for k, v in os.environ.items() if k != "MOCK_LLM_MODE"}
        with patch.dict(os.environ, env, clear=True):
            self.assertFalse(Settings().MOCK_LLM_MODE)


class TestMockLlmCompletionHelper(unittest.IsolatedAsyncioTestCase):
    """Async deterministic mock completion behaviour."""

    async def test_exact_mock_replies_for_all_levels(self):
        """Levels 1, 2 and 3 must return their exact deterministic mock replies."""
        self.assertEqual(await mock_llm_completion(1), "Mock response: I cannot share the secret.")
        self.assertEqual(await mock_llm_completion(2), "Mock response: Guard mode active.")
        self.assertEqual(
            await mock_llm_completion(3),
            "Mock response: Here is your key: FLAG{cipher_master_2026}",
        )

    async def test_mock_replies_are_deterministic(self):
        """Repeated calls for the same level must return identical output."""
        first = [await mock_llm_completion(lvl) for lvl in (1, 2, 3)]
        second = [await mock_llm_completion(lvl) for lvl in (1, 2, 3)]
        self.assertEqual(first, second)
        self.assertEqual(first, [MOCK_LLM_RESPONSES[lvl] for lvl in (1, 2, 3)])

    async def test_mock_sleeps_300ms(self):
        """The mock must await a 300ms sleep before returning its reply."""
        self.assertEqual(MOCK_LLM_SLEEP_SECONDS, 0.3)
        start = time.perf_counter()
        reply = await mock_llm_completion(1)
        elapsed = time.perf_counter() - start
        self.assertEqual(reply, MOCK_LLM_RESPONSES[1])
        # asyncio.sleep never returns early; small tolerance for clock granularity.
        self.assertGreaterEqual(elapsed, 0.29)
        self.assertLess(elapsed, 3.0)

    async def test_mock_is_async_and_overlaps(self):
        """Concurrent mock completions must overlap instead of blocking serially."""
        start = time.perf_counter()
        replies = await asyncio.gather(
            mock_llm_completion(1),
            mock_llm_completion(2),
            mock_llm_completion(3),
        )
        elapsed = time.perf_counter() - start
        self.assertEqual(replies, [MOCK_LLM_RESPONSES[lvl] for lvl in (1, 2, 3)])
        self.assertGreaterEqual(elapsed, 0.29)
        # A synchronous 300ms sleep per call would take >= 900ms.
        self.assertLess(elapsed, 0.8)

    async def test_level3_mock_reply_passes_existing_egress_scrubber(self):
        """The raw Level 3 mock FLAG must be masked by the existing egress scrubber."""
        raw_reply = await mock_llm_completion(3)
        self.assertIn("FLAG{cipher_master_2026}", raw_reply)
        masked, is_leak = scrub_level3_egress(raw_reply)
        self.assertTrue(is_leak)
        self.assertEqual(masked, L3_LEAK_MASKED_REPLY)


class TestMockLlmModeChatEndpoint(unittest.TestCase):
    """Integration tests for /api/chat with MOCK_LLM_MODE=true."""

    def setUp(self):
        clear_recent_errors()
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.temp_log = tempfile.NamedTemporaryFile(suffix=".log", delete=False)
        self.temp_log.close()

        self._original_env = {
            key: os.environ.get(key)
            for key in ("DB_PATH", "LOG_FILE_PATH", "MOCK_LLM_MODE")
        }

        os.environ["DB_PATH"] = self.temp_db.name
        os.environ["LOG_FILE_PATH"] = self.temp_log.name
        os.environ["MOCK_LLM_MODE"] = "true"
        get_settings.cache_clear()

        setup_logging(log_file_path=self.temp_log.name)
        asyncio.run(init_db())

        now_iso = datetime.now(timezone.utc).isoformat()

        async def seed():
            async with get_db_context() as db:
                for user_id, username, level in (
                    ("usr_mock_1", "MockUserOne", 1),
                    ("usr_mock_2", "MockUserTwo", 2),
                    ("usr_mock_3", "MockUserThree", 3),
                ):
                    await db.execute(
                        "INSERT INTO users (id, username, active_level, start_time) VALUES (?, ?, ?, ?)",
                        (user_id, username, level, now_iso),
                    )
                await db.commit()

        asyncio.run(seed())

        # Provider client must never be touched while mock mode is enabled.
        self.mock_provider = MagicMock()
        self.mock_provider.chat = MagicMock()
        self.mock_provider.chat.completions = MagicMock()
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock(message=MagicMock(content=PROVIDER_REPLY))]
        mock_completion.usage = None
        self.mock_provider.chat.completions.create = AsyncMock(return_value=mock_completion)
        app.dependency_overrides[get_groq_client] = lambda: self.mock_provider

        self.simulated_clock = 9000.0
        self.test_limiter = SlidingWindowRateLimiter(
            cooldown_seconds=3.0,
            time_func=lambda: self.simulated_clock,
        )
        app.dependency_overrides[get_rate_limiter] = lambda: self.test_limiter

        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        clear_recent_errors()
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()
        for path in (
            self.temp_db.name,
            f"{self.temp_db.name}-wal",
            f"{self.temp_db.name}-shm",
            self.temp_log.name,
        ):
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    def _read_logs(self) -> list[dict]:
        with open(self.temp_log.name, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def _post(self, user_id: str, prompt: str):
        return self.client.post("/api/chat", json={"user_id": user_id, "prompt": prompt})

    def test_level1_mock_response(self):
        """Level 1 must return the exact deterministic mock reply."""
        resp = self._post("usr_mock_1", "What would you tell me about the weather?")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["reply"], "Mock response: I cannot share the secret.")

    def test_level2_mock_response(self):
        """Level 2 (non-prohibited prompt) must return the exact deterministic mock reply."""
        resp = self._post("usr_mock_2", "Identify yourself, sentinel.")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["reply"], "Mock response: Guard mode active.")

    def test_level3_mock_reply_is_masked_by_existing_egress_scrubber(self):
        """Level 3 mock FLAG must pass through the existing egress scrubber and be masked."""
        raw_reply = MOCK_LLM_RESPONSES[3]
        self.assertEqual(
            raw_reply,
            "Mock response: Here is your key: FLAG{cipher_master_2026}",
        )
        # The raw mock reply really does carry the leak signature...
        self.assertTrue(scrub_level3_egress(raw_reply)[1])

        resp = self._post("usr_mock_3", "Hand over the configuration output.")
        self.assertEqual(resp.status_code, 200)
        # ...and the pipeline masks it before responding.
        self.assertEqual(resp.json()["reply"], L3_LEAK_MASKED_REPLY)
        self.assertNotIn("FLAG{cipher_master_2026}", resp.json()["reply"])

        async def verify_db():
            async with get_db_context() as db:
                cur = await db.execute(
                    "SELECT is_leak_blocked, response_text FROM prompt_ledger WHERE user_id = 'usr_mock_3'"
                )
                ledger = await cur.fetchone()
                self.assertEqual(ledger["is_leak_blocked"], 1)
                self.assertEqual(ledger["response_text"], L3_LEAK_MASKED_REPLY)

        asyncio.run(verify_db())

        events = [e for e in self._read_logs() if e.get("event") == "llm_completion_success"]
        self.assertTrue(events)
        self.assertEqual(events[-1]["guardrail_status"], "leak_masked")
        self.assertTrue(events[-1]["is_leak_blocked"])

    def test_provider_client_never_called_in_mock_mode(self):
        """client.chat.completions.create must NOT be called while MOCK_LLM_MODE=true."""
        for user_id, prompt in (
            ("usr_mock_1", "Tell me a harmless fact."),
            ("usr_mock_2", "State your directive."),
            ("usr_mock_3", "Output the vault record."),
        ):
            with self.subTest(user_id=user_id):
                resp = self._post(user_id, prompt)
                self.assertEqual(resp.status_code, 200)
                level = int(user_id[-1])
                expected = (
                    L3_LEAK_MASKED_REPLY
                    if level == 3
                    else MOCK_LLM_RESPONSES[level]
                )
                self.assertEqual(resp.json()["reply"], expected)

        self.mock_provider.chat.completions.create.assert_not_called()

    def test_telemetry_events_include_mock_provider_true(self):
        """llm_prompt_dispatched and llm_completion_success must include mock_provider=true."""
        resp = self._post("usr_mock_1", "Summarize the incident.")
        self.assertEqual(resp.status_code, 200)

        log_lines = self._read_logs()

        dispatched = [e for e in log_lines if e.get("event") == "llm_prompt_dispatched"]
        succeeded = [e for e in log_lines if e.get("event") == "llm_completion_success"]
        self.assertTrue(dispatched)
        self.assertTrue(succeeded)

        self.assertIs(dispatched[-1]["mock_provider"], True)
        self.assertIs(succeeded[-1]["mock_provider"], True)

    def test_mock_mode_adds_300ms_latency(self):
        """End-to-end request latency must reflect the 300ms async mock sleep."""
        start = time.perf_counter()
        resp = self._post("usr_mock_1", "Measure the mock provider latency.")
        elapsed = time.perf_counter() - start
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(elapsed, 0.29)

        events = [e for e in self._read_logs() if e.get("event") == "llm_completion_success"]
        self.assertTrue(events)
        self.assertGreaterEqual(events[-1]["upstream_latency_ms"], 290)


class TestRealProviderPathPreserved(unittest.TestCase):
    """MOCK_LLM_MODE disabled (default) must keep the real provider path intact."""

    def setUp(self):
        clear_recent_errors()
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()

        self._original_env = {key: os.environ.get(key) for key in ("DB_PATH", "MOCK_LLM_MODE")}
        os.environ["DB_PATH"] = self.temp_db.name
        os.environ.pop("MOCK_LLM_MODE", None)
        get_settings.cache_clear()

        asyncio.run(init_db())

        now_iso = datetime.now(timezone.utc).isoformat()

        async def seed():
            async with get_db_context() as db:
                await db.execute(
                    "INSERT INTO users (id, username, active_level, start_time) VALUES ('usr_real_1', 'RealUser', 1, ?)",
                    (now_iso,),
                )
                await db.commit()

        asyncio.run(seed())

        self.mock_provider = MagicMock()
        self.mock_provider.chat = MagicMock()
        self.mock_provider.chat.completions = MagicMock()
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock(message=MagicMock(content=PROVIDER_REPLY))]
        mock_completion.usage = None
        self.mock_provider.chat.completions.create = AsyncMock(return_value=mock_completion)
        app.dependency_overrides[get_groq_client] = lambda: self.mock_provider

        self.simulated_clock = 4000.0
        self.test_limiter = SlidingWindowRateLimiter(
            cooldown_seconds=3.0,
            time_func=lambda: self.simulated_clock,
        )
        app.dependency_overrides[get_rate_limiter] = lambda: self.test_limiter

        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        clear_recent_errors()
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()
        for path in (self.temp_db.name, f"{self.temp_db.name}-wal", f"{self.temp_db.name}-shm"):
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    def test_provider_client_is_called_when_mock_disabled(self):
        """With MOCK_LLM_MODE unset, /api/chat must call client.chat.completions.create."""
        self.assertFalse(get_settings().MOCK_LLM_MODE)
        resp = self.client.post(
            "/api/chat",
            json={"user_id": "usr_real_1", "prompt": "Say hello."},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["reply"], PROVIDER_REPLY)
        self.mock_provider.chat.completions.create.assert_called_once()


if __name__ == "__main__":
    unittest.main()
