"""
constraint_guard.repair.repairer
================================
LLM repair engine for constraint-violated Python code.
"""

from typing import Any, Dict, List, Optional

from constraint_guard.llm.base import LLMProvider
from constraint_guard.llm.parser import extract_python_code
from constraint_guard.llm.prompts import (
    REPAIR_SYSTEM_PROMPT,
    build_repair_prompt,
)
from constraint_guard.llm.provider import get_default_provider
from constraint_guard.models import ConstraintStatus, VerificationReport


def repair_code(
    conversation: List[Dict[str, Any]],
    code: str,
    verification_report: VerificationReport,
    active_constraints: Optional[List[Any]] = None,
    provider: Optional[LLMProvider] = None,
) -> str:
    """Propose repaired Python code for code that violated active constraints.

    ConstraintGuard remains the sole independent verification authority.
    This function generates candidate code fixes given exact line-numbered evidence.
    """
    if provider is None:
        provider = get_default_provider()

    violated_results = [
        res for res in verification_report.results if res.status == ConstraintStatus.VIOLATED
    ]

    if not violated_results:
        # Code is already verified / no violations
        return code

    if active_constraints is None:
        active_constraints = []

    prompt = build_repair_prompt(
        conversation=conversation,
        code=code,
        active_constraints=active_constraints,
        violated_results=violated_results,
    )

    raw_response = provider.generate(
        prompt=prompt,
        system_prompt=REPAIR_SYSTEM_PROMPT,
    )

    repaired_code = extract_python_code(raw_response)
    return repaired_code
