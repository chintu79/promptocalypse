"""
Tests for Issue #26:
[Backend] Health & Readiness Diagnostic Probe (/api/health).

Test Coverage:
1. Healthy end-to-end response shape (overall status, database, provider, timestamp).
2. Database probe: SELECT 1 verification and latency measurement.
3. WAL verification: PRAGMA journal_mode reports 'wal'.
4. Provider success via the mocked get_groq_client dependency (no real network).
5. 60-second provider result cache semantics (1, 2, and exactly 60s boundary).
6. Provider failure → HTTP 200 with overall 'degraded' status.
7. Database failure → HTTP 503 with overall 'error' status.
8. Empty GROQ_API_KEY → provider 'unconfigured' state without upstream calls.
9. Telemetry middleware attaches X-Process-Time to /api/health.
10. CORS origin mirroring on /api/health.
Extras:
- Status transitions are logged once; steady-state probes never flood logs.
- Provider probe enforces a short timeout (not the 8s chat timeout).
- Legacy GET /health behavior is unchanged.
"""

import asyncio
import logging
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import init_db
from app.logger import clear_recent_errors
from app.main import app
from app.routes.chat import get_groq_client
from app.routes.health import (
    PROVIDER_CACHE_TTL_SECONDS,
    PROVIDER_PROBE_TIMEOUT_SECONDS,
    ProviderHealthCache,
    get_provider_health_cache,
    reset_health_status_logging,
    router as health_router,
)


class TestHealthEndpoint(unittest.TestCase):
    """Integration tests for GET /api/health using the standard test harness."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        os.environ["DB_PATH"] = self.temp_db.name
        # Save any pre-existing key so tearDown can restore it untouched.
        self._original_groq_key = os.environ.get("GROQ_API_KEY")
        os.environ["GROQ_API_KEY"] = "gsk_test_health_dummy_key"
        get_settings.cache_clear()
        asyncio.run(init_db())
        reset_health_status_logging()

        # Simulated monotonic clock for the 60-second provider cache
        # (same pattern as the rate limiter tests).
        self.simulated_clock = 1000.0
        self.test_cache = ProviderHealthCache(time_func=lambda: self.simulated_clock)
        app.dependency_overrides[get_provider_health_cache] = lambda: self.test_cache

        # Mock Groq client: get_groq_client is overridden so no real
        # network calls are ever made from unit tests.
        self.mock_groq = MagicMock()
        self.mock_groq.models = MagicMock()
        self.mock_groq.models.list = AsyncMock(return_value=MagicMock(data=[]))
        app.dependency_overrides[get_groq_client] = lambda: self.mock_groq

        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        reset_health_status_logging()
        clear_recent_errors()
        if self._original_groq_key is None:
            os.environ.pop("GROQ_API_KEY", None)
        else:
            os.environ["GROQ_API_KEY"] = self._original_groq_key
        os.environ.pop("DB_PATH", None)
        get_settings.cache_clear()
        for path in [self.temp_db.name, f"{self.temp_db.name}-wal", f"{self.temp_db.name}-shm"]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # 1. Healthy end-to-end response shape
    # ------------------------------------------------------------------
    def test_healthy_response_shape(self):
        """GET /api/health returns the full structured payload with overall 'ok'."""
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)

        body = res.json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("database", body)
        self.assertIn("provider", body)
        self.assertIn("timestamp", body)
        self.assertTrue(body["timestamp"].endswith("Z"))

        self.assertEqual(body["database"]["status"], "ok")
        self.assertEqual(body["provider"]["status"], "ok")
        self.assertEqual(body["provider"]["name"], "groq")
        self.assertEqual(body["provider"]["model"], get_settings().GROQ_MODEL)
        self.assertIsInstance(body["provider"]["checked_at"], str)

    # ------------------------------------------------------------------
    # 2. Database probe: SELECT 1 + latency
    # ------------------------------------------------------------------
    def test_database_probe_latency(self):
        """Database probe runs SELECT 1 and reports a numeric latency >= 0."""
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)

        database = res.json()["database"]
        self.assertEqual(database["status"], "ok")
        self.assertIsNone(database["error"])
        self.assertIsInstance(database["latency_ms"], int)
        self.assertGreaterEqual(database["latency_ms"], 0)

    # ------------------------------------------------------------------
    # 3. WAL verification
    # ------------------------------------------------------------------
    def test_database_reports_wal_mode(self):
        """The probe connection verifies SQLite is in WAL journal mode."""
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)

        database = res.json()["database"]
        self.assertEqual(database["journal_mode"], "wal")

    # ------------------------------------------------------------------
    # 4. Provider success (mocked — no real Groq call)
    # ------------------------------------------------------------------
    def test_provider_success_reports_fresh_probe(self):
        """A fresh (uncached) provider probe calls models.list exactly once."""
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)

        provider = res.json()["provider"]
        self.assertEqual(provider["status"], "ok")
        self.assertIsNone(provider["error"])
        self.assertFalse(provider["cached"])
        self.assertIsInstance(provider["latency_ms"], int)
        self.assertGreaterEqual(provider["latency_ms"], 0)
        self.assertTrue(provider["checked_at"].endswith("Z"))
        self.assertEqual(self.mock_groq.models.list.await_count, 1)

    # ------------------------------------------------------------------
    # 5. 60-second cache behavior
    # ------------------------------------------------------------------
    def test_provider_result_cached_for_exactly_60_seconds(self):
        """Cache serves hits before 60s and re-probes exactly at 60s."""
        # t=0: first probe (miss)
        res1 = self.client.get("/api/health")
        self.assertEqual(res1.json()["provider"]["cached"], False)
        self.assertEqual(self.mock_groq.models.list.await_count, 1)

        # t=59.999: still fresh → cached hit, no upstream call
        self.simulated_clock += 59.999
        res2 = self.client.get("/api/health")
        self.assertEqual(res2.json()["provider"]["cached"], True)
        self.assertEqual(
            res2.json()["provider"]["checked_at"],
            res1.json()["provider"]["checked_at"],
        )
        self.assertEqual(self.mock_groq.models.list.await_count, 1)

        # t=60.000: cache expired exactly at 60s → fresh probe
        self.simulated_clock += 0.001  # now exactly 60.0s after first probe
        res3 = self.client.get("/api/health")
        self.assertEqual(res3.json()["provider"]["cached"], False)
        self.assertEqual(self.mock_groq.models.list.await_count, 2)

        # Configuration guard: TTL is exactly 60 seconds, probe timeout is short.
        self.assertEqual(PROVIDER_CACHE_TTL_SECONDS, 60.0)
        self.assertEqual(self.test_cache.ttl_seconds, 60.0)

    # ------------------------------------------------------------------
    # 6. Provider failure → 200 + degraded
    # ------------------------------------------------------------------
    def test_provider_failure_returns_degraded_200(self):
        """Upstream failure keeps HTTP 200 but reports overall 'degraded'."""
        self.mock_groq.models.list = AsyncMock(side_effect=Exception("Groq unreachable"))

        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)

        body = res.json()
        self.assertEqual(body["status"], "degraded")
        self.assertEqual(body["database"]["status"], "ok")
        self.assertEqual(body["provider"]["status"], "error")
        self.assertIn("Groq unreachable", body["provider"]["error"])

    # ------------------------------------------------------------------
    # 7. Database failure → 503 + error
    # ------------------------------------------------------------------
    def test_database_failure_returns_503(self):
        """An unavailable database yields HTTP 503 with overall 'error'."""
        bad_db_path = tempfile.mkdtemp(prefix="promptocalypse_health_")
        os.environ["DB_PATH"] = bad_db_path  # a directory → sqlite cannot open
        get_settings.cache_clear()
        try:
            res = self.client.get("/api/health")
        finally:
            os.environ["DB_PATH"] = self.temp_db.name
            get_settings.cache_clear()

        self.assertEqual(res.status_code, 503)
        body = res.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["database"]["status"], "error")
        self.assertIsNone(body["database"]["latency_ms"])
        self.assertIsNotNone(body["database"]["error"])
        # Provider section is still rendered alongside the database failure.
        self.assertEqual(body["provider"]["status"], "ok")
        os.rmdir(bad_db_path)

    # ------------------------------------------------------------------
    # 8. Empty GROQ_API_KEY → unconfigured provider
    # ------------------------------------------------------------------
    def test_empty_groq_api_key_reports_unconfigured(self):
        """An empty API key reports 'unconfigured' and never calls upstream."""
        os.environ["GROQ_API_KEY"] = ""
        get_settings.cache_clear()

        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)

        body = res.json()
        self.assertEqual(body["status"], "degraded")
        self.assertEqual(body["provider"]["status"], "unconfigured")
        self.assertIsNotNone(body["provider"]["error"])
        # No upstream network call was attempted.
        self.mock_groq.models.list.assert_not_awaited()

    # ------------------------------------------------------------------
    # 9. Telemetry header
    # ------------------------------------------------------------------
    def test_telemetry_process_time_header(self):
        """Telemetry middleware attaches X-Process-Time to /api/health."""
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        self.assertIn("x-process-time", res.headers)
        self.assertTrue(res.headers["x-process-time"].endswith("ms"))

    # ------------------------------------------------------------------
    # 10. CORS
    # ------------------------------------------------------------------
    def test_cors_mirrors_origin_on_api_health(self):
        """/api/health mirrors the request origin and never returns '*'."""
        origin = "http://localhost:5173"
        res = self.client.get("/api/health", headers={"Origin": origin})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("access-control-allow-origin"), origin)
        self.assertEqual(res.headers.get("access-control-allow-credentials"), "true")

    def test_cors_absent_without_origin_header(self):
        """Non-CORS requests to /api/health get no CORS headers."""
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("access-control-allow-origin", res.headers)

    # ------------------------------------------------------------------
    # Extras: log-flood protection, short timeout, legacy endpoint
    # ------------------------------------------------------------------
    def test_status_transition_logging_does_not_flood(self):
        """Health status transitions log once; steady-state probes stay silent."""
        captured: list[logging.LogRecord] = []

        class _Recorder(logging.Handler):
            def emit(self, record):
                if getattr(record, "event", None) == "health_status_change":
                    captured.append(record)

        recorder = _Recorder()
        arena_logger = logging.getLogger("arena")
        arena_logger.addHandler(recorder)
        try:
            # Provider down → transition into 'degraded' logged exactly once.
            self.mock_groq.models.list = AsyncMock(side_effect=Exception("provider down"))
            res1 = self.client.get("/api/health")
            self.assertEqual(res1.json()["status"], "degraded")
            res2 = self.client.get("/api/health")
            self.assertEqual(res2.json()["provider"]["cached"], True)
            self.assertEqual(len(captured), 1)
            self.assertEqual(captured[0].status, "degraded")
            self.assertIsNone(captured[0].previous_status)

            # Provider recovered → transition back to 'ok' logged once.
            self.mock_groq.models.list = AsyncMock(return_value=MagicMock())
            self.simulated_clock += PROVIDER_CACHE_TTL_SECONDS
            res3 = self.client.get("/api/health")
            self.assertEqual(res3.json()["status"], "ok")
            self.assertEqual(len(captured), 2)
            self.assertEqual(captured[1].status, "ok")

            # Steady state 'ok' → no further transition logs.
            res4 = self.client.get("/api/health")
            self.assertEqual(res4.json()["status"], "ok")
            self.assertEqual(len(captured), 2)
        finally:
            arena_logger.removeHandler(recorder)

    def test_provider_probe_uses_short_timeout(self):
        """The provider probe enforces a short timeout, not the 8s chat timeout."""
        self.assertLessEqual(PROVIDER_PROBE_TIMEOUT_SECONDS, 3.0)
        self.assertLess(PROVIDER_PROBE_TIMEOUT_SECONDS, 8.0)

        async def slow_list():
            await asyncio.sleep(1.0)
            return MagicMock()

        slow_client = SimpleNamespace(models=SimpleNamespace(list=slow_list))
        cache = ProviderHealthCache(time_func=lambda: self.simulated_clock)
        result = asyncio.run(
            cache.probe(slow_client, get_settings(), timeout_seconds=0.05)
        )
        self.assertEqual(result["status"], "error")
        self.assertIn("timed out", result["error"])

    def test_legacy_health_endpoint_unchanged(self):
        """Existing GET /health keeps returning {"status": "ok"}."""
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok"})

    def test_health_router_registered_under_api_prefix(self):
        """The new router is mounted with the /api prefix (Issue #26)."""
        paths = [route.path for route in health_router.routes]
        self.assertIn("/api/health", paths)


if __name__ == "__main__":
    unittest.main()
