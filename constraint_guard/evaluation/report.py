"""
constraint_guard.evaluation.report
====================================
Formats evaluation results as human-readable text and machine-readable JSON,
and saves them to the evaluation/ output directory.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from .metrics import AggregateMetrics, CaseComparison, aggregate_metrics
from .runner import EvaluationResult


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _pct(v: Optional[float]) -> str:
    if v is None:
        return "N/A (undefined)"
    return f"{v * 100:.1f}%"


def _fp(v: Optional[float]) -> str:
    if v is None:
        return "N/A"
    return f"{v:.3f}"


# ---------------------------------------------------------------------------
# Error analysis
# ---------------------------------------------------------------------------

def _error_analysis(
    comparisons: list[CaseComparison],
    cases,
) -> list[dict]:
    """Return a list of dicts describing cases where CG or baseline was wrong."""
    errors = []
    case_map = {c.case_id: c for c in cases}

    for comp in comparisons:
        cg_wrong = not comp.cg_overall_correct
        bl_wrong = not comp.bl_overall_correct
        state_wrong = not comp.cg_states_correct

        if cg_wrong or state_wrong:
            case = case_map[comp.case_id]
            category = _classify_error(comp, case)
            errors.append({
                "case_id":          comp.case_id,
                "description":      case.description,
                "category":         comp.category,
                "expected_overall": comp.expected_overall,
                "cg_overall":       comp.cg_overall,
                "bl_overall":       comp.bl_overall,
                "cg_state_correct": comp.cg_states_correct,
                "cg_active":        comp.cg_active_types,
                "cg_superseded":    comp.cg_superseded_types,
                "cg_conflicting":   comp.cg_conflicting_types,
                "cg_violated":      comp.cg_violated_types,
                "cg_satisfied":     comp.cg_satisfied_types,
                "expected_active":  case.expected_active_types,
                "expected_violated":case.expected_violated_types,
                "failure_category": category,
            })
    return errors


def _classify_error(comp: CaseComparison, case) -> str:
    """Heuristic: categorise the type of failure."""
    if comp.cg_overall == "PASS" and comp.expected_overall == "FAIL":
        return "False Negative — system missed a violation"
    if comp.cg_overall == "FAIL" and comp.expected_overall == "PASS":
        return "False Positive — system incorrectly flagged violation"
    if not comp.cg_states_correct:
        if case.expected_superseded_types and not comp.cg_superseded_types:
            return "State Error — supersession not detected"
        if case.expected_conflicting_types and not comp.cg_conflicting_types:
            return "State Error — conflict not detected"
        return "State Error — lifecycle states incorrect"
    return "Uncertain — no clear failure mode"


# ---------------------------------------------------------------------------
# Text report
# ---------------------------------------------------------------------------

_DIVIDER = "=" * 60
_THIN    = "-" * 60


def build_text_report(
    eval_result: EvaluationResult,
    metrics: AggregateMetrics,
) -> str:
    comparisons = eval_result.comparisons
    cases = eval_result.cases
    errors = _error_analysis(comparisons, cases)

    lines = [
        _DIVIDER,
        "CONSTRAINTGUARD EVALUATION",
        _DIVIDER,
        "",
        "Dataset : ConstraintBench-Small (custom multi-turn benchmark)",
        "NOTE    : This is NOT MBPP, HumanEval, or any official benchmark.",
        f"Cases   : {metrics.n_cases}",
        f"Expected constraint instances: {metrics.n_constraints}",
        "",
        _THIN,
        "METRICS COMPARISON",
        _THIN,
        "",
        f"{'Metric':<40} {'ConstraintGuard':>18} {'Baseline':>12}",
        "-" * 72,
        f"{'Constraint identification acc.':<40} {_pct(metrics.cg_id_accuracy):>18} {_pct(metrics.bl_id_accuracy):>12}",
        f"{'Constraint state accuracy':<40} {_pct(metrics.cg_state_accuracy):>18} {_pct(metrics.bl_state_accuracy):>12}",
        f"{'Violation detection precision':<40} {_pct(metrics.cg_precision):>18} {_pct(metrics.bl_precision):>12}",
        f"{'Violation detection recall':<40} {_pct(metrics.cg_recall):>18} {_pct(metrics.bl_recall):>12}",
        f"{'End-to-end verification accuracy':<40} {_pct(metrics.cg_e2e_accuracy):>18} {_pct(metrics.bl_e2e_accuracy):>12}",
        "",
        _THIN,
        "CONFUSION MATRIX (FAIL = positive class)",
        _THIN,
        "",
        f"{'':>30} {'ConstraintGuard':>16} {'Baseline':>12}",
        f"{'True Positives (TP)':<30} {metrics.cg_tp:>16} {metrics.bl_tp:>12}",
        f"{'False Positives (FP)':<30} {metrics.cg_fp:>16} {metrics.bl_fp:>12}",
        f"{'False Negatives (FN)':<30} {metrics.cg_fn:>16} {metrics.bl_fn:>12}",
        f"{'True Negatives (TN)':<30} {metrics.cg_tn:>16} {metrics.bl_tn:>12}",
        "",
        _THIN,
        "VERIFICATION SUMMARY (ConstraintGuard)",
        _THIN,
        "",
        f"  Violated constraints  : {metrics.total_violated}",
        f"  Satisfied constraints : {metrics.total_satisfied}",
        f"  Uncertain constraints : {metrics.total_uncertain}",
        f"  Conflicting pairs     : {metrics.total_conflicts}",
        "",
        _THIN,
        "PER-CASE RESULTS",
        _THIN,
        "",
        f"{'ID':<5} {'Cat':<18} {'Expected':<10} {'CG':<8} {'BL':<8} {'CG✓':<5} {'BL✓':<5}",
        "-" * 62,
    ]

    for comp in comparisons:
        cg_ok = "✓" if comp.cg_overall_correct else "✗"
        bl_ok = "✓" if comp.bl_overall_correct else "✗"
        lines.append(
            f"{comp.case_id:<5} {comp.category:<18} {comp.expected_overall:<10} "
            f"{comp.cg_overall:<8} {comp.bl_overall:<8} {cg_ok:<5} {bl_ok:<5}"
        )

    lines += [
        "",
        _THIN,
        f"ERROR ANALYSIS ({len(errors)} case(s) with CG errors)",
        _THIN,
        "",
    ]

    if not errors:
        lines.append("  No errors. All cases passed.")
    else:
        for err in errors:
            lines += [
                f"  Case {err['case_id']} — {err['description']}",
                f"    Category        : {err['category']}",
                f"    Expected overall: {err['expected_overall']}",
                f"    CG overall      : {err['cg_overall']}",
                f"    BL overall      : {err['bl_overall']}",
                f"    CG state ok     : {err['cg_state_correct']}",
                f"    CG active types : {err['cg_active']}",
                f"    Expected active : {err['expected_active']}",
                f"    CG violated     : {err['cg_violated']}",
                f"    Expected violated: {err['expected_violated']}",
                f"    Failure category: {err['failure_category']}",
                "",
            ]

    lines += [
        _THIN,
        "KNOWN LIMITATIONS",
        _THIN,
        "",
        "  1. COMPLEXITY constraints always produce UNCERTAIN (correct by design;",
        "     static analysis cannot prove time/space complexity).",
        "  2. Behavioral sandbox calls func([]) only; non-list signatures → UNCERTAIN.",
        "  3. Identification is type-based (not text-exact); edge cases may slip through.",
        "  4. This benchmark is NOT MBPP, HumanEval, or any standardized dataset.",
        "     Results should be interpreted in the context of ConstraintBench-Small only.",
        "",
        _DIVIDER,
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------

def build_json_output(
    eval_result: EvaluationResult,
    metrics: AggregateMetrics,
) -> dict:
    def _opt(v):
        return v  # None serializes to null in JSON

    comparisons = eval_result.comparisons
    cases = eval_result.cases
    errors = _error_analysis(comparisons, cases)

    return {
        "dataset": "ConstraintBench-Small",
        "disclaimer": "NOT MBPP, HumanEval, or any official benchmark.",
        "n_cases": metrics.n_cases,
        "n_constraint_instances": metrics.n_constraints,
        "constraintguard": {
            "identification_accuracy": metrics.cg_id_accuracy,
            "state_accuracy":          metrics.cg_state_accuracy,
            "violation_precision":     _opt(metrics.cg_precision),
            "violation_recall":        _opt(metrics.cg_recall),
            "e2e_accuracy":            metrics.cg_e2e_accuracy,
            "tp": metrics.cg_tp, "fp": metrics.cg_fp,
            "fn": metrics.cg_fn, "tn": metrics.cg_tn,
            "total_violated":          metrics.total_violated,
            "total_satisfied":         metrics.total_satisfied,
            "total_uncertain":         metrics.total_uncertain,
            "total_conflicts":         metrics.total_conflicts,
        },
        "baseline": {
            "identification_accuracy": metrics.bl_id_accuracy,
            "state_accuracy":          metrics.bl_state_accuracy,
            "violation_precision":     _opt(metrics.bl_precision),
            "violation_recall":        _opt(metrics.bl_recall),
            "e2e_accuracy":            metrics.bl_e2e_accuracy,
            "tp": metrics.bl_tp, "fp": metrics.bl_fp,
            "fn": metrics.bl_fn, "tn": metrics.bl_tn,
        },
        "per_case": [
            {
                "case_id":              comp.case_id,
                "category":             comp.category,
                "expected_overall":     comp.expected_overall,
                "cg_overall":           comp.cg_overall,
                "bl_overall":           comp.bl_overall,
                "cg_overall_correct":   comp.cg_overall_correct,
                "bl_overall_correct":   comp.bl_overall_correct,
                "cg_states_correct":    comp.cg_states_correct,
                "cg_types_found":       comp.cg_types_found,
                "cg_active_types":      comp.cg_active_types,
                "cg_superseded_types":  comp.cg_superseded_types,
                "cg_conflicting_types": comp.cg_conflicting_types,
                "cg_violated_types":    comp.cg_violated_types,
                "cg_satisfied_types":   comp.cg_satisfied_types,
                "bl_active_types":      comp.bl_active_types,
                "bl_violated_types":    comp.bl_violated_types,
            }
            for comp in comparisons
        ],
        "error_analysis": errors,
    }


# ---------------------------------------------------------------------------
# Save + print
# ---------------------------------------------------------------------------

def save_and_print(
    eval_result: EvaluationResult,
    output_dir: str = "evaluation",
) -> tuple[str, dict]:
    """
    Compute metrics, generate text + JSON reports, save files, and print to stdout.

    Returns (text_report, json_data).
    """
    from .metrics import aggregate_metrics
    metrics = aggregate_metrics(eval_result.cases, eval_result.comparisons, eval_result.cg_results)

    text = build_text_report(eval_result, metrics)
    data = build_json_output(eval_result, metrics)

    # Ensure output directory exists
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    (out / "results.md").write_text(text, encoding="utf-8")
    (out / "results.json").write_text(
        json.dumps(data, indent=2, default=str), encoding="utf-8"
    )

    import sys
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(text.encode("utf-8"))
        print()

    return text, data
