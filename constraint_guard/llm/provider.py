"""
constraint_guard.llm.provider
=============================
OpenAI-compatible HTTP provider with structured error handling, bounded retries,
dynamic model discovery (`list_models`), model access checking (`test_model_availability`),
Fallback Mock provider, and Deterministic Mock provider.
"""

from __future__ import annotations

import http.client
import json
import os
import socket
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from constraint_guard.llm.base import LLMProvider
from constraint_guard.llm.catalog import DEFAULT_GROQ_MODEL, GROQ_MODEL_CATALOG
from constraint_guard.llm.errors import LLMErrorCategory, LLMProviderError


def _load_env_file() -> None:
    """Auto-load .env file from project root if present."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
    env_path = os.path.join(project_root, ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("\"'")
                        if k and not os.environ.get(k):
                            os.environ[k] = v
        except Exception:
            pass


_load_env_file()


def _parse_http_error(e: urllib.error.HTTPError) -> LLMProviderError:
    """Map urllib HTTPError status codes and payload details into structured LLMProviderError."""
    code = e.code
    try:
        body = e.read().decode("utf-8", errors="ignore")
    except Exception:
        body = ""

    parsed_msg = None
    if body:
        try:
            body_json = json.loads(body)
            if isinstance(body_json, dict):
                if "error" in body_json and isinstance(body_json["error"], dict):
                    parsed_msg = body_json["error"].get("message")
                elif "message" in body_json:
                    parsed_msg = str(body_json["message"])
        except Exception:
            pass

    body_lower = body.lower()

    if code == 401:
        msg = parsed_msg or "Invalid API key or authentication failure."
        return LLMProviderError(
            LLMErrorCategory.AUTH_ERROR,
            msg,
            status_code=code,
            raw_error=body,
            retryable=False,
        )
    elif code == 403:
        msg = parsed_msg or "The selected model is blocked at the project level or permission is denied."
        return LLMProviderError(
            LLMErrorCategory.MODEL_PERMISSION,
            msg,
            status_code=code,
            raw_error=body,
            retryable=False,
        )
    elif code == 404:
        msg = parsed_msg or "The requested model was not found or is unavailable."
        return LLMProviderError(
            LLMErrorCategory.MODEL_NOT_FOUND,
            msg,
            status_code=code,
            raw_error=body,
            retryable=False,
        )
    elif code == 408:
        msg = parsed_msg or "LLM request timed out."
        return LLMProviderError(
            LLMErrorCategory.TIMEOUT,
            msg,
            status_code=code,
            raw_error=body,
            retryable=True,
        )
    elif code == 429:
        if any(kw in body_lower for kw in ["quota", "credit", "balance", "insufficient", "exceeded", "payment"]):
            msg = parsed_msg or "LLM API quota or account credit exhausted."
            return LLMProviderError(
                LLMErrorCategory.QUOTA_EXCEEDED,
                msg,
                status_code=code,
                raw_error=body,
                retryable=False,
            )
        else:
            msg = parsed_msg or "LLM rate limit exceeded. Please try again shortly."
            return LLMProviderError(
                LLMErrorCategory.RATE_LIMIT,
                msg,
                status_code=code,
                raw_error=body,
                retryable=True,
            )
    elif code == 400:
        msg = parsed_msg or "Bad request sent to LLM provider."
        # Groq returns HTTP 400 when the model produces no output (e.g. empty
        # assistant turn).  The error text is:
        #   "model output must contain either output text or tool calls"
        # This is a transient model failure — mark it retryable so the
        # retry loop in generate() can attempt the call again.
        is_empty_output_error = "model output must contain" in body_lower
        return LLMProviderError(
            LLMErrorCategory.INVALID_RESPONSE if is_empty_output_error else LLMErrorCategory.PROVIDER_ERROR,
            msg,
            status_code=code,
            raw_error=body,
            retryable=is_empty_output_error,
        )
    elif code in (500, 502, 503, 504):
        msg = parsed_msg or f"LLM provider server error (HTTP {code})."
        return LLMProviderError(
            LLMErrorCategory.PROVIDER_ERROR,
            msg,
            status_code=code,
            raw_error=body,
            retryable=True,
        )
    else:
        msg = parsed_msg or f"LLM API returned HTTP {code}."
        is_server_err = code >= 500
        category = LLMErrorCategory.PROVIDER_ERROR if is_server_err else LLMErrorCategory.UNKNOWN_ERROR
        return LLMProviderError(
            category,
            msg,
            status_code=code,
            raw_error=body,
            retryable=is_server_err,
        )


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI-compatible HTTP API provider using standard urllib with structured error handling and retries."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: int = 30,
        max_retries: int = 2,
    ) -> None:
        self.base_url = (
            base_url or os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
        ).rstrip("/")
        self.api_key = api_key or os.getenv("LLM_API_KEY", "").strip()
        self.model = model or os.getenv("LLM_MODEL", DEFAULT_GROQ_MODEL)
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def list_models(self) -> List[Dict[str, Any]]:
        """List models available from provider endpoint GET /models."""
        if not self.is_configured():
            return []

        url = f"{self.base_url}/models"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ConstraintGuard/1.0",
        }
        req = urllib.request.Request(url, headers=headers, method="GET")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw_bytes = resp.read()
                if not raw_bytes:
                    return []
                resp_data = json.loads(raw_bytes.decode("utf-8"))
                if isinstance(resp_data, dict) and "data" in resp_data and isinstance(resp_data["data"], list):
                    return resp_data["data"]
                elif isinstance(resp_data, list):
                    return resp_data
                return []
        except Exception:
            return []

    def test_model_availability(self, model: Optional[str] = None) -> Dict[str, Any]:
        """Test access to selected model by running a minimal generation request."""
        target_model = model or self.model
        if not self.is_configured():
            return {
                "available": False,
                "status_label": "🔴 Unavailable",
                "message": "LLM_API_KEY is not configured.",
                "error_category": LLMErrorCategory.AUTH_ERROR.value,
                "status_code": None,
            }

        orig_model = self.model
        self.model = target_model
        try:
            self._single_attempt_generate(prompt="ping", system_prompt="Respond with pong.")
            return {
                "available": True,
                "status_label": "🟢 Available",
                "message": f"Model '{target_model}' is accessible.",
                "error_category": None,
                "status_code": 200,
            }
        except LLMProviderError as err:
            category_val = err.error_category.value
            if err.error_category == LLMErrorCategory.MODEL_PERMISSION:
                detail_msg = f"Model Permission Blocked (HTTP 403) — The selected model '{target_model}' is blocked at the project level."
            elif err.error_category == LLMErrorCategory.MODEL_NOT_FOUND:
                detail_msg = f"Model Not Found (HTTP 404) — The requested model '{target_model}' does not exist or is unavailable."
            elif err.error_category == LLMErrorCategory.AUTH_ERROR:
                detail_msg = "Invalid API Key — Authentication failed."
            elif err.error_category in (LLMErrorCategory.RATE_LIMIT, LLMErrorCategory.QUOTA_EXCEEDED):
                detail_msg = f"Rate Limit / Quota Exceeded — {err.message}"
            else:
                detail_msg = f"{category_val}: {err.message}"

            return {
                "available": False,
                "status_label": "🔴 Unavailable",
                "message": detail_msg,
                "error_category": category_val,
                "status_code": err.status_code,
            }
        except Exception as err:
            return {
                "available": False,
                "status_label": "🔴 Unavailable",
                "message": f"Unexpected error testing model access: {err}",
                "error_category": LLMErrorCategory.UNKNOWN_ERROR.value,
                "status_code": None,
            }
        finally:
            self.model = orig_model

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        if not self.is_configured():
            raise LLMProviderError(
                LLMErrorCategory.AUTH_ERROR,
                "LLM_API_KEY is not configured. Please set LLM_API_KEY in environment or .env.",
                retryable=False,
            )

        attempts = 0
        while True:
            attempts += 1
            try:
                return self._single_attempt_generate(prompt, system_prompt)
            except LLMProviderError as err:
                if not err.retryable or attempts > self.max_retries:
                    raise err
                time.sleep(0.2 * attempts)

    def _single_attempt_generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ConstraintGuard/1.0",
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw_bytes = resp.read()
                if not raw_bytes or not raw_bytes.strip():
                    raise LLMProviderError(
                        LLMErrorCategory.INVALID_RESPONSE,
                        "Empty response received from LLM provider.",
                        retryable=False,
                    )
                try:
                    resp_data = json.loads(raw_bytes.decode("utf-8"))
                except Exception as json_err:
                    raise LLMProviderError(
                        LLMErrorCategory.INVALID_RESPONSE,
                        f"Malformed JSON response received from LLM provider: {json_err}",
                        raw_error=raw_bytes.decode("utf-8", errors="ignore"),
                        retryable=False,
                    ) from json_err

                try:
                    content = resp_data["choices"][0]["message"]["content"]
                    if content is None:
                        raise KeyError("content is None")
                    # Guard against empty-string output — Groq occasionally
                    # returns HTTP 200 with an empty content field when the
                    # model produces no output (the "model output must contain
                    # either output text or tool calls" scenario).
                    if not str(content).strip():
                        raise LLMProviderError(
                            LLMErrorCategory.INVALID_RESPONSE,
                            "LLM returned an empty response (model produced no output). "
                            "This is a transient error — please retry or select a different model.",
                            raw_error=json.dumps(resp_data),
                            retryable=True,
                        )
                    return content
                except LLMProviderError:
                    raise
                except (KeyError, IndexError, TypeError) as struct_err:
                    raise LLMProviderError(
                        LLMErrorCategory.INVALID_RESPONSE,
                        "Invalid response structure from LLM provider (missing choices/message content).",
                        raw_error=json.dumps(resp_data),
                        retryable=False,
                    ) from struct_err

        except urllib.error.HTTPError as e:
            raise _parse_http_error(e) from e
        except urllib.error.URLError as e:
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                raise LLMProviderError(
                    LLMErrorCategory.TIMEOUT,
                    f"LLM API request timed out: {e.reason}",
                    retryable=True,
                ) from e
            raise LLMProviderError(
                LLMErrorCategory.NETWORK_ERROR,
                f"Network connection error: {e.reason}",
                raw_error=str(e),
                retryable=True,
            ) from e
        except (socket.timeout, TimeoutError) as e:
            raise LLMProviderError(
                LLMErrorCategory.TIMEOUT,
                f"LLM API request timed out: {e}",
                retryable=True,
            ) from e
        except (ConnectionError, http.client.RemoteDisconnected) as e:
            raise LLMProviderError(
                LLMErrorCategory.NETWORK_ERROR,
                f"Network connection failed: {e}",
                retryable=True,
            ) from e
        except LLMProviderError:
            raise
        except Exception as e:
            raise LLMProviderError(
                LLMErrorCategory.UNKNOWN_ERROR,
                f"Unexpected LLM API failure: {e}",
                raw_error=str(e),
                retryable=False,
            ) from e


class FallbackMockProvider(LLMProvider):
    """Fallback provider when no live API key is set. Prevents crashes."""

    def __init__(self, default_code: Optional[str] = None) -> None:
        self.default_code = default_code or """\
def find_max(lst):
    if not lst:
        return None
    curr = lst[0]
    for x in lst[1:]:
        if x > curr:
            curr = x
    return curr
"""

    def is_configured(self) -> bool:
        return False

    def list_models(self) -> List[Dict[str, Any]]:
        return [{"id": m} for m in GROQ_MODEL_CATALOG]

    def test_model_availability(self, model: Optional[str] = None) -> Dict[str, Any]:
        return {
            "available": True,
            "status_label": "🟢 Available",
            "message": "Fallback mock provider active.",
            "error_category": None,
            "status_code": 200,
        }

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        return f"```python\n{self.default_code}\n```"


class DeterministicMockProvider(LLMProvider):
    """Deterministic provider for offline reproducible testing and evaluation."""

    def __init__(
        self,
        response_map: Optional[Dict[str, str]] = None,
        default_response: Optional[str] = None,
    ) -> None:
        self.response_map = response_map or {}
        self.default_response = default_response or """\
def process_data(lst):
    if not lst:
        return None
    return lst[0]
"""

    def is_configured(self) -> bool:
        return True

    def list_models(self) -> List[Dict[str, Any]]:
        return [{"id": m} for m in GROQ_MODEL_CATALOG]

    def test_model_availability(self, model: Optional[str] = None) -> Dict[str, Any]:
        return {
            "available": True,
            "status_label": "🟢 Available",
            "message": "Deterministic mock provider active.",
            "error_category": None,
            "status_code": 200,
        }

    def register_response(self, keyword: str, response_code: str) -> None:
        self.response_map[keyword] = response_code

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        full_text = f"{system_prompt or ''}\n{prompt}".lower()
        for keyword, resp in self.response_map.items():
            if keyword.lower() in full_text:
                resp_clean = resp.strip()
                return f"```python\n{resp_clean}\n```" if not resp_clean.startswith("```") else resp_clean
        default_clean = self.default_response.strip()
        return f"```python\n{default_clean}\n```" if not default_clean.startswith("```") else default_clean


def get_default_provider() -> LLMProvider:
    """Return configured live provider if LLM_API_KEY is present, else FallbackMockProvider."""
    api_key = os.getenv("LLM_API_KEY", "").strip()
    if api_key:
        return OpenAICompatibleProvider()
    return FallbackMockProvider()
