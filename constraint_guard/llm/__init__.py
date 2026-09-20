"""
constraint_guard.llm
====================
LLM provider abstraction, code generation service, prompt formatting, and response parsing.
"""

from constraint_guard.llm.base import LLMProvider
from constraint_guard.llm.catalog import (
    DEFAULT_GROQ_MODEL,
    GROQ_MODEL_CATALOG,
    get_model_catalog,
)
from constraint_guard.llm.errors import LLMErrorCategory, LLMProviderError
from constraint_guard.llm.provider import (
    DeterministicMockProvider,
    FallbackMockProvider,
    OpenAICompatibleProvider,
    get_default_provider,
)
from constraint_guard.llm.parser import extract_python_code
from constraint_guard.llm.service import generate_code

__all__ = [
    "LLMProvider",
    "DEFAULT_GROQ_MODEL",
    "GROQ_MODEL_CATALOG",
    "get_model_catalog",
    "LLMErrorCategory",
    "LLMProviderError",
    "OpenAICompatibleProvider",
    "FallbackMockProvider",
    "DeterministicMockProvider",
    "get_default_provider",
    "extract_python_code",
    "generate_code",
]


