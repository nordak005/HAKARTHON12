"""
constraint_guard.llm.errors
============================
Structured LLM provider error handling and categories.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional


class LLMErrorCategory(str, Enum):
    """Structured categories for LLM provider errors."""

    AUTH_ERROR = "AUTH_ERROR"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    MODEL_PERMISSION = "MODEL_PERMISSION"
    RATE_LIMIT = "RATE_LIMIT"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    TIMEOUT = "TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


class LLMProviderError(RuntimeError):
    """Structured exception raised when an LLM provider call fails."""

    def __init__(
        self,
        error_category: LLMErrorCategory,
        message: str,
        status_code: Optional[int] = None,
        raw_error: Optional[str] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.error_category = error_category
        self.message = message
        self.status_code = status_code
        self.raw_error = raw_error
        self.retryable = retryable

    def to_dict(self) -> Dict[str, Any]:
        """Return structured dictionary representation of the error."""
        return {
            "success": False,
            "error_type": self.error_category.value,
            "status_code": self.status_code,
            "message": self.message,
            "retryable": self.retryable,
            "raw_error": self.raw_error,
        }

    def __str__(self) -> str:
        code_str = f" (HTTP {self.status_code})" if self.status_code else ""
        return f"[{self.error_category.value}]{code_str}: {self.message}"
