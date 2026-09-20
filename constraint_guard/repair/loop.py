"""
constraint_guard.repair.loop
============================
Closed-loop LLM repair controller and structured RepairHistory dataclass.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from constraint_guard.extractor import extract
from constraint_guard.graph import VersionedConstraintGraph
from constraint_guard.llm.base import LLMProvider
from constraint_guard.llm.provider import get_default_provider
from constraint_guard.models import ConstraintStatus, VerificationReport
from constraint_guard.repair.repairer import repair_code
from constraint_guard.resolver import ConstraintResolver
from constraint_guard.verifier.engine import VerificationEngine


class RepairAttempt(BaseModel):
    """Structured record of a single repair iteration."""

    iteration: int
    code: str
    violated_constraints: List[str]
    verification_report: VerificationReport
    status: str  # "PASS" or "FAIL"


class RepairHistory(BaseModel):
    """Structured history of a closed-loop repair sequence."""

    initial_code: str
    initial_report: VerificationReport
    attempts: List[RepairAttempt] = Field(default_factory=list)
    final_code: str
    final_report: VerificationReport
    iterations_used: int = 0
    success: bool = False


def run_repair_loop(
    conversation: List[Dict[str, Any]],
    initial_code: str,
    max_iterations: int = 2,
    provider: Optional[LLMProvider] = None,
) -> RepairHistory:
    """Execute a controlled repair loop with MAX_REPAIR_ITERATIONS cap.

    Architecture:
    LLM = proposes candidate repaired code.
    ConstraintGuard = sole independent verifier determining PASS/FAIL.
    """
    if provider is None:
        provider = get_default_provider()

    # 1. Pipeline preparation
    extraction_res = extract(conversation)
    graph = VersionedConstraintGraph.build_from_constraints(extraction_res.constraints)
    resolver = ConstraintResolver()
    state = resolver.resolve(graph)
    all_constraints = graph.get_all_constraints()
    active_ids = {c.id for c in state.active}

    engine = VerificationEngine()
    initial_report = engine.verify(initial_code, all_constraints)

    # If initial code is already passing, no repair needed
    if initial_report.overall_status == "PASS":
        return RepairHistory(
            initial_code=initial_code,
            initial_report=initial_report,
            attempts=[],
            final_code=initial_code,
            final_report=initial_report,
            iterations_used=0,
            success=True,
        )

    current_code = initial_code
    current_report = initial_report
    attempts: List[RepairAttempt] = []
    success = False
    iterations_used = 0

    for iteration in range(1, max_iterations + 1):
        iterations_used = iteration

        # Extract currently violated constraint IDs for recording
        violated_ids = [
            res.constraint_id
            for res in current_report.results
            if res.status == ConstraintStatus.VIOLATED
        ]

        # LLM proposes repaired code based on line-numbered evidence
        repaired_candidate = repair_code(
            conversation=conversation,
            code=current_code,
            verification_report=current_report,
            active_constraints=state.active,
            provider=provider,
        )

        # Reset active constraint statuses to ACTIVE so engine re-verifies fresh code
        for c in all_constraints:
            if c.id in active_ids:
                c.status = ConstraintStatus.ACTIVE

        # ConstraintGuard independently verifies repaired candidate code
        re_report = engine.verify(repaired_candidate, all_constraints)
        attempt_status = "PASS" if re_report.overall_status == "PASS" else "FAIL"

        attempt = RepairAttempt(
            iteration=iteration,
            code=repaired_candidate,
            violated_constraints=violated_ids,
            verification_report=re_report,
            status=attempt_status,
        )
        attempts.append(attempt)

        current_code = repaired_candidate
        current_report = re_report

        if re_report.overall_status == "PASS":
            success = True
            break

    return RepairHistory(
        initial_code=initial_code,
        initial_report=initial_report,
        attempts=attempts,
        final_code=current_code,
        final_report=current_report,
        iterations_used=iterations_used,
        success=success,
    )
