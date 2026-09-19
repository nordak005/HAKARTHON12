"""
tests/test_evaluation.py
==========================
Tests for the constraint_guard.evaluation package.

Tests cover:
  - Benchmark case validity
  - Metrics calculations
  - Precision/recall edge cases (zero denominators)
  - Baseline execution
  - ConstraintGuard execution (single case)
  - Comparison generation
  - Report serialization
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from constraint_guard.evaluation.cases import (
    load_cases, get_case, BenchmarkCase, CONSTRAINT_BENCH_SMALL,
)
from constraint_guard.evaluation.baseline import BaselineVerifier, BaselineResult
from constraint_guard.evaluation.metrics import (
    CGRunResult, CaseComparison, AggregateMetrics,
    compare_case, aggregate_metrics,
    _safe_precision, _safe_recall,
)
from constraint_guard.evaluation.runner import (
    run_constraintguard, run_evaluation, EvaluationResult,
)
from constraint_guard.evaluation.report import (
    build_text_report, build_json_output,
)


# ---------------------------------------------------------------------------
# Benchmark dataset validity
# ---------------------------------------------------------------------------

class TestBenchmarkCases:
    def test_cases_loaded(self):
        cases = load_cases()
        assert len(cases) >= 15

    def test_all_cases_have_ids(self):
        for case in load_cases():
            assert case.case_id, f"Missing case_id"

    def test_all_cases_have_conversation(self):
        for case in load_cases():
            assert len(case.conversation) >= 1, f"Case {case.case_id} has no conversation"

    def test_all_cases_have_code(self):
        for case in load_cases():
            assert case.code.strip(), f"Case {case.case_id} has no code"

    def test_all_cases_have_expected_overall(self):
        for case in load_cases():
            assert case.expected_overall in ("PASS", "FAIL"), \
                f"Case {case.case_id}: unexpected overall value '{case.expected_overall}'"

    def test_no_duplicate_case_ids(self):
        ids = [c.case_id for c in load_cases()]
        assert len(ids) == len(set(ids)), "Duplicate case IDs found"

    def test_get_case_by_id(self):
        case = get_case("A1")
        assert case.case_id == "A1"
        assert case.category == "NO_BUILTIN"

    def test_get_nonexistent_case_raises(self):
        with pytest.raises(KeyError):
            get_case("NONEXISTENT_XYZ")

    def test_supersession_cases_have_expected_superseded(self):
        b1 = get_case("B1")
        assert len(b1.expected_superseded_types) >= 1

    def test_conflict_case_has_expected_conflicting(self):
        e1 = get_case("E1")
        assert len(e1.expected_conflicting_types) >= 1

    def test_fail_cases_have_expected_violated(self):
        fail_cases = [c for c in load_cases() if c.expected_overall == "FAIL"
                      and not c.expected_conflicting_types]
        for case in fail_cases:
            assert case.expected_violated_types, \
                f"FAIL case {case.case_id} has no expected violated types"

    def test_at_least_one_pass_and_one_fail(self):
        cases = load_cases()
        pass_cases = [c for c in cases if c.expected_overall == "PASS"]
        fail_cases = [c for c in cases if c.expected_overall == "FAIL"]
        assert pass_cases
        assert fail_cases

    def test_all_categories_covered(self):
        categories = {c.category for c in load_cases()}
        required = {"NO_BUILTIN", "SUPERSESSION", "CONFLICT", "ERROR_HANDLING",
                    "NAMING", "COMPLEXITY", "MIXED"}
        missing = required - categories
        assert not missing, f"Missing categories: {missing}"


# ---------------------------------------------------------------------------
# Metrics: safe precision / recall
# ---------------------------------------------------------------------------

class TestPrecisionRecall:
    def test_precision_normal(self):
        assert abs(_safe_precision(3, 1) - 0.75) < 1e-9

    def test_precision_zero_denominator(self):
        assert _safe_precision(0, 0) is None

    def test_recall_normal(self):
        assert abs(_safe_recall(3, 1) - 0.75) < 1e-9

    def test_recall_zero_denominator(self):
        assert _safe_recall(0, 0) is None

    def test_precision_perfect(self):
        assert abs(_safe_precision(5, 0) - 1.0) < 1e-9

    def test_recall_perfect(self):
        assert abs(_safe_recall(5, 0) - 1.0) < 1e-9

    def test_precision_zero_tp(self):
        # 0 TP, 2 FP → precision = 0.0
        assert abs(_safe_precision(0, 2) - 0.0) < 1e-9

    def test_recall_zero_tp(self):
        # 0 TP, 2 FN → recall = 0.0
        assert abs(_safe_recall(0, 2) - 0.0) < 1e-9


# ---------------------------------------------------------------------------
# Baseline execution
# ---------------------------------------------------------------------------

class TestBaselineExecution:
    def test_baseline_runs_on_case_a1(self):
        case = get_case("A1")
        bl = BaselineVerifier().verify(case.case_id, case.conversation, case.code)
        assert isinstance(bl, BaselineResult)
        assert bl.case_id == "A1"

    def test_baseline_finds_no_builtin_type(self):
        case = get_case("A1")
        bl = BaselineVerifier().verify(case.case_id, case.conversation, case.code)
        assert "no_builtin" in bl.active_types

    def test_baseline_detects_violation_on_a1(self):
        case = get_case("A1")
        bl = BaselineVerifier().verify(case.case_id, case.conversation, case.code)
        assert bl.overall_status == "FAIL"

    def test_baseline_returns_pass_on_a2(self):
        case = get_case("A2")
        bl = BaselineVerifier().verify(case.case_id, case.conversation, case.code)
        assert bl.overall_status == "PASS"

    def test_baseline_detects_naming_violation(self):
        case = get_case("G2")
        bl = BaselineVerifier().verify(case.case_id, case.conversation, case.code)
        assert bl.overall_status == "FAIL"

    def test_baseline_result_has_per_constraint_dict(self):
        case = get_case("A1")
        bl = BaselineVerifier().verify(case.case_id, case.conversation, case.code)
        assert isinstance(bl.per_constraint, dict)
        assert len(bl.per_constraint) >= 1

    def test_baseline_complexity_uncertain(self):
        case = get_case("J1")
        bl = BaselineVerifier().verify(case.case_id, case.conversation, case.code)
        assert "complexity" in bl.uncertain_types or "complexity" in bl.active_types


# ---------------------------------------------------------------------------
# ConstraintGuard execution (single cases)
# ---------------------------------------------------------------------------

class TestCGExecution:
    def test_cg_runs_on_case_a1(self):
        case = get_case("A1")
        result = run_constraintguard(case)
        assert result.case_id == "A1"
        assert result.error is None

    def test_cg_detects_violation_on_a1(self):
        case = get_case("A1")
        result = run_constraintguard(case)
        assert result.overall_status == "FAIL"
        assert "no_builtin" in result.violated_types

    def test_cg_pass_on_a2(self):
        case = get_case("A2")
        result = run_constraintguard(case)
        assert result.overall_status == "PASS"

    def test_cg_detects_supersession_on_b1(self):
        case = get_case("B1")
        result = run_constraintguard(case)
        assert "algorithm" in result.superseded_types

    def test_cg_detects_conflict_on_e1(self):
        case = get_case("E1")
        result = run_constraintguard(case)
        assert "error_handling" in result.conflicting_types
        assert result.overall_status == "FAIL"

    def test_cg_naming_satisfied_on_g1(self):
        case = get_case("G1")
        result = run_constraintguard(case)
        assert result.overall_status == "PASS"

    def test_cg_naming_violated_on_g2(self):
        case = get_case("G2")
        result = run_constraintguard(case)
        assert result.overall_status == "FAIL"

    def test_cg_complexity_does_not_produce_violated(self):
        case = get_case("J1")
        result = run_constraintguard(case)
        assert "complexity" not in result.violated_types

    def test_cg_no_error_on_any_case(self):
        for case in load_cases():
            result = run_constraintguard(case)
            assert result.error is None, \
                f"Case {case.case_id} raised: {result.error}"


# ---------------------------------------------------------------------------
# Comparison and aggregate metrics
# ---------------------------------------------------------------------------

class TestComparison:
    def setup_method(self):
        self.case = get_case("A1")
        self.cg = run_constraintguard(self.case)
        self.bl = BaselineVerifier().verify(
            self.case.case_id, self.case.conversation, self.case.code
        )
        self.comp = compare_case(self.case, self.cg, self.bl)

    def test_comparison_has_correct_case_id(self):
        assert self.comp.case_id == "A1"

    def test_comparison_actual_is_violation(self):
        assert self.comp.actual_is_violation is True  # A1 is a FAIL case

    def test_comparison_cg_predicted_violation(self):
        assert self.comp.cg_predicted_violation is True

    def test_comparison_cg_overall_correct(self):
        assert self.comp.cg_overall_correct is True


class TestAggregateMetrics:
    def setup_method(self):
        cases = load_cases()
        bl = BaselineVerifier()
        self.cg_results = [run_constraintguard(c) for c in cases]
        self.bl_results = [bl.verify(c.case_id, c.conversation, c.code) for c in cases]
        self.comparisons = [
            compare_case(c, cg, bl_r)
            for c, cg, bl_r in zip(cases, self.cg_results, self.bl_results)
        ]
        self.metrics = aggregate_metrics(cases, self.comparisons, self.cg_results)

    def test_n_cases_correct(self):
        assert self.metrics.n_cases == len(load_cases())

    def test_n_constraints_positive(self):
        assert self.metrics.n_constraints > 0

    def test_id_accuracy_between_0_and_1(self):
        assert 0.0 <= self.metrics.cg_id_accuracy <= 1.0
        assert 0.0 <= self.metrics.bl_id_accuracy <= 1.0

    def test_e2e_accuracy_between_0_and_1(self):
        assert 0.0 <= self.metrics.cg_e2e_accuracy <= 1.0
        assert 0.0 <= self.metrics.bl_e2e_accuracy <= 1.0

    def test_precision_is_none_or_valid(self):
        p = self.metrics.cg_precision
        assert p is None or 0.0 <= p <= 1.0

    def test_recall_is_none_or_valid(self):
        r = self.metrics.cg_recall
        assert r is None or 0.0 <= r <= 1.0

    def test_confusion_matrix_sums_to_n_cases(self):
        total_cg = self.metrics.cg_tp + self.metrics.cg_fp + \
                   self.metrics.cg_fn + self.metrics.cg_tn
        assert total_cg == self.metrics.n_cases

    def test_confusion_matrix_sums_to_n_cases_baseline(self):
        total_bl = self.metrics.bl_tp + self.metrics.bl_fp + \
                   self.metrics.bl_fn + self.metrics.bl_tn
        assert total_bl == self.metrics.n_cases


# ---------------------------------------------------------------------------
# Report serialization
# ---------------------------------------------------------------------------

class TestReport:
    def setup_method(self):
        cases = load_cases()
        from constraint_guard.evaluation.runner import run_evaluation
        self.eval_result = run_evaluation(cases)
        self.metrics = aggregate_metrics(
            self.eval_result.cases,
            self.eval_result.comparisons,
            self.eval_result.cg_results,
        )

    def test_text_report_is_string(self):
        text = build_text_report(self.eval_result, self.metrics)
        assert isinstance(text, str)
        assert len(text) > 100

    def test_text_report_contains_dataset_name(self):
        text = build_text_report(self.eval_result, self.metrics)
        assert "ConstraintBench-Small" in text

    def test_text_report_contains_disclaimer(self):
        text = build_text_report(self.eval_result, self.metrics)
        assert "NOT MBPP" in text

    def test_json_output_is_dict(self):
        data = build_json_output(self.eval_result, self.metrics)
        assert isinstance(data, dict)

    def test_json_has_required_keys(self):
        data = build_json_output(self.eval_result, self.metrics)
        for key in ("dataset", "constraintguard", "baseline", "per_case", "error_analysis"):
            assert key in data, f"Missing key: {key}"

    def test_json_per_case_count_matches(self):
        data = build_json_output(self.eval_result, self.metrics)
        assert len(data["per_case"]) == len(self.eval_result.cases)

    def test_json_serializable(self):
        import json
        data = build_json_output(self.eval_result, self.metrics)
        serialized = json.dumps(data, default=str)
        assert len(serialized) > 100

    def test_full_run_evaluation(self):
        from constraint_guard.evaluation.runner import run_evaluation
        result = run_evaluation(load_cases())
        assert isinstance(result, EvaluationResult)
        assert len(result.cg_results) == len(load_cases())
        assert len(result.bl_results) == len(load_cases())
        assert len(result.comparisons) == len(load_cases())
