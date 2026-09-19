"""
constraint_guard.evaluation.runner
====================================
Runs ConstraintGuard and baseline on each ConstraintBench-Small case.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .cases import BenchmarkCase
from .baseline import BaselineVerifier, BaselineResult
from .metrics import CGRunResult, CaseComparison, compare_case


# ---------------------------------------------------------------------------
# ConstraintGuard pipeline (full)
# ---------------------------------------------------------------------------

def run_constraintguard(case: BenchmarkCase) -> CGRunResult:
    """
    Run the full ConstraintGuard pipeline on one case:
      extract → graph → resolve → verify
    Returns a CGRunResult with all observed types and statuses.
    """
    try:
        from constraint_guard.extractor import extract
        from constraint_guard.graph import VersionedConstraintGraph
        from constraint_guard.resolver import ConstraintResolver
        from constraint_guard.verifier.engine import VerificationEngine
        from constraint_guard.models import ConstraintStatus

        # Step 1: Extract
        extraction = extract(case.conversation)
        all_constraints = extraction.constraints

        # Step 2: Build graph
        vcg = VersionedConstraintGraph.build_from_constraints(all_constraints)

        # Step 3: Resolve lifecycle
        resolution = ConstraintResolver().resolve(vcg)

        # Step 4: Verify against code
        #   Engine expects constraints with their resolved statuses
        verifiable = resolution.active + resolution.conflicting + resolution.superseded
        report = VerificationEngine().verify(case.code, verifiable)

        # Collect type names
        def _types(cs):
            return [c.type.value for c in cs]

        active_types      = _types(resolution.active)
        superseded_types  = _types(resolution.superseded)
        conflicting_types = _types(resolution.conflicting)

        # Per-constraint verified statuses
        violated_types:  list[str] = []
        satisfied_types: list[str] = []
        uncertain_types: list[str] = []

        # Map constraint_id → type
        id_to_type = {c.id: c.type.value for c in all_constraints}

        for r in report.results:
            ctype = id_to_type.get(r.constraint_id, "unknown")
            if r.status == ConstraintStatus.VIOLATED:
                violated_types.append(ctype)
            elif r.status == ConstraintStatus.SATISFIED:
                satisfied_types.append(ctype)
            elif r.status == ConstraintStatus.CONFLICTING:
                pass  # already in conflicting_types
            else:
                uncertain_types.append(ctype)

        return CGRunResult(
            case_id=case.case_id,
            active_types=active_types,
            superseded_types=superseded_types,
            conflicting_types=conflicting_types,
            violated_types=violated_types,
            satisfied_types=satisfied_types,
            uncertain_types=uncertain_types,
            overall_status=report.overall_status,
        )

    except Exception as exc:
        return CGRunResult(
            case_id=case.case_id,
            overall_status="FAIL",
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# Evaluation runner
# ---------------------------------------------------------------------------

@dataclass
class EvaluationResult:
    """Full evaluation output: per-case comparisons + raw results."""
    cases:          list[BenchmarkCase]
    cg_results:     list[CGRunResult]
    bl_results:     list[BaselineResult]
    comparisons:    list[CaseComparison]


def run_evaluation(cases: Optional[list[BenchmarkCase]] = None) -> EvaluationResult:
    """
    Run all benchmark cases through both ConstraintGuard and the baseline.
    Returns an EvaluationResult ready for metric aggregation and reporting.
    """
    if cases is None:
        from .cases import load_cases
        cases = load_cases()

    baseline = BaselineVerifier()
    cg_results:  list[CGRunResult]   = []
    bl_results:  list[BaselineResult] = []
    comparisons: list[CaseComparison] = []

    for case in cases:
        cg = run_constraintguard(case)
        bl = baseline.verify(case.case_id, case.conversation, case.code)

        cg_results.append(cg)
        bl_results.append(bl)
        comparisons.append(compare_case(case, cg, bl))

    return EvaluationResult(
        cases=cases,
        cg_results=cg_results,
        bl_results=bl_results,
        comparisons=comparisons,
    )
