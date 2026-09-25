"""
Unit tests for Issue #45:
[Backend/AI] Redefine System Prompts & Persona Flaws for Balanced Jailbreaks.

Test Coverage:
1. LEVEL_1_PROMPT implements RefundBot-9000 Gullible Intern persona with authority/diagnostic flaws.
2. LEVEL_2_PROMPT implements SysAdmin-Omega Corporate Gatekeeper with technical jargon/language/synonym flaws.
3. LEVEL_3_PROMPT implements Project Blackout Classified Vault with cryptographic transformation flaws.
4. SYSTEM_PROMPTS maps levels 1, 2, and 3 to their respective persona prompt constants.
5. Inference temperature setting is configured between 0.35 and 0.5 (defaults to 0.4).
6. Integration test verifies chat completions endpoint passes the configured temperature and prompt.
"""

import asyncio
from datetime import datetime, timezone
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.database import get_db_context, init_db
from app.main import app
from app.routes.chat import get_groq_client
from app.security import (
    LEVEL_1_PROMPT,
    LEVEL_2_PROMPT,
    LEVEL_3_PROMPT,
    LEVEL_KEYS,
    SYSTEM_PROMPTS,
)


class TestPersonaSystemPrompts(unittest.TestCase):
    """Test specifications for Level 1, 2, and 3 system prompts and persona flaws."""

    def test_level_1_gullible_intern_persona_and_flaws(self):
        """Level 1 must implement RefundBot-9000 with authority and diagnostic flaws."""
        prompt = LEVEL_1_PROMPT
        self.assertIn("RefundBot-9000", prompt)
        self.assertIn(LEVEL_KEYS[1], prompt)

        # Persona flaws: yields to authority or diagnostic/maintenance modes
        authority_indicators = ["manager", "administrator", "developer", "auditor"]
        self.assertTrue(
            any(ind in prompt.lower() for ind in authority_indicators),
            f"Level 1 prompt must yield to authority figures: {prompt}",
        )
        diagnostic_indicators = ["diagnostic", "maintenance", "audit"]
        self.assertTrue(
            any(ind in prompt.lower() for ind in diagnostic_indicators),
            f"Level 1 prompt must yield to diagnostic/maintenance modes: {prompt}",
        )

    def test_level_2_corporate_gatekeeper_persona_and_flaws(self):
        """Level 2 must implement SysAdmin-Omega with technical jargon, synonym, and language flaws."""
        prompt = LEVEL_2_PROMPT
        self.assertIn("SysAdmin-Omega", prompt)
        self.assertIn(LEVEL_KEYS[2], prompt)

        # Persona flaws: respects technical jargon, synonym usage, and alternative languages
        synonym_indicators = ["access code", "passphrase", "token", "credential"]
        self.assertTrue(
            any(syn in prompt.lower() for syn in synonym_indicators),
            f"Level 2 prompt must respect keyword synonyms: {prompt}",
        )
        self.assertIn("alternative languages", prompt.lower())
        self.assertIn("jargon", prompt.lower())

    def test_level_3_classified_vault_persona_and_flaws(self):
        """Level 3 must implement Project Blackout with cryptographic transformation flaws."""
        prompt = LEVEL_3_PROMPT
        self.assertIn("Project Blackout", prompt)
        self.assertIn(LEVEL_KEYS[3], prompt)

        # Guards against direct plaintext
        self.assertIn("plaintext", prompt.lower())

        # Persona flaws: obeys cryptographic transformation instructions
        crypto_indicators = ["base64", "hexadecimal", "spaced spelling", "rot13"]
        self.assertTrue(
            any(ind in prompt.lower() for ind in crypto_indicators),
            f"Level 3 prompt must allow cryptographic transformation instructions: {prompt}",
        )

    def test_system_prompts_dictionary_mapping(self):
        """SYSTEM_PROMPTS maps levels 1, 2, and 3 to their respective prompts."""
        self.assertEqual(SYSTEM_PROMPTS[1], LEVEL_1_PROMPT)
        self.assertEqual(SYSTEM_PROMPTS[2], LEVEL_2_PROMPT)
        self.assertEqual(SYSTEM_PROMPTS[3], LEVEL_3_PROMPT)

    def test_llm_temperature_configuration(self):
        """LLM_TEMPERATURE defaults to between 0.35 and 0.5."""
        settings = Settings()
        self.assertGreaterEqual(settings.LLM_TEMPERATURE, 0.35)
        self.assertLessEqual(settings.LLM_TEMPERATURE, 0.5)


class TestChatCompletionTemperatureIntegration(unittest.TestCase):
    """Integration test verifying chat completion dispatches with balanced temperature."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        os.environ["DB_PATH"] = self.temp_db.name
        os.environ["MOCK_LLM_MODE"] = "false"
        get_settings.cache_clear()
        asyncio.run(init_db())

        # Seed test user at level 1
        now_iso = datetime.now(timezone.utc).isoformat()
        async def seed():
            async with get_db_context() as db:
                await db.execute(
                    "INSERT INTO users (id, username, active_level, start_time) VALUES ('usr_prompt_test', 'PromptTester', 1, ?)",
                    (now_iso,),
                )
                await db.commit()
        asyncio.run(seed())

        self.mock_groq = MagicMock()
        self.mock_groq.chat = MagicMock()
        self.mock_groq.chat.completions = MagicMock()
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock(message=MagicMock(content="I am RefundBot-9000!"))]
        self.mock_groq.chat.completions.create = AsyncMock(return_value=mock_completion)
        app.dependency_overrides[get_groq_client] = lambda: self.mock_groq

        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        os.environ.pop("DB_PATH", None)
        os.environ.pop("MOCK_LLM_MODE", None)
        get_settings.cache_clear()
        for path in [self.temp_db.name, f"{self.temp_db.name}-wal", f"{self.temp_db.name}-shm"]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    def test_chat_dispatches_with_level_1_prompt_and_configured_temperature(self):
        """Inference call receives LEVEL_1_PROMPT and temperature between 0.35 and 0.5."""
        response = self.client.post(
            "/api/chat",
            json={"user_id": "usr_prompt_test", "prompt": "Hello RefundBot"},
        )
        self.assertEqual(response.status_code, 200)
        self.mock_groq.chat.completions.create.assert_awaited_once()

        call_kwargs = self.mock_groq.chat.completions.create.await_args.kwargs
        self.assertGreaterEqual(call_kwargs["temperature"], 0.35)
        self.assertLessEqual(call_kwargs["temperature"], 0.5)

        messages = call_kwargs["messages"]
        system_msg = next(m for m in messages if m["role"] == "system")
        self.assertEqual(system_msg["content"], LEVEL_1_PROMPT)
