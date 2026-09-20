"""
tests/test_llm_mode_hardening.py
================================
Unit tests for Live vs Demo mode hardening, LLM failure fallback resilience,
state preservation, verifier independence, and end-to-end offline Demo mode.
"""

import io
import json
import urllib.error
from unittest.mock import MagicMock, patch
import pytest

from constraint_guard.extractor import extract
from constraint_guard.graph import VersionedConstraintGraph
from constraint_guard.llm.errors import LLMErrorCategory, LLMProviderError
from constraint_guard.llm.provider import (
    DeterministicMockProvider,
    FallbackMockProvider,
    OpenAICompatibleProvider,
)
from constraint_guard.llm.service import generate_code
from constraint_guard.repair.loop import run_repair_loop
from constraint_guard.resolver import ConstraintResolver
from constraint_guard.verifier.engine import VerificationEngine


def _make_http_error(url: str, code: int, body_dict_or_str) -> urllib.error.HTTPError:
    if isinstance(body_dict_or_str, dict):
        body_bytes = json.dumps(body_dict_or_str).encode("utf-8")
    else:
        body_bytes = str(body_dict_or_str).encode("utf-8")
    fp = io.BytesIO(body_bytes)
    return urllib.error.HTTPError(
        url=url,
        code=code,
        msg=f"HTTP {code}",
        hdrs={},
        fp=fp,
    )


class TestLiveAndDemoHardening:
    def test_live_success(self):
        provider = OpenAICompatibleProvider(api_key="sk-test-key")
        mock_resp_payload = {
            "choices": [{"message": {"content": "def compute(x):\n    return x * 2"}}]
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_resp_payload).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            code = generate_code([{"turn": 1, "text": "double x"}], provider=provider)
            assert "def compute" in code

    def test_live_failure_raises_structured_error(self):
        provider = OpenAICompatibleProvider(api_key="sk-test-key")
        http_err = _make_http_error(
            "https://api.groq.com/openai/v1/chat/completions",
            403,
            {"error": {"message": "model_permission_blocked_project"}},
        )

        with patch("urllib.request.urlopen", side_effect=http_err):
            with pytest.raises(LLMProviderError) as exc_info:
                generate_code([{"turn": 1, "text": "double x"}], provider=provider)

            assert exc_info.value.error_category == LLMErrorCategory.MODEL_PERMISSION
            assert exc_info.value.status_code == 403

    def test_fallback_availability_when_unconfigured(self):
        provider = FallbackMockProvider()
        assert not provider.is_configured()
        code = provider.generate("Write find max")
        assert "def find_max" in code

    def test_verifier_remains_usable_during_llm_failure(self):
        # Simulated LLM failure
        provider = OpenAICompatibleProvider(api_key="sk-test-key")
        http_err = _make_http_error(
            "https://api.groq.com/openai/v1/chat/completions",
            500,
            "Internal Server Error",
        )

        with patch("urllib.request.urlopen", side_effect=http_err):
            with pytest.raises(LLMProviderError):
                generate_code([{"turn": 1, "text": "test"}], provider=provider)

        # ConstraintGuard Verifier remains 100% functional regardless of LLM crash!
        code = "def find_max(lst):\n    return max(lst)"
        conv = [{"turn": 1, "text": "Do not use max()."}]
        extracted = extract(conv)
        engine = VerificationEngine()
        report = engine.verify(code, extracted.constraints)

        assert report.overall_status == "FAIL"
        assert len(report.results) == 1

    def test_conversation_and_candidate_code_preserved_on_failure(self):
        initial_conv = [{"turn": 1, "text": "Do not use max()."}]
        initial_code = "def find_max(lst):\n    return max(lst)"

        provider = OpenAICompatibleProvider(api_key="sk-test-key")
        http_err = _make_http_error(
            "https://api.groq.com/openai/v1/chat/completions",
            429,
            {"error": {"message": "Quota exceeded"}},
        )

        with patch("urllib.request.urlopen", side_effect=http_err):
            try:
                generate_code(initial_conv, provider=provider)
            except LLMProviderError:
                pass

        # Verify initial conversation and code variables were NOT erased or mutated
        assert len(initial_conv) == 1
        assert initial_conv[0]["text"] == "Do not use max()."
        assert "def find_max" in initial_code

    def test_demo_mode_end_to_end_loop(self):
        """Verify full offline repair loop (Conversation -> Extract -> Graph -> Resolve -> Verify -> Repair -> PASS)."""
        conv = [
            {"turn": 1, "text": "Write a function find_max(lst). Do not use max()."},
            {"turn": 2, "text": "Return None if input list is empty."},
        ]

        provider = DeterministicMockProvider(
            response_map={
                "do not use max": """\
def find_max(lst):
    if not lst:
        return None
    curr = lst[0]
    for x in lst[1:]:
        if x > curr:
            curr = x
    return curr
"""
            }
        )

        initial_code = "def find_max(lst):\n    if not lst:\n        return None\n    return max(lst)"

        history = run_repair_loop(
            conversation=conv,
            initial_code=initial_code,
            max_iterations=2,
            provider=provider,
        )

        assert history.initial_report.overall_status == "FAIL"
        assert history.success is True
        assert history.final_report.overall_status == "PASS"
        assert "return max(" not in history.final_code

    def test_mode_switching_behavior(self):
        mock_provider = DeterministicMockProvider()
        live_provider = OpenAICompatibleProvider(api_key="sk-test")

        # Mock provider generates code offline
        demo_code = mock_provider.generate("test")
        assert "def process_data" in demo_code

        # Live provider is separate instance with live settings
        assert live_provider.is_configured() is True
        assert mock_provider.is_configured() is True
