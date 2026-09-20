"""
evaluation/repair_metrics.py
============================
Metric definitions and calculator for ConstraintGuard repair performance.

Metrics:
1. Initial Violation Rate (% cases failing initial verification)
2. Repair Success Rate (% initially violated cases that become VERIFIED after repair)
3. Residual Violation Rate (% initially violated cases that remain violated)
4. Average Repair Iterations (mean repair iterations used)
5. Constraint Preservation Rate (% previously satisfied constraints preserved post-repair)
"""

from dataclasses import dataclass
from typing import List
from constraint_guard.repair.loop import RepairHistory


@dataclass
class RepairMetrics:
    total_cases: int
    initial_violations: int
    initial_violation_rate: float
    repaired_successes: int
    repair_success_rate: float
    residual_violations: int
    residual_violation_rate: float
    average_iterations: float
    constraint_preservation_rate: float


def compute_repair_metrics(histories: List[RepairHistory]) -> RepairMetrics:
    """Compute empirical repair performance metrics from a list of RepairHistory results."""
    total = len(histories)
    if total == 0:
        return RepairMetrics(
            total_cases=0,
            initial_violations=0,
            initial_violation_rate=0.0,
            repaired_successes=0,
            repair_success_rate=0.0,
            residual_violations=0,
            residual_violation_rate=0.0,
            average_iterations=0.0,
            constraint_preservation_rate=100.0,
        )

    initial_violations = sum(
        1 for h in histories if h.initial_report.overall_status != "PASS"
    )

    repaired_successes = sum(
        1 for h in histories if h.initial_report.overall_status != "PASS" and h.success
    )

    residual_violations = initial_violations - repaired_successes

    total_iters = sum(h.iterations_used for h in histories)
    avg_iters = total_iters / total if total > 0 else 0.0

    init_viol_rate = (initial_violations / total) * 100.0 if total > 0 else 0.0
    repair_succ_rate = (
        (repaired_successes / initial_violations) * 100.0
        if initial_violations > 0
        else 100.0
    )
    residual_viol_rate = (
        (residual_violations / initial_violations) * 100.0
        if initial_violations > 0
        else 0.0
    )

    # Calculate Constraint Preservation Rate:
    # Look at constraints that were SATISFIED initially, check if they remain SATISFIED in final_report
    total_preserved = 0
    total_initial_satisfied = 0

    for h in histories:
        init_satisfied_ids = {
            r.constraint_id
            for r in h.initial_report.results
            if r.status.value == "SATISFIED"
        }
        if not init_satisfied_ids:
            continue
        total_initial_satisfied += len(init_satisfied_ids)

        final_satisfied_ids = {
            r.constraint_id
            for r in h.final_report.results
            if r.status.value == "SATISFIED"
        }
        preserved_ids = init_satisfied_ids.intersection(final_satisfied_ids)
        total_preserved += len(preserved_ids)

    preservation_rate = (
        (total_preserved / total_initial_satisfied) * 100.0
        if total_initial_satisfied > 0
        else 100.0
    )

    return RepairMetrics(
        total_cases=total,
        initial_violations=initial_violations,
        initial_violation_rate=init_viol_rate,
        repaired_successes=repaired_successes,
        repair_success_rate=repair_succ_rate,
        residual_violations=residual_violations,
        residual_violation_rate=residual_viol_rate,
        average_iterations=avg_iters,
        constraint_preservation_rate=preservation_rate,
    )
