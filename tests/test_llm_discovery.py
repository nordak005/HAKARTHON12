"""
tests/test_llm_discovery.py
============================
Unit tests for dynamic model discovery (list_models), model access testing
(test_model_availability), and structured availability status mapping.
"""

import io
import json
import urllib.error
from unittest.mock import MagicMock, patch
import pytest

from constraint_guard.llm.errors import LLMErrorCategory, LLMProviderError
from constraint_guard.llm.provider import OpenAICompatibleProvider


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


class TestModelDiscoveryAndAvailability:
    def test_list_models_success(self):
        provider = OpenAICompatibleProvider(api_key="sk-test-key")
        mock_resp_payload = {
            "data": [
                {"id": "openai/gpt-oss-120b", "object": "model"},
                {"id": "openai/gpt-oss-20b", "object": "model"},
            ]
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_resp_payload).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            models = provider.list_models()
            assert len(models) == 2
            assert models[0]["id"] == "openai/gpt-oss-120b"
            assert models[1]["id"] == "openai/gpt-oss-20b"

    def test_list_models_failure_does_not_crash(self):
        provider = OpenAICompatibleProvider(api_key="sk-test-key")
        http_err = _make_http_error("https://api.groq.com/openai/v1/models", 500, "Server Error")

        with patch("urllib.request.urlopen", side_effect=http_err):
            models = provider.list_models()
            assert models == []  # Handled safely without raising!

    def test_list_models_empty_response(self):
        provider = OpenAICompatibleProvider(api_key="sk-test-key")
        mock_resp = MagicMock()
        mock_resp.read.return_value = b""
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            models = provider.list_models()
            assert models == []

    def test_selected_model_available(self):
        provider = OpenAICompatibleProvider(api_key="sk-test-key", model="openai/gpt-oss-120b")
        mock_resp_payload = {
            "choices": [{"message": {"content": "pong"}}]
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_resp_payload).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            res = provider.test_model_availability("openai/gpt-oss-120b")
            assert res["available"] is True
            assert res["status_label"] == "🟢 Available"
            assert "accessible" in res["message"].lower()

    def test_selected_model_unavailable_http_403_permission(self):
        provider = OpenAICompatibleProvider(api_key="sk-test-key")
        err_body = {"error": {"message": "model_permission_blocked_project"}}
        http_err = _make_http_error("https://api.groq.com/openai/v1/chat/completions", 403, err_body)

        with patch("urllib.request.urlopen", side_effect=http_err):
            res = provider.test_model_availability("openai/gpt-oss-120b")
            assert res["available"] is False
            assert res["status_label"] == "🔴 Unavailable"
            assert res["status_code"] == 403
            assert "Permission Blocked" in res["message"] or "blocked" in res["message"].lower()

    def test_selected_model_unavailable_http_404_not_found(self):
        provider = OpenAICompatibleProvider(api_key="sk-test-key")
        err_body = {"error": {"message": "Model not found"}}
        http_err = _make_http_error("https://api.groq.com/openai/v1/chat/completions", 404, err_body)

        with patch("urllib.request.urlopen", side_effect=http_err):
            res = provider.test_model_availability("nonexistent-model")
            assert res["available"] is False
            assert res["status_label"] == "🔴 Unavailable"
            assert res["status_code"] == 404
            assert "Not Found" in res["message"] or "not found" in res["message"].lower()

    def test_selected_model_unavailable_http_401_auth_failure(self):
        provider = OpenAICompatibleProvider(api_key="sk-invalid")
        err_body = {"error": {"message": "Invalid API key"}}
        http_err = _make_http_error("https://api.groq.com/openai/v1/chat/completions", 401, err_body)

        with patch("urllib.request.urlopen", side_effect=http_err):
            res = provider.test_model_availability("openai/gpt-oss-120b")
            assert res["available"] is False
            assert res["status_label"] == "🔴 Unavailable"
            assert res["status_code"] == 401
            assert "Invalid API Key" in res["message"]

    def test_selected_model_unavailable_http_429_quota_or_rate_limit(self):
        provider = OpenAICompatibleProvider(api_key="sk-test-key", max_retries=0)
        err_body = {"error": {"message": "Rate limit reached"}}
        http_err = _make_http_error("https://api.groq.com/openai/v1/chat/completions", 429, err_body)

        with patch("urllib.request.urlopen", side_effect=http_err):
            res = provider.test_model_availability("openai/gpt-oss-120b")
            assert res["available"] is False
            assert res["status_label"] == "🔴 Unavailable"
            assert res["status_code"] == 429
            assert "Rate Limit" in res["message"]
