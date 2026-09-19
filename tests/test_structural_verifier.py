"""
tests/test_structural_verifier.py
====================================
Tests for constraint_guard.verifier.structural
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from constraint_guard.models import Constraint, ConstraintType
from constraint_guard.verifier import structural


def _c(text, ctype=ConstraintType.NO_BUILTIN, target=None):
    return Constraint(text=text, source_turn=1, type=ctype, target=target)


# ---------------------------------------------------------------------------
# NO_BUILTIN via AST
# ---------------------------------------------------------------------------

class TestStructuralNoBuiltin:
    def test_max_call_violated(self):
        c = _c("Do not use max()", target="max")
        ev = structural.verify(c, "def f(lst): return max(lst)")
        assert not ev.passed
        assert ev.metadata["status"] == "violated"
        assert ev.metadata.get("ast_node_type") == "Call"

    def test_max_not_present_satisfied(self):
        c = _c("Do not use max()", target="max")
        code = "def f(lst):\n    return lst[0] if lst else None"
        ev = structural.verify(c, code)
        assert ev.passed
        assert ev.metadata["status"] == "satisfied"

    def test_line_number_included(self):
        c = _c("Do not use max()", target="max")
        code = "def f(lst):\n    x = 1\n    return max(lst)"
        ev = structural.verify(c, code)
        assert ev.line_number == 3

    def test_no_target_is_uncertain(self):
        c = _c("Do not use built-ins", target=None)
        ev = structural.verify(c, "return max(lst)")
        assert ev.metadata["status"] == "uncertain"


# ---------------------------------------------------------------------------
# ALGORITHM — recursion
# ---------------------------------------------------------------------------

class TestStructuralAlgorithmRecursion:
    def test_recursion_detected_as_violated_when_forbidden(self):
        c = _c("Do not use recursion", ctype=ConstraintType.ALGORITHM)
        code = """
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)
"""
        ev = structural.verify(c, code)
        assert not ev.passed
        assert ev.metadata["status"] == "violated"

    def test_no_recursion_when_forbidden_is_satisfied(self):
        c = _c("Do not use recursion", ctype=ConstraintType.ALGORITHM)
        code = """
def factorial(n):
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result
"""
        ev = structural.verify(c, code)
        assert ev.passed
        assert ev.metadata["status"] == "satisfied"

    def test_recursion_required_is_satisfied_when_present(self):
        c = _c("Use recursion", ctype=ConstraintType.ALGORITHM)
        code = """
def fact(n):
    return 1 if n <= 1 else n * fact(n-1)
"""
        ev = structural.verify(c, code)
        assert ev.passed

    def test_recursion_required_violated_when_absent(self):
        c = _c("Use recursion", ctype=ConstraintType.ALGORITHM)
        code = """
def fact(n):
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result
"""
        ev = structural.verify(c, code)
        assert not ev.passed
        assert ev.metadata["status"] == "violated"

    def test_recursion_line_number_included(self):
        c = _c("Do not use recursion", ctype=ConstraintType.ALGORITHM)
        code = "def f(n):\n    return f(n-1) if n > 0 else 0"
        ev = structural.verify(c, code)
        assert ev.line_number == 2


# ---------------------------------------------------------------------------
# NAMING
# ---------------------------------------------------------------------------

class TestStructuralNaming:
    def test_correct_function_name_satisfied(self):
        c = _c("Name the function calculate_max", ctype=ConstraintType.NAMING,
               target="calculate_max")
        ev = structural.verify(c, "def calculate_max(lst): return max(lst)")
        assert ev.passed
        assert ev.metadata["status"] == "satisfied"

    def test_wrong_function_name_violated(self):
        c = _c("Name the function calculate_max", ctype=ConstraintType.NAMING,
               target="calculate_max")
        ev = structural.verify(c, "def find_max(lst): return max(lst)")
        assert not ev.passed
        assert ev.metadata["status"] == "violated"

    def test_missing_target_is_uncertain(self):
        c = _c("Name the function correctly", ctype=ConstraintType.NAMING, target=None)
        ev = structural.verify(c, "def find_max(lst): pass")
        assert ev.metadata["status"] == "uncertain"


# ---------------------------------------------------------------------------
# STRUCTURE
# ---------------------------------------------------------------------------

class TestStructuralStructure:
    def test_class_present_when_required(self):
        c = _c("Use a class", ctype=ConstraintType.STRUCTURE)
        ev = structural.verify(c, "class MyClass:\n    def method(self): pass")
        assert ev.passed

    def test_class_absent_when_required_violated(self):
        c = _c("Use a class", ctype=ConstraintType.STRUCTURE)
        ev = structural.verify(c, "def plain_func(): pass")
        assert not ev.passed

    def test_single_function_satisfied(self):
        c = _c("Use a single function", ctype=ConstraintType.STRUCTURE)
        ev = structural.verify(c, "def f(x): return x")
        assert ev.passed

    def test_multiple_functions_violated_when_single_required(self):
        c = _c("Use a single function", ctype=ConstraintType.STRUCTURE)
        code = "def f(x): return x\ndef g(x): return x"
        ev = structural.verify(c, code)
        assert not ev.passed


# ---------------------------------------------------------------------------
# COMPLEXITY — always uncertain
# ---------------------------------------------------------------------------

class TestStructuralComplexity:
    def test_complexity_always_uncertain(self):
        c = _c("O(n) time complexity", ctype=ConstraintType.COMPLEXITY)
        ev = structural.verify(c, "def f(n):\n    for i in range(n): pass")
        assert ev.metadata["status"] == "uncertain"
        assert ev.confidence == 0.0

    def test_complexity_reason_includes_depth(self):
        c = _c("O(n) time", ctype=ConstraintType.COMPLEXITY)
        ev = structural.verify(c, "def f(n):\n    for i in range(n):\n        for j in range(n): pass")
        assert "depth" in ev.message.lower() or "nesting" in ev.message.lower()

    def test_complexity_never_produces_satisfied(self):
        c = _c("O(n) time", ctype=ConstraintType.COMPLEXITY)
        ev = structural.verify(c, "def f(n): return n * 2")
        assert ev.metadata["status"] != "satisfied"


# ---------------------------------------------------------------------------
# Syntax error
# ---------------------------------------------------------------------------

class TestStructuralSyntaxError:
    def test_syntax_error_produces_uncertain(self):
        c = _c("Do not use max()", target="max")
        ev = structural.verify(c, "def f(lst  # broken")
        assert ev.metadata["status"] == "uncertain"
        assert "syntax" in ev.message.lower()
