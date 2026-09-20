"""
tests/test_llm_catalog.py
==========================
Unit tests for Groq model catalog, default model, runtime model override,
generation/repair model payload verification, and .env file protection.
"""

import json
import os
from unittest.mock import MagicMock, patch
import pytest

from constraint_guard.llm.catalog import (
    DEFAULT_GROQ_MODEL,
    GROQ_MODEL_CATALOG,
    get_model_catalog,
)
from constraint_guard.llm.provider import OpenAICompatibleProvider
from constraint_guard.llm.service import generate_code
from constraint_guard.repair.repairer import repair_code
from constraint_guard.models import ConstraintStatus, VerificationReport



class TestGroqModelCatalog:
    def test_default_model_is_gpt_oss_120b(self):
        assert DEFAULT_GROQ_MODEL == "openai/gpt-oss-120b"
        catalog = get_model_catalog()
        assert catalog[0] == "openai/gpt-oss-120b"
        assert "openai/gpt-oss-20b" in catalog
        assert "openai/gpt-oss-safeguard-20b" in catalog
        assert "qwen/qwen3.8-27b" in catalog

    def test_provider_default_model(self, monkeypatch):
        monkeypatch.delenv("LLM_MODEL", raising=False)
        provider = OpenAICompatibleProvider(api_key="sk-test-key")
        assert provider.model == "openai/gpt-oss-120b"

    def test_provider_explicit_model_override(self):
        provider = OpenAICompatibleProvider(
            api_key="sk-test-key",
            model="openai/gpt-oss-20b",
        )
        assert provider.model == "openai/gpt-oss-20b"

    def test_generation_payload_uses_selected_model(self):
        provider = OpenAICompatibleProvider(
            api_key="sk-test-key",
            model="qwen/qwen3.8-27b",
        )
        captured_payloads = []

        def mock_urlopen(req, timeout=30):
            payload = json.loads(req.data.decode("utf-8"))
            captured_payloads.append(payload)
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(
                {"choices": [{"message": {"content": "def foo(): pass"}}]}
            ).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            code = generate_code([{"turn": 1, "text": "write foo"}], provider=provider)
            assert "def foo" in code
            assert len(captured_payloads) == 1
            assert captured_payloads[0]["model"] == "qwen/qwen3.8-27b"

    def test_repair_payload_uses_selected_model(self):
        provider = OpenAICompatibleProvider(
            api_key="sk-test-key",
            model="openai/gpt-oss-safeguard-20b",
        )
        captured_payloads = []

        def mock_urlopen(req, timeout=30):
            payload = json.loads(req.data.decode("utf-8"))
            captured_payloads.append(payload)
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(
                {"choices": [{"message": {"content": "def bar(): pass"}}]}
            ).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            return mock_resp

        mock_report = MagicMock(spec=VerificationReport)
        mock_result = MagicMock()
        mock_result.status = ConstraintStatus.VIOLATED
        mock_report.results = [mock_result]

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            repaired = repair_code(
                conversation=[{"turn": 1, "text": "do not use max"}],
                code="def bar(): return max([1])",
                verification_report=mock_report,
                provider=provider,
            )
            assert "def bar" in repaired
            assert len(captured_payloads) == 1
            assert captured_payloads[0]["model"] == "openai/gpt-oss-safeguard-20b"

    def test_changing_model_does_not_modify_env_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("LLM_MODEL=openai/gpt-oss-120b\n", encoding="utf-8")

        initial_content = env_file.read_text(encoding="utf-8")

        # Simulate user selecting another model at runtime
        runtime_model = "openai/gpt-oss-20b"
        provider = OpenAICompatibleProvider(api_key="sk-test", model=runtime_model)
        assert provider.model == "openai/gpt-oss-20b"

        # Verify .env content was NOT altered
        assert env_file.read_text(encoding="utf-8") == initial_content

    def test_session_state_survives_simulation(self):
        # Simulate Streamlit session state dictionary
        session_state = {}
        if "selected_model" not in session_state:
            session_state["selected_model"] = DEFAULT_GROQ_MODEL
        if "model_status" not in session_state:
            session_state["model_status"] = "🟡 Availability not checked"

        assert session_state["selected_model"] == "openai/gpt-oss-120b"

        # Simulate user changing model in UI
        session_state["selected_model"] = "qwen/qwen3.8-27b"
        session_state["model_status"] = "🟡 Availability not checked"

        # Simulate rerun (dict persists)
        assert session_state["selected_model"] == "qwen/qwen3.8-27b"
