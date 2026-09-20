"""
constraint_guard.llm.catalog
=============================
Maintainable Groq model catalog for text/code-generation models.
"""

from __future__ import annotations

from typing import List

DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"

GROQ_MODEL_CATALOG: List[str] = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-safeguard-20b",
    "qwen/qwen3.8-27b",
    "llama-3.3-70b-versatile",
]


def get_model_catalog() -> List[str]:
    """Return list of candidate Groq models with default prioritized."""
    return list(GROQ_MODEL_CATALOG)
