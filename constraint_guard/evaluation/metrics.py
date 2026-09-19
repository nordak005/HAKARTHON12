"""
constraint_guard.evaluation.metrics
=====================================
Metric computation for the ConstraintBench-Small evaluation.

Metrics computed:
  1. Constraint Identification Accuracy
     — were expected constraint types found anywhere in the output?
  2. Constraint State Accuracy
     — did the system produce the correct lifecycle state (active/superseded/conflicting)?
  3. Violation Detection Precision   = TP / (TP + FP)
  4. Violation Detection Recall      = TP / (TP + FN)
  5. End-to-End Verification Accuracy = % correct overall PASS/FAIL

Zero-denominator convention:
  Precision with no positive predictions  → None  (undefined, not 0 or 1)
  Recall    with no actual positives      → None  (undefined)
  These are always reported explicitly, never silently defaulted.

All metrics are computed from REAL execution output, not hardcoded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Per-case result containers
# ---------------------------------------------------------------------------

@dataclass
class CGRunResult:
    """
    Output produced by running ConstraintGuard on one benchmark case.
    Type names are lowercase strings matching ConstraintType.value.
    """
    case_id:             str
    active_types:        list[str]   = field(default_factory=list)
    superseded_types:    list[str]   = field(default_factory=list)
    conflicting_types:   list[str]   = field(default_factory=list)
    violated_types:      list[str]   = field(default_factory=list)
    satisfied_types:     list[str]   = field(default_factory=list)
    uncertain_types:     list[str]   = field(default_factory=list)
    overall_status:      str         = "PASS"
    error:               Optional[str] = None   # if CG threw an exception


@dataclass
class CaseComparison:
    """Comparison of CG and baseline against ground truth for one case."""
    case_id:               str
    category:              str
    expected_overall:      str

    # Identification accuracy per case (bool)
    cg_types_found:        bool  = False
    bl_types_found:        bool  = False

    # State accuracy per case (bool)
    cg_states_correct:     bool  = False
    bl_states_correct:     bool  = False

    # Per-case violation labels (for precision/recall)
    actual_is_violation:   bool  = False  # ground truth: FAIL case?
    cg_predicted_violation:bool  = False  # CG says FAIL?
    bl_predicted_violation:bool  = False  # baseline says FAIL?

    # Overall PASS/FAIL match
    cg_overall_correct:    bool  = False
    bl_overall_correct:    bool  = False

    # Details for error analysis
    cg_active_types:       list[str] = field(default_factory=list)
    cg_superseded_types:   list[str] = field(default_factory=list)
    cg_conflicting_types:  list[str] = field(default_factory=list)
    cg_violated_types:     list[str] = field(default_factory=list)
    cg_satisfied_types:    list[str] = field(default_factory=list)
    bl_active_types:       list[str] = field(default_factory=list)
    bl_violated_types:     list[str] = field(default_factory=list)

    cg_overall:            str = "PASS"
    bl_overall:            str = "PASS"


@dataclass
class AggregateMetrics:
    """Final aggregated metrics across all benchmark cases."""
    n_cases:         int     = 0
    n_constraints:   int     = 0   # total expected constraint instances across all cases

    # Constraint identification (% of cases where all expected types were found)
    cg_id_accuracy:  float   = 0.0
    bl_id_accuracy:  float   = 0.0

    # Lifecycle state accuracy (% of cases where states are correct)
    cg_state_accuracy: float = 0.0
    bl_state_accuracy: float = 0.0

    # Violation detection (case-level binary)
    cg_tp:  int = 0;  cg_fp: int = 0;  cg_fn: int = 0;  cg_tn: int = 0
    bl_tp:  int = 0;  bl_fp: int = 0;  bl_fn: int = 0;  bl_tn: int = 0

    cg_precision:    Optional[float] = None
    cg_recall:       Optional[float] = None
    bl_precision:    Optional[float] = None
    bl_recall:       Optional[float] = None

    # End-to-end accuracy
    cg_e2e_accuracy: float = 0.0
    bl_e2e_accuracy: float = 0.0

    # Counts across all cases
    total_violated:  int = 0
    total_satisfied: int = 0
    total_uncertain: int = 0
    total_conflicts: int = 0


# ---------------------------------------------------------------------------
# Comparison logic
# ---------------------------------------------------------------------------

def _types_found(expected: list[str], actual: list[str]) -> bool:
    """Return True iff every expected type appears at least once in actual."""
    if not expected:
        return True  # no expectation → vacuously correct
    return all(t in actual for t in expected)


def _all_types_present(
    expected: list[str],
    actual_all: list[str],
) -> bool:
    return _types_found(expected, actual_all)


def compare_case(
    case,  # BenchmarkCase
    cg: CGRunResult,
    bl,    # BaselineResult
) -> CaseComparison:
    """Build a CaseComparison from ground truth + system outputs."""
    from .cases import BenchmarkCase
    assert isinstance(case, BenchmarkCase)

    # All types expected in any state across CG output
    cg_all_types = cg.active_types + cg.superseded_types + cg.conflicting_types

    # Constraint identification: were all expected_active_types found anywhere?
    expected_find = case.expected_active_types + case.expected_superseded_types + \
                    case.expected_conflicting_types
    cg_found = _all_types_present(expected_find, cg_all_types) if expected_find else True

    bl_all = bl.active_types
    bl_found = _all_types_present(expected_find, bl_all) if expected_find else True

    # Lifecycle state accuracy
    # CG correct if: active types contain expected_active_types AND
    #                superseded types contain expected_superseded_types AND
    #                conflicting types contain expected_conflicting_types
    cg_active_ok = _types_found(case.expected_active_types, cg.active_types)
    cg_sup_ok    = _types_found(case.expected_superseded_types, cg.superseded_types)
    cg_conf_ok   = _types_found(case.expected_conflicting_types, cg.conflicting_types)
    cg_states_ok = cg_active_ok and cg_sup_ok and cg_conf_ok

    # Baseline: no supersession/conflict tracking → only check active types found
    bl_active_ok  = _types_found(
        case.expected_active_types + case.expected_superseded_types,
        bl.active_types,
    )
    # Baseline never tracks superseded/conflicting explicitly
    bl_states_ok = bl_active_ok

    # Violation prediction (case-level binary)
    actual_is_violation  = (case.expected_overall == "FAIL")
    cg_pred_violation    = (cg.overall_status == "FAIL")
    bl_pred_violation    = (bl.overall_status == "FAIL")

    return CaseComparison(
        case_id=case.case_id,
        category=case.category,
        expected_overall=case.expected_overall,
        cg_types_found=cg_found,
        bl_types_found=bl_found,
        cg_states_correct=cg_states_ok,
        bl_states_correct=bl_states_ok,
        actual_is_violation=actual_is_violation,
        cg_predicted_violation=cg_pred_violation,
        bl_predicted_violation=bl_pred_violation,
        cg_overall_correct=(cg.overall_status == case.expected_overall),
        bl_overall_correct=(bl.overall_status == case.expected_overall),
        cg_active_types=cg.active_types,
        cg_superseded_types=cg.superseded_types,
        cg_conflicting_types=cg.conflicting_types,
        cg_violated_types=cg.violated_types,
        cg_satisfied_types=cg.satisfied_types,
        bl_active_types=bl.active_types,
        bl_violated_types=bl.violated_types,
        cg_overall=cg.overall_status,
        bl_overall=bl.overall_status,
    )


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _safe_precision(tp: int, fp: int) -> Optional[float]:
    denom = tp + fp
    return tp / denom if denom > 0 else None


def _safe_recall(tp: int, fn: int) -> Optional[float]:
    denom = tp + fn
    return tp / denom if denom > 0 else None


def aggregate_metrics(
    cases,           # list[BenchmarkCase]
    comparisons:     list[CaseComparison],
    cg_results:      list[CGRunResult],
) -> AggregateMetrics:
    """Compute all aggregated metrics from per-case comparisons."""
    m = AggregateMetrics()
    m.n_cases = len(comparisons)

    # Count expected constraints across all cases
    for case in cases:
        m.n_constraints += len(case.expected_active_types)
        m.n_constraints += len(case.expected_superseded_types)
        m.n_constraints += len(case.expected_conflicting_types)

    # Per-case aggregation
    cg_id_correct    = sum(1 for c in comparisons if c.cg_types_found)
    bl_id_correct    = sum(1 for c in comparisons if c.bl_types_found)
    cg_state_correct = sum(1 for c in comparisons if c.cg_states_correct)
    bl_state_correct = sum(1 for c in comparisons if c.bl_states_correct)
    cg_e2e_correct   = sum(1 for c in comparisons if c.cg_overall_correct)
    bl_e2e_correct   = sum(1 for c in comparisons if c.bl_overall_correct)

    n = m.n_cases
    m.cg_id_accuracy    = cg_id_correct    / n if n else 0.0
    m.bl_id_accuracy    = bl_id_correct    / n if n else 0.0
    m.cg_state_accuracy = cg_state_correct / n if n else 0.0
    m.bl_state_accuracy = bl_state_correct / n if n else 0.0
    m.cg_e2e_accuracy   = cg_e2e_correct   / n if n else 0.0
    m.bl_e2e_accuracy   = bl_e2e_correct   / n if n else 0.0

    # Confusion matrix counts (case-level binary: FAIL=positive)
    for c in comparisons:
        pos = c.actual_is_violation
        cg_p = c.cg_predicted_violation
        bl_p = c.bl_predicted_violation

        if pos and cg_p:  m.cg_tp += 1
        elif pos and not cg_p: m.cg_fn += 1
        elif not pos and cg_p: m.cg_fp += 1
        else: m.cg_tn += 1

        if pos and bl_p:  m.bl_tp += 1
        elif pos and not bl_p: m.bl_fn += 1
        elif not pos and bl_p: m.bl_fp += 1
        else: m.bl_tn += 1

    m.cg_precision = _safe_precision(m.cg_tp, m.cg_fp)
    m.cg_recall    = _safe_recall(m.cg_tp, m.cg_fn)
    m.bl_precision = _safe_precision(m.bl_tp, m.bl_fp)
    m.bl_recall    = _safe_recall(m.bl_tp, m.bl_fn)

    # Count totals from CG results
    for r in cg_results:
        m.total_violated  += len(r.violated_types)
        m.total_satisfied += len(r.satisfied_types)
        m.total_uncertain += len(r.uncertain_types)
        m.total_conflicts += len(r.conflicting_types)

    return m
