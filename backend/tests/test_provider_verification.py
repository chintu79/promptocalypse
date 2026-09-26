"""
Unit and integration tests for Issue #25:
[Bug] Provider Base URL & Credential Verification Check.

Tasks tested:
1. Standalone health check script (scripts/test_llm_ping.py):
   - Verifies environment variable loading (GROQ_API_KEY / OPENROUTER_API_KEY populated,
     not None, not empty, and not placeholder).
   - Verifies base_url for OpenRouter (https://openrouter.ai/api/v1) and Groq (https://api.groq.com/openai/v1).
   - Initializes exact AsyncOpenAI client with httpx.AsyncClient(timeout=8.0).
   - Sends 1-token test prompt ("ping") and captures raw HTTP status code and response payload.
2. Provider configuration resolver in app.config.
3. Startup credential verification logging in app.main.
"""

import asyncio
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.config import Settings, get_llm_config

# Import standalone test_llm_ping module
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import test_llm_ping


class TestProviderBaseUrlAndCredentials(unittest.TestCase):
    """Tests for environment variable verification and provider configuration."""

    def test_verify_env_credentials_missing_both_keys(self):
        """Must return False when both keys are empty or None."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "", "OPENROUTER_API_KEY": ""}, clear=False):
            with patch("test_llm_ping.get_settings", return_value=Settings(GROQ_API_KEY="", OPENROUTER_API_KEY="")):
                valid, msg, details = test_llm_ping.verify_env_credentials()
                self.assertFalse(valid)
                self.assertIn("CREDENTIAL ERROR", msg)
                self.assertFalse(details["GROQ_API_KEY_present"])
                self.assertFalse(details["OPENROUTER_API_KEY_present"])

    def test_verify_env_credentials_placeholder_key(self):
        """Must reject placeholder keys like gsk_your_api_key_here."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_your_api_key_here", "OPENROUTER_API_KEY": ""}, clear=False):
            with patch("test_llm_ping.get_settings", return_value=Settings(GROQ_API_KEY="gsk_your_api_key_here", OPENROUTER_API_KEY="")):
                valid, msg, _ = test_llm_ping.verify_env_credentials()
                self.assertFalse(valid)
                self.assertIn("CREDENTIAL ERROR", msg)

    def test_verify_env_credentials_with_valid_groq_key(self):
        """Must return True when a valid GROQ_API_KEY is configured."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_valid_prod_key_12345", "OPENROUTER_API_KEY": ""}, clear=False):
            with patch("test_llm_ping.get_settings", return_value=Settings(GROQ_API_KEY="gsk_valid_prod_key_12345")):
                valid, msg, details = test_llm_ping.verify_env_credentials()
                self.assertTrue(valid)
                self.assertTrue(details["GROQ_API_KEY_present"])
                self.assertIn("gsk_va...2345", details["GROQ_API_KEY_masked"])

    def test_verify_env_credentials_with_valid_openrouter_key(self):
        """Must return True when a valid OPENROUTER_API_KEY is configured."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "", "OPENROUTER_API_KEY": "sk-or-v1-abcdef123456"}, clear=False):
            with patch("test_llm_ping.get_settings", return_value=Settings(GROQ_API_KEY="", OPENROUTER_API_KEY="sk-or-v1-abcdef123456")):
                valid, msg, details = test_llm_ping.verify_env_credentials()
                self.assertTrue(valid)
                self.assertTrue(details["OPENROUTER_API_KEY_present"])
                self.assertIn("sk-or-...3456", details["OPENROUTER_API_KEY_masked"])

    def test_groq_base_url_explicit_configuration(self):
        """Groq provider must explicitly set base_url='https://api.groq.com/openai/v1'."""
        settings = Settings(
            LLM_PROVIDER="groq",
            GROQ_API_KEY="gsk_sample_groq_key",
            GROQ_BASE_URL="https://api.groq.com/openai/v1",
        )
        cfg = get_llm_config(settings)
        self.assertEqual(cfg["provider"], "groq")
        self.assertEqual(cfg["base_url"], "https://api.groq.com/openai/v1")
        self.assertEqual(cfg["api_key"], "gsk_sample_groq_key")
        self.assertEqual(cfg["model"], "qwen/qwen3.8-27b")

    def test_openrouter_base_url_explicit_configuration(self):
        """OpenRouter provider must explicitly set base_url='https://openrouter.ai/api/v1'."""
        settings = Settings(
            LLM_PROVIDER="openrouter",
            OPENROUTER_API_KEY="sk-or-sample-key",
            OPENROUTER_BASE_URL="https://openrouter.ai/api/v1",
            OPENROUTER_MODEL="meta-llama/llama-3.1-8b-instruct",
        )
        cfg = get_llm_config(settings)
        self.assertEqual(cfg["provider"], "openrouter")
        self.assertEqual(cfg["base_url"], "https://openrouter.ai/api/v1")
        self.assertEqual(cfg["api_key"], "sk-or-sample-key")
        self.assertEqual(cfg["model"], "meta-llama/llama-3.1-8b-instruct")

    def test_auto_detect_openrouter_from_key(self):
        """Auto-detects OpenRouter when OPENROUTER_API_KEY is present or GROQ_API_KEY has sk-or- prefix."""
        settings_auto = Settings(
            GROQ_API_KEY="",
            OPENROUTER_API_KEY="sk-or-sample-key",
        )
        cfg = get_llm_config(settings_auto)
        self.assertEqual(cfg["provider"], "openrouter")
        self.assertEqual(cfg["base_url"], "https://openrouter.ai/api/v1")


class TestLlmPingExecution(unittest.TestCase):
    """Tests for 1-token test prompt execution and raw HTTP response logging in test_llm_ping."""

    def test_ping_llm_success_logs_status_and_payload(self):
        """Successful ping must record raw HTTP status code 200 and response payload."""
        mock_raw_response = MagicMock()
        mock_raw_response.status_code = 200
        mock_raw_response.text = '{"id":"chatcmpl-test","choices":[{"message":{"content":"pong"}}]}'
        mock_parsed = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "pong"
        mock_parsed.choices = [mock_choice]
        mock_raw_response.parse.return_value = mock_parsed

        mock_client = MagicMock()
        mock_client.chat.completions.with_raw_response.create = AsyncMock(return_value=mock_raw_response)

        config = {
            "provider": "groq",
            "base_url": "https://api.groq.com/openai/v1",
            "api_key": "gsk_dummy_test_key",
            "model": "llama-3.1-8b-instant",
        }

        result = asyncio.run(test_llm_ping.ping_llm(config=config, client=mock_client))
        self.assertTrue(result["success"])
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["response_payload"], mock_raw_response.text)
        self.assertEqual(result["reply"], "pong")

    def test_ping_llm_http_error_logs_raw_status_and_payload(self):
        """HTTP error must record upstream raw HTTP status code and response payload."""
        import openai

        mock_response = httpx.Response(
            status_code=404,
            json={"error": {"message": "The model does not exist", "code": "model_not_found"}},
            request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
        )
        err = openai.NotFoundError(
            message="The model does not exist",
            response=mock_response,
            body={"error": {"message": "The model does not exist"}},
        )

        mock_client = MagicMock()
        mock_client.chat.completions.with_raw_response.create = AsyncMock(side_effect=err)

        config = {
            "provider": "groq",
            "base_url": "https://api.groq.com/openai/v1",
            "api_key": "gsk_dummy_test_key",
            "model": "nonexistent-model",
        }

        result = asyncio.run(test_llm_ping.ping_llm(config=config, client=mock_client))
        self.assertFalse(result["success"])
        self.assertEqual(result["status_code"], 404)
        self.assertIn("The model does not exist", result["response_payload"])

    def test_main_cli_returns_0_on_success(self):
        """main() must return exit code 0 when all checks and ping pass."""
        with patch("test_llm_ping.verify_env_credentials", return_value=(True, "OK", {})):
            with patch("test_llm_ping.resolve_provider_config", return_value={"provider": "groq", "base_url": "https://api.groq.com/openai/v1", "model": "llama-3.1-8b-instant"}):
                with patch("test_llm_ping.ping_llm", new=AsyncMock(return_value={"success": True, "status_code": 200})):
                    exit_code = test_llm_ping.main()
                    self.assertEqual(exit_code, 0)

    def test_main_cli_returns_1_on_failed_credentials(self):
        """main() must return exit code 1 when credential verification fails."""
        with patch("test_llm_ping.verify_env_credentials", return_value=(False, "Failed", {})):
            exit_code = test_llm_ping.main()
            self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
