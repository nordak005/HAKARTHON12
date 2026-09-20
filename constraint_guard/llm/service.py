"""
constraint_guard.llm.service
============================
High-level code generation service.
"""

from typing import Any, Dict, List, Optional

from constraint_guard.llm.base import LLMProvider
from constraint_guard.llm.parser import extract_python_code
from constraint_guard.llm.prompts import (
    CODE_GENERATION_SYSTEM_PROMPT,
    build_code_generation_prompt,
)
from constraint_guard.llm.provider import get_default_provider


def generate_code(
    conversation: List[Dict[str, Any]],
    provider: Optional[LLMProvider] = None,
) -> str:
    """Generate Python code from a multi-turn conversation.

    Note: This service generates candidate code ONLY. Verification is
    performed independently by ConstraintGuard downstream.
    """
    if provider is None:
        provider = get_default_provider()

    user_prompt = build_code_generation_prompt(conversation)
    raw_response = provider.generate(
        prompt=user_prompt,
        system_prompt=CODE_GENERATION_SYSTEM_PROMPT,
    )

    clean_code = extract_python_code(raw_response)
    return clean_code
