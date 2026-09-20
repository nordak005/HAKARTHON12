"""
tests/test_llm_errors.py
========================
Focused test suite for structured LLM error categories, HTTP error handling,
retry policy, and verification engine independence.
"""

import io
import json
import socket
import urllib.error
import pytest
from unittest.mock import MagicMock, patch

from constraint_guard.extractor import extract
from constraint_guard.llm.errors import LLMErrorCategory, LLMProviderError
from constraint_guard.llm.provider import OpenAICompatibleProvider
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


class TestStructuredLLMErrors:
    def test_successful_request(self):
        provider = OpenAICompatibleProvider(api_key="sk-fake-test-key")
        mock_resp_payload = {
            "choices": [{"message": {"content": "def add(a, b):\n    return a + b"}}]
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_resp_payload).encode("utf-8")
        mock_response.__enter__.return_value = mock_response

        with patch("urllib.request.urlopen", return_value=mock_response):
            res = provider.generate("Write an add function")
            assert "def add(a, b):" in res

    def test_http_401_auth_error(self):
        provider = OpenAICompatibleProvider(api_key="sk-invalid-key")
        err_body = {"error": {"message": "Invalid API key provided"}}
        http_err = _make_http_error("https://api.groq.com/openai/v1/chat/completions", 401, err_body)

        with patch("urllib.request.urlopen", side_effect=http_err):
            with pytest.raises(LLMProviderError) as exc_info:
                provider.generate("test")

            err = exc_info.value
            assert err.error_category == LLMErrorCategory.AUTH_ERROR
            assert err.status_code == 401
            assert not err.retryable
            assert "Invalid API key" in err.message

    def test_http_403_model_permission_error(self):
        provider = OpenAICompatibleProvider(api_key="sk-test-key")
        err_body = {"error": {"message": "model_permission_blocked_project"}}
        http_err = _make_http_error("https://api.groq.com/openai/v1/chat/completions", 403, err_body)

        with patch("urllib.request.urlopen", side_effect=http_err):
            with pytest.raises(LLMProviderError) as exc_info:
                provider.generate("test")

            err = exc_info.value
            assert err.error_category == LLMErrorCategory.MODEL_PERMISSION
            assert err.status_code == 403
            assert not err.retryable
            assert "blocked" in err.message.lower() or "permission" in err.message.lower()

    def test_http_404_model_not_found(self):
        provider = OpenAICompatibleProvider(api_key="sk-test-key")
        err_body = {"error": {"message": "The model `llama-3-nonexistent` does not exist"}}
        http_err = _make_http_error("https://api.groq.com/openai/v1/chat/completions", 404, err_body)

        with patch("urllib.request.urlopen", side_effect=http_err):
            with pytest.raises(LLMProviderError) as exc_info:
                provider.generate("test")

            err = exc_info.value
            assert err.error_category == LLMErrorCategory.MODEL_NOT_FOUND
            assert err.status_code == 404
            assert not err.retryable

    def test_http_408_timeout(self):
        provider = OpenAICompatibleProvider(api_key="sk-test-key", max_retries=0)
        http_err = _make_http_error("https://api.groq.com/openai/v1/chat/completions", 408, "Request Timeout")

        with patch("urllib.request.urlopen", side_effect=http_err):
            with pytest.raises(LLMProviderError) as exc_info:
                provider.generate("test")

            err = exc_info.value
            assert err.error_category == LLMErrorCategory.TIMEOUT
            assert err.status_code == 408
            assert err.retryable

    def test_http_429_rate_limit(self):
        provider = OpenAICompatibleProvider(api_key="sk-test-key", max_retries=0)
        err_body = {"error": {"message": "Rate limit reached for requests"}}
        http_err = _make_http_error("https://api.groq.com/openai/v1/chat/completions", 429, err_body)

        with patch("urllib.request.urlopen", side_effect=http_err):
            with pytest.raises(LLMProviderError) as exc_info:
                provider.generate("test")

            err = exc_info.value
            assert err.error_category == LLMErrorCategory.RATE_LIMIT
            assert err.status_code == 429
            assert err.retryable

    def test_http_429_quota_exhausted(self):
        provider = OpenAICompatibleProvider(api_key="sk-test-key")
        err_body = {"error": {"message": "You exceeded your current quota or credit balance."}}
        http_err = _make_http_error("https://api.groq.com/openai/v1/chat/completions", 429, err_body)

        with patch("urllib.request.urlopen", side_effect=http_err):
            with pytest.raises(LLMProviderError) as exc_info:
                provider.generate("test")

            err = exc_info.value
            assert err.error_category == LLMErrorCategory.QUOTA_EXCEEDED
            assert err.status_code == 429
            assert not err.retryable

    def test_http_500_provider_error(self):
        provider = OpenAICompatibleProvider(api_key="sk-test-key", max_retries=0)
        http_err = _make_http_error("https://api.groq.com/openai/v1/chat/completions", 500, "Internal Error")

        with patch("urllib.request.urlopen", side_effect=http_err):
            with pytest.raises(LLMProviderError) as exc_info:
                provider.generate("test")

            err = exc_info.value
            assert err.error_category == LLMErrorCategory.PROVIDER_ERROR
            assert err.status_code == 500
            assert err.retryable

    def test_http_502_503_504_errors(self):
        provider = OpenAICompatibleProvider(api_key="sk-test-key", max_retries=0)
        for code in (502, 503, 504):
            http_err = _make_http_error("https://api.groq.com/openai/v1/chat/completions", code, "Server Error")
            with patch("urllib.request.urlopen", side_effect=http_err):
                with pytest.raises(LLMProviderError) as exc_info:
                    provider.generate("test")

                err = exc_info.value
                assert err.error_category == LLMErrorCategory.PROVIDER_ERROR
                assert err.status_code == code
                assert err.retryable

    def test_connection_failure(self):
        provider = OpenAICompatibleProvider(api_key="sk-test-key", max_retries=0)
        url_err = urllib.error.URLError(reason="Connection refused")

        with patch("urllib.request.urlopen", side_effect=url_err):
            with pytest.raises(LLMProviderError) as exc_info:
                provider.generate("test")

            err = exc_info.value
            assert err.error_category == LLMErrorCategory.NETWORK_ERROR
            assert err.retryable

    def test_malformed_json_response(self):
        provider = OpenAICompatibleProvider(api_key="sk-test-key")
        mock_response = MagicMock()
        mock_response.read.return_value = b"<html>Cloudflare Error</html>"
        mock_response.__enter__.return_value = mock_response

        with patch("urllib.request.urlopen", return_value=mock_response):
            with pytest.raises(LLMProviderError) as exc_info:
                provider.generate("test")

            err = exc_info.value
            assert err.error_category == LLMErrorCategory.INVALID_RESPONSE
            assert not err.retryable

    def test_empty_response(self):
        provider = OpenAICompatibleProvider(api_key="sk-test-key")
        mock_response = MagicMock()
        mock_response.read.return_value = b""
        mock_response.__enter__.return_value = mock_response

        with patch("urllib.request.urlopen", return_value=mock_response):
            with pytest.raises(LLMProviderError) as exc_info:
                provider.generate("test")

            err = exc_info.value
            assert err.error_category == LLMErrorCategory.INVALID_RESPONSE
            assert not err.retryable

    def test_retryable_error_retries_and_succeeds(self):
        provider = OpenAICompatibleProvider(api_key="sk-test-key", max_retries=2)

        http_500 = _make_http_error("https://api.groq.com/openai/v1/chat/completions", 500, "Transient error")

        mock_success = MagicMock()
        mock_success.read.return_value = json.dumps(
            {"choices": [{"message": {"content": "def ok(): pass"}}]}
        ).encode("utf-8")
        mock_success.__enter__.return_value = mock_success

        call_count = 0

        def side_effect_fn(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise http_500
            return mock_success

        with patch("urllib.request.urlopen", side_effect=side_effect_fn), patch("time.sleep"):
            res = provider.generate("test")
            assert "def ok():" in res
            assert call_count == 2

    def test_retryable_error_exceeds_max_retries(self):
        provider = OpenAICompatibleProvider(api_key="sk-test-key", max_retries=2)
        http_500 = _make_http_error("https://api.groq.com/openai/v1/chat/completions", 500, "Persistent 500")

        call_count = 0

        def side_effect_fn(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise http_500

        with patch("urllib.request.urlopen", side_effect=side_effect_fn), patch("time.sleep"):
            with pytest.raises(LLMProviderError) as exc_info:
                provider.generate("test")

            assert exc_info.value.status_code == 500
            assert call_count == 3  # 1 initial + 2 retries

    def test_non_retryable_fails_immediately(self):
        provider = OpenAICompatibleProvider(api_key="sk-test-key", max_retries=2)
        http_403 = _make_http_error("https://api.groq.com/openai/v1/chat/completions", 403, "Forbidden")

        call_count = 0

        def side_effect_fn(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise http_403

        with patch("urllib.request.urlopen", side_effect=side_effect_fn), patch("time.sleep"):
            with pytest.raises(LLMProviderError) as exc_info:
                provider.generate("test")

            assert exc_info.value.status_code == 403
            assert call_count == 1  # No retries for 403!

    def test_to_dict_format(self):
        err = LLMProviderError(
            error_category=LLMErrorCategory.MODEL_PERMISSION,
            message="Model permission blocked",
            status_code=403,
            raw_error="raw body",
            retryable=False,
        )
        d = err.to_dict()
        assert d["success"] is False
        assert d["error_type"] == "MODEL_PERMISSION"
        assert d["status_code"] == 403
        assert d["message"] == "Model permission blocked"
        assert d["retryable"] is False
        assert d["raw_error"] == "raw body"

    def test_llm_failure_does_not_break_verification_pipeline(self):
        """Verify that LLM failure does not impair ConstraintGuard verification engine."""
        # Simulated LLM failure scenario: candidate code was produced previously or manually written
        code = "def find_max(lst):\n    return max(lst)"
        conv = [{"turn": 1, "text": "Do not use max()."}]

        extracted = extract(conv)
        engine = VerificationEngine()
        report = engine.verify(code, extracted.constraints)

        # Verification engine works independently without LLM!
        assert report.overall_status == "FAIL"
        assert len(report.results) == 1
        assert report.results[0].status.value == "violated"
