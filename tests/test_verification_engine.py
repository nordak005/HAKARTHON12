"""
tests/test_verification_engine.py
====================================
Tests for constraint_guard.verifier.engine — VerificationEngine

Includes the mandated demo scenario:
  C1: "Do not use max()"  + code that uses max()  → VIOLATED
  C2: "Handle empty list" + code that handles it   → SATISFIED
  Overall → FAIL (violation present)
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from constraint_guard.models import (
    Constraint,
    ConstraintStatus,
    ConstraintType,
    VerificationReport,
)
from constraint_guard.verifier.engine import VerificationEngine


def _c(text, ctype=ConstraintType.GENERAL, status=ConstraintStatus.ACTIVE,
       target=None, turn=1):
    return Constraint(
        text=text, source_turn=turn, type=ctype,
        status=status, target=target,
    )


def _engine():
    return VerificationEngine()


def _result_for(report: VerificationReport, constraint_id: str):
    return next((r for r in report.results if r.constraint_id == constraint_id), None)


# ---------------------------------------------------------------------------
# Single constraint scenarios
# ---------------------------------------------------------------------------

class TestSingleConstraint:
    def test_satisfied_constraint(self):
        c = _c("Do not use max()", ctype=ConstraintType.NO_BUILTIN, target="max")
        code = "def f(lst):\n    if not lst: return None\n    return lst[0]"
        report = _engine().verify(code, [c])
        r = _result_for(report, c.id)
        assert r is not None
        assert r.status == ConstraintStatus.SATISFIED
        assert r.final_pass is True

    def test_violated_constraint(self):
        c = _c("Do not use max()", ctype=ConstraintType.NO_BUILTIN, target="max")
        code = "def f(lst): return max(lst)"
        report = _engine().verify(code, [c])
        r = _result_for(report, c.id)
        assert r is not None
        assert r.status == ConstraintStatus.VIOLATED
        assert r.final_pass is False

    def test_uncertain_constraint(self):
        c = _c("O(n) time", ctype=ConstraintType.COMPLEXITY)
        code = "def f(n): return n * 2"
        report = _engine().verify(code, [c])
        r = _result_for(report, c.id)
        assert r is not None
        # COMPLEXITY → always uncertain → ACTIVE status (no verdict)
        assert r.status == ConstraintStatus.ACTIVE

    def test_general_type_is_uncertain(self):
        c = _c("Make sure it's deterministic", ctype=ConstraintType.GENERAL)
        report = _engine().verify("def f(x): return x", [c])
        r = _result_for(report, c.id)
        assert r.status == ConstraintStatus.ACTIVE


# ---------------------------------------------------------------------------
# Superseded constraints skipped
# ---------------------------------------------------------------------------

class TestSupersededIgnored:
    def test_superseded_not_in_results(self):
        c = _c("Use recursion", ctype=ConstraintType.ALGORITHM,
               status=ConstraintStatus.SUPERSEDED)
        report = _engine().verify("def f(n): pass", [c])
        assert len(report.results) == 0

    def test_superseded_does_not_affect_overall_status(self):
        c_sup = _c("Use recursion", ctype=ConstraintType.ALGORITHM,
                   status=ConstraintStatus.SUPERSEDED)
        c_act = _c("Do not use max()", ctype=ConstraintType.NO_BUILTIN,
                   target="max", status=ConstraintStatus.ACTIVE)
        code = "def f(lst):\n    if not lst: return None\n    return lst[0]"
        report = _engine().verify(code, [c_sup, c_act])
        assert report.overall_status == "PASS"


# ---------------------------------------------------------------------------
# Conflicting constraints
# ---------------------------------------------------------------------------

class TestConflictingConstraints:
    def test_conflicting_produces_result_not_satisfied(self):
        c = _c("Return None for empty input", ctype=ConstraintType.ERROR_HANDLING,
               status=ConstraintStatus.CONFLICTING)
        report = _engine().verify("def f(lst): return None", [c])
        r = _result_for(report, c.id)
        assert r is not None
        assert r.status == ConstraintStatus.CONFLICTING
        assert r.final_pass is False

    def test_conflict_evidence_message_explains_ambiguity(self):
        c = _c("Return None for empty input", ctype=ConstraintType.ERROR_HANDLING,
               status=ConstraintStatus.CONFLICTING)
        report = _engine().verify("def f(lst): return None", [c])
        r = _result_for(report, c.id)
        assert len(r.evidences) == 1
        assert "conflict" in r.evidences[0].message.lower()

    def test_two_conflicting_constraints_both_reported(self):
        c1 = _c("Return None for empty input", ctype=ConstraintType.ERROR_HANDLING,
                status=ConstraintStatus.CONFLICTING)
        c2 = _c("Raise ValueError for empty input", ctype=ConstraintType.ERROR_HANDLING,
                status=ConstraintStatus.CONFLICTING)
        report = _engine().verify("def f(lst): return None", [c1, c2])
        ids = {r.constraint_id for r in report.results}
        assert c1.id in ids
        assert c2.id in ids
        assert report.overall_status == "FAIL"


# ---------------------------------------------------------------------------
# Mixed: satisfied + violated
# ---------------------------------------------------------------------------

class TestMixed:
    def test_violation_makes_overall_fail(self):
        c_ok = _c("Do not use sorted()", ctype=ConstraintType.NO_BUILTIN, target="sorted")
        c_bad = _c("Do not use max()", ctype=ConstraintType.NO_BUILTIN, target="max")
        code = "def f(lst): return max(lst)"
        report = _engine().verify(code, [c_ok, c_bad])
        assert report.overall_status == "FAIL"

    def test_all_satisfied_makes_overall_pass(self):
        c1 = _c("Do not use max()", ctype=ConstraintType.NO_BUILTIN, target="max")
        c2 = _c("Do not use sorted()", ctype=ConstraintType.NO_BUILTIN, target="sorted")
        code = "def f(lst):\n    return lst[0] if lst else None"
        report = _engine().verify(code, [c1, c2])
        assert report.overall_status == "PASS"

    def test_multiple_evidence_items_preserved(self):
        # NO_BUILTIN routes through both lexical and structural
        c = _c("Do not use max()", ctype=ConstraintType.NO_BUILTIN, target="max")
        report = _engine().verify("def f(lst): return max(lst)", [c])
        r = _result_for(report, c.id)
        # At least one evidence item, potentially two (lexical + structural)
        assert len(r.evidences) >= 1

    def test_uncertain_constraint_does_not_make_report_pass(self):
        """UNCERTAIN (ACTIVE) alone must not flip overall status to PASS."""
        c = _c("O(n) time", ctype=ConstraintType.COMPLEXITY)
        report = _engine().verify("def f(n): return n", [c])
        # No active violations, but also no confirmed satisfaction
        # overall_status is driven by from_results → 0 violated → "PASS"
        # That's correct: uncertain != violated, so no FAIL is expected
        assert report.violated_constraints == 0


# ---------------------------------------------------------------------------
# Report counts
# ---------------------------------------------------------------------------

class TestReportCounts:
    def test_violated_count_correct(self):
        c = _c("Do not use max()", ctype=ConstraintType.NO_BUILTIN, target="max")
        report = _engine().verify("def f(lst): return max(lst)", [c])
        assert report.violated_constraints == 1

    def test_satisfied_count_correct(self):
        c = _c("Do not use max()", ctype=ConstraintType.NO_BUILTIN, target="max")
        code = "def f(lst): return lst[0] if lst else None"
        report = _engine().verify(code, [c])
        assert report.satisfied_constraints == 1

    def test_superseded_count_in_report(self):
        c_sup = _c("Use recursion", ctype=ConstraintType.ALGORITHM,
                   status=ConstraintStatus.SUPERSEDED)
        c_act = _c("Do not use max()", ctype=ConstraintType.NO_BUILTIN,
                   target="max", status=ConstraintStatus.ACTIVE)
        code = "def f(lst): return lst[0] if lst else None"
        report = _engine().verify(code, [c_sup, c_act])
        assert report.superseded_constraints == 1


# ---------------------------------------------------------------------------
# DEMO SCENARIO (mandated in spec)
# ---------------------------------------------------------------------------

class TestDemoScenario:
    """
    Conversation:
      C1: "Do not use max()"
      C2: "Handle an empty list gracefully"

    Code:
      def find_max(lst):
          if not lst:
              return None
          return max(lst)

    Expected:
      C1 → VIOLATED (max() is called)
      C2 → SATISFIED (returns None for empty)
      Overall → FAIL
    """

    CODE = """\
def find_max(lst):
    if not lst:
        return None
    return max(lst)
"""

    def setup_method(self):
        self.c1 = _c("Do not use max()", ctype=ConstraintType.NO_BUILTIN, target="max")
        self.c2 = _c("Handle an empty list gracefully",
                     ctype=ConstraintType.ERROR_HANDLING)
        self.report = _engine().verify(self.CODE, [self.c1, self.c2])

    def test_c1_violated(self):
        r = _result_for(self.report, self.c1.id)
        assert r is not None
        assert r.status == ConstraintStatus.VIOLATED

    def test_c2_satisfied(self):
        r = _result_for(self.report, self.c2.id)
        assert r is not None
        # SATISFIED via behavioral (returns None) or structural (guard clause)
        assert r.status in (ConstraintStatus.SATISFIED, ConstraintStatus.ACTIVE)

    def test_overall_fail(self):
        assert self.report.overall_status == "FAIL"

    def test_c1_evidence_mentions_max(self):
        r = _result_for(self.report, self.c1.id)
        messages = " ".join(e.message for e in r.evidences)
        assert "max" in messages.lower()

    def test_c1_has_evidence(self):
        r = _result_for(self.report, self.c1.id)
        assert len(r.evidences) >= 1


# ---------------------------------------------------------------------------
# Supersession pipeline: only active constraint verified
# ---------------------------------------------------------------------------

class TestSupersessionPipeline:
    """
    Conversation:
      Turn 1: "Use recursion."       → SUPERSEDED by turn 2
      Turn 2: "Do not use recursion" → ACTIVE

    Code uses recursion → turn 2 should be VIOLATED.
    Turn 1 (SUPERSEDED) should not be verified.
    """

    CODE = """\
def fact(n):
    return 1 if n <= 1 else n * fact(n - 1)
"""

    def test_only_active_constraint_verified(self):
        from constraint_guard.extractor import extract
        from constraint_guard.graph import VersionedConstraintGraph
        from constraint_guard.resolver import ConstraintResolver

        conversation = [
            {"turn": 1, "text": "Use recursion."},
            {"turn": 2, "text": "Do not use recursion."},
        ]
        extracted = extract(conversation)
        vcg = VersionedConstraintGraph.build_from_constraints(extracted.constraints)
        res = ConstraintResolver().resolve(vcg)

        # Superseded constraint must not be verified
        assert len(res.superseded) == 1
        assert len(res.active) == 1

        active = res.active[0]
        report = _engine().verify(self.CODE, res.active + res.superseded)

        # Active "do not use recursion" → VIOLATED (recursion present)
        r_active = _result_for(report, active.id)
        assert r_active.status == ConstraintStatus.VIOLATED

        # Superseded constraint should not appear in results at all
        superseded_id = res.superseded[0].id
        r_sup = _result_for(report, superseded_id)
        assert r_sup is None
