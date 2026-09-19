"""
tests/test_lexical_verifier.py
================================
Tests for constraint_guard.verifier.lexical
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from constraint_guard.models import Constraint, ConstraintType, ConstraintStatus
from constraint_guard.verifier import lexical


def _c(text, ctype=ConstraintType.NO_BUILTIN, target=None):
    return Constraint(text=text, source_turn=1, type=ctype, target=target)


# ---------------------------------------------------------------------------
# NO_BUILTIN — violations
# ---------------------------------------------------------------------------

class TestNoBuiltinViolated:
    def test_max_call_detected(self):
        c = _c("Do not use max()", target="max")
        ev = lexical.verify(c, "def f(lst): return max(lst)")
        assert not ev.passed
        assert ev.metadata["status"] == "violated"
        assert ev.confidence >= 0.90

    def test_sorted_call_detected(self):
        c = _c("Do not use sorted()", target="sorted")
        ev = lexical.verify(c, "items = sorted(data)")
        assert not ev.passed
        assert ev.metadata["status"] == "violated"

    def test_eval_call_detected(self):
        c = _c("Do not use eval()", target="eval")
        ev = lexical.verify(c, "result = eval(expr)")
        assert not ev.passed
        assert ev.metadata["status"] == "violated"

    def test_line_number_in_evidence(self):
        c = _c("Do not use max()", target="max")
        code = "def f(lst):\n    x = 1\n    return max(lst)"
        ev = lexical.verify(c, code)
        assert ev.line_number == 3

    def test_import_of_forbidden_module(self):
        c = _c("Do not import numpy", ctype=ConstraintType.NO_BUILTIN, target="numpy")
        ev = lexical.verify(c, "import numpy\nprint(numpy.array([1,2]))")
        assert not ev.passed
        assert ev.metadata["status"] == "violated"

    def test_code_snippet_captured(self):
        c = _c("Do not use max()", target="max")
        ev = lexical.verify(c, "return max(lst)")
        assert ev.code_snippet is not None


# ---------------------------------------------------------------------------
# NO_BUILTIN — satisfied
# ---------------------------------------------------------------------------

class TestNoBuiltinSatisfied:
    def test_no_max_call_passes(self):
        c = _c("Do not use max()", target="max")
        code = """
def find_max(lst):
    if not lst:
        return None
    best = lst[0]
    for x in lst[1:]:
        if x > best:
            best = x
    return best
"""
        ev = lexical.verify(c, code)
        assert ev.passed
        assert ev.metadata["status"] == "satisfied"

    def test_max_in_string_not_detected_as_call(self):
        """'max' inside a string should not trigger the call detector."""
        c = _c("Do not use max()", target="max")
        code = 'def f(): return "use max manually"'
        ev = lexical.verify(c, code)
        assert ev.passed

    def test_max_as_variable_not_call(self):
        """'max_value = 0' is not a call to max()."""
        c = _c("Do not use max()", target="max")
        code = "max_value = 0\nreturn max_value"
        ev = lexical.verify(c, code)
        assert ev.passed

    def test_sorted_alternative_acceptable(self):
        c = _c("Do not use sorted()", target="sorted")
        code = """
def my_sort(lst):
    return lst[:]  # no sorted()
"""
        ev = lexical.verify(c, code)
        assert ev.passed


# ---------------------------------------------------------------------------
# NO_BUILTIN — uncertain
# ---------------------------------------------------------------------------

class TestNoBuiltinUncertain:
    def test_missing_target_is_uncertain(self):
        c = _c("Do not use forbidden builtins", target=None)
        ev = lexical.verify(c, "return x + 1")
        assert ev.metadata["status"] == "uncertain"
        assert ev.confidence == 0.0


# ---------------------------------------------------------------------------
# Non-applicable types → uncertain
# ---------------------------------------------------------------------------

class TestNonApplicable:
    def test_naming_constraint_is_uncertain(self):
        c = _c("Name the function find_max", ctype=ConstraintType.NAMING, target="find_max")
        ev = lexical.verify(c, "def find_max(lst): pass")
        assert ev.metadata["status"] == "uncertain"

    def test_complexity_constraint_is_uncertain(self):
        c = _c("O(n) time", ctype=ConstraintType.COMPLEXITY)
        ev = lexical.verify(c, "def f(n): return n*2")
        assert ev.metadata["status"] == "uncertain"

    def test_structure_constraint_is_uncertain(self):
        c = _c("Use a class", ctype=ConstraintType.STRUCTURE)
        ev = lexical.verify(c, "class MyClass: pass")
        assert ev.metadata["status"] == "uncertain"
