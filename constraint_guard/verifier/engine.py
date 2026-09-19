"""
constraint_guard.verifier.engine
==================================
Central VerificationEngine.

Routes each ACTIVE constraint through the applicable verification lanes
(lexical, structural, behavioral), aggregates the evidence conservatively,
and produces a VerificationReport.

Routing table
-------------
NO_BUILTIN     → lexical (primary) + structural (secondary)
ALGORITHM      → structural (primary)
NAMING         → structural
SIGNATURE      → structural
STRUCTURE      → structural
ERROR_HANDLING → behavioral (primary) + structural (secondary)
COMPLEXITY     → structural (always uncertain)
GENERAL        → uncertain (no applicable verifier)

Aggregation rules (conservative)
---------------------------------
1. Any confident VIOLATED evidence (confidence >= threshold, status="violated")
   → final = VIOLATED regardless of other lanes.
2. All applicable lanes return SATISFIED (passed=True)
   → final = SATISFIED.
3. All applicable lanes are uncertain
   → final = ACTIVE (i.e., cannot determine; no verdict).
4. Mix of satisfied + uncertain (no violation)
   → final = SATISFIED with reduced confidence.
5. Conflicting constraints → reported as CONFLICTING; no code verdict attempted.
6. Superseded constraints → skipped entirely.
"""

from __future__ import annotations

from typing import Optional

from ..models import (
    Constraint,
    ConstraintStatus,
    ConstraintType,
    Evidence,
    VerificationReport,
    VerificationResult,
)
from . import lexical, structural, behavioral


# ---------------------------------------------------------------------------
# Routing configuration
# ---------------------------------------------------------------------------

# Maps ConstraintType → ordered list of verifier modules to apply
_ROUTING: dict[ConstraintType, list] = {
    ConstraintType.NO_BUILTIN:     [lexical, structural],
    ConstraintType.ALGORITHM:      [structural],
    ConstraintType.NAMING:         [structural],
    ConstraintType.SIGNATURE:      [structural],
    ConstraintType.STRUCTURE:      [structural],
    ConstraintType.ERROR_HANDLING: [behavioral, structural],
    ConstraintType.COMPLEXITY:     [structural],
    ConstraintType.GENERAL:        [],           # no applicable lane
}

# Minimum confidence required for a violation to be treated as definitive
_VIOLATION_CONFIDENCE_THRESHOLD = 0.70


# ---------------------------------------------------------------------------
# Evidence status helpers
# ---------------------------------------------------------------------------

def _is_violated(ev: Evidence) -> bool:
    return (
        not ev.passed
        and ev.metadata.get("status") == "violated"
        and ev.confidence >= _VIOLATION_CONFIDENCE_THRESHOLD
    )


def _is_satisfied(ev: Evidence) -> bool:
    return ev.passed and ev.metadata.get("status") == "satisfied"


def _is_uncertain(ev: Evidence) -> bool:
    return ev.metadata.get("status") == "uncertain"


# ---------------------------------------------------------------------------
# Per-constraint aggregation
# ---------------------------------------------------------------------------

def _aggregate(
    constraint: Constraint,
    evidences: list[Evidence],
) -> VerificationResult:
    """
    Combine *evidences* from multiple verifier lanes into a single
    VerificationResult for *constraint*.

    Returns a result with status:
      VIOLATED   — at least one confident violation found
      SATISFIED  — all applicable evidences pass (no violation, some satisfied)
      ACTIVE     — only uncertain evidences (no verdict possible)
    """
    violations = [e for e in evidences if _is_violated(e)]
    satisfactions = [e for e in evidences if _is_satisfied(e)]
    uncertain_only = all(_is_uncertain(e) for e in evidences)

    if violations:
        # Highest-confidence violation wins
        top_v = max(violations, key=lambda e: e.confidence)
        return VerificationResult(
            constraint_id=constraint.id,
            status=ConstraintStatus.VIOLATED,
            evidences=evidences,
            final_pass=False,
            confidence=top_v.confidence,
        )

    if satisfactions and not violations:
        avg_conf = sum(e.confidence for e in satisfactions) / len(satisfactions)
        # Reduce confidence if some lanes were uncertain
        if uncertain_only is False and len(satisfactions) < len(evidences):
            avg_conf *= 0.90  # partial evidence penalty
        return VerificationResult(
            constraint_id=constraint.id,
            status=ConstraintStatus.SATISFIED,
            evidences=evidences,
            final_pass=True,
            confidence=min(avg_conf, 1.0),
        )

    # All lanes returned uncertain or no lanes were applicable
    return VerificationResult(
        constraint_id=constraint.id,
        status=ConstraintStatus.ACTIVE,  # ACTIVE = "uncertain, no verdict yet"
        evidences=evidences,
        final_pass=False,
        confidence=0.0,
    )


def _conflicting_result(constraint: Constraint) -> VerificationResult:
    """
    Produce a VerificationResult for a CONFLICTING constraint.
    No code verification is attempted — the ambiguity is surfaced explicitly.
    """
    ev = Evidence(
        constraint_id=constraint.id,
        verifier="engine",
        passed=False,
        confidence=1.0,
        message=(
            "Constraint is CONFLICTING with another active constraint. "
            "No code verification attempted until conflict is resolved."
        ),
        metadata={"status": "conflicting"},
    )
    return VerificationResult(
        constraint_id=constraint.id,
        status=ConstraintStatus.CONFLICTING,
        evidences=[ev],
        final_pass=False,
        confidence=1.0,
    )


# ---------------------------------------------------------------------------
# VerificationEngine
# ---------------------------------------------------------------------------

class VerificationEngine:
    """
    Central engine that verifies generated Python code against a list of
    Constraint objects produced by the resolver.

    Usage
    -----
        engine = VerificationEngine()
        report = engine.verify(code=generated_python, constraints=active_constraints)
    """

    def verify(
        self,
        code: str,
        constraints: list[Constraint],
    ) -> VerificationReport:
        """
        Verify *code* against *constraints*.

        Parameters
        ----------
        code        : The generated Python source code to be verified.
        constraints : All constraints, regardless of status.  The engine
                      internally filters by status (skips SUPERSEDED,
                      handles CONFLICTING, verifies ACTIVE).

        Returns
        -------
        A VerificationReport with per-constraint results and summary counts.
        """
        results: list[VerificationResult] = []

        for constraint in constraints:
            status = constraint.status

            # Skip superseded constraints entirely
            if status == ConstraintStatus.SUPERSEDED:
                continue

            # Conflicting constraints get a special result (no code check)
            if status == ConstraintStatus.CONFLICTING:
                results.append(_conflicting_result(constraint))
                continue

            # ACTIVE constraints → route through verifier lanes
            if status == ConstraintStatus.ACTIVE:
                result = self._verify_constraint(constraint, code)
                results.append(result)
                continue

            # Already SATISFIED / VIOLATED from a previous pass (idempotent)
            if status in (ConstraintStatus.SATISFIED, ConstraintStatus.VIOLATED):
                results.append(VerificationResult(
                    constraint_id=constraint.id,
                    status=status,
                    evidences=[],
                    final_pass=(status == ConstraintStatus.SATISFIED),
                    confidence=1.0,
                ))

        report = VerificationReport.from_results(constraints, results)

        # Override: unresolved conflicts also make the overall result FAIL.
        # (from_results only checks VIOLATED for overall_status)
        has_conflict = any(r.status == ConstraintStatus.CONFLICTING for r in results)
        if has_conflict and report.overall_status != "FAIL":
            report.overall_status = "FAIL"

        return report

    def verify_single(
        self,
        code: str,
        constraint: Constraint,
    ) -> VerificationResult:
        """Convenience method: verify a single constraint and return its result."""
        return self._verify_constraint(constraint, code)

    # ------------------------------------------------------------------ private

    def _verify_constraint(
        self,
        constraint: Constraint,
        code: str,
    ) -> VerificationResult:
        """Run all applicable verifier lanes for *constraint* and aggregate."""
        lanes = _ROUTING.get(constraint.type, [])

        if not lanes:
            ev = Evidence(
                constraint_id=constraint.id,
                verifier="engine",
                passed=False,
                confidence=0.0,
                message=(
                    f"No verification lane is defined for constraint type "
                    f"'{constraint.type.value}'. Cannot verify."
                ),
                metadata={"status": "uncertain"},
            )
            return _aggregate(constraint, [ev])

        evidences: list[Evidence] = []
        for lane_module in lanes:
            ev = lane_module.verify(constraint, code)
            evidences.append(ev)

            # Short-circuit: if any lane produces a confident violation, stop early
            if _is_violated(ev):
                break

        return _aggregate(constraint, evidences)
