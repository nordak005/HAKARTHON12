"""
tests/test_behavioral_verifier.py
====================================
Tests for constraint_guard.verifier.behavioral

These tests execute real subprocesses, so they require Python to be on PATH.
Each test uses simple, well-understood code so behavior is deterministic.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from constraint_guard.models import Constraint, ConstraintType
from constraint_guard.verifier import behavioral


def _c(text, ctype=ConstraintType.ERROR_HANDLING, target=None):
    return Constraint(text=text, source_turn=1, type=ctype, target=target)


# ---------------------------------------------------------------------------
# ERROR_HANDLING — "Return None for empty input"
# ---------------------------------------------------------------------------

class TestBehavioralReturnNone:
    CODE_RETURNS_NONE = """\
def find_max(lst):
    if not lst:
        return None
    return lst[0]
"""

    CODE_DOES_NOT_RETURN_NONE = """\
def find_max(lst):
    return lst[0]
"""

    def test_returns_none_satisfied(self):
        c = _c("Return None for empty input")
        ev = behavioral.verify(c, self.CODE_RETURNS_NONE)
        assert ev.passed
        assert ev.metadata["status"] == "satisfied"

    def test_returns_none_confident(self):
        c = _c("Return None for empty input")
        ev = behavioral.verify(c, self.CODE_RETURNS_NONE)
        assert ev.confidence >= 0.80

    def test_does_not_return_none_violated(self):
        c = _c("Return None for empty input")
        ev = behavioral.verify(c, self.CODE_DOES_NOT_RETURN_NONE)
        assert not ev.passed
        assert ev.metadata["status"] in ("violated", "uncertain")

    def test_evidence_includes_function_name(self):
        c = _c("Return None for empty input")
        ev = behavioral.verify(c, self.CODE_RETURNS_NONE)
        assert "find_max" in ev.message


# ---------------------------------------------------------------------------
# ERROR_HANDLING — "Raise ValueError for empty input"
# ---------------------------------------------------------------------------

class TestBehavioralRaiseValueError:
    CODE_RAISES = """\
def find_max(lst):
    if not lst:
        raise ValueError("List cannot be empty")
    return lst[0]
"""

    CODE_RETURNS_NONE_INSTEAD = """\
def find_max(lst):
    if not lst:
        return None
    return lst[0]
"""

    def test_raises_valueerror_satisfied(self):
        c = _c("Raise ValueError for empty input")
        ev = behavioral.verify(c, self.CODE_RAISES)
        assert ev.passed
        assert ev.metadata["status"] == "satisfied"

    def test_returns_none_instead_of_raise_violated(self):
        c = _c("Raise ValueError for empty input")
        ev = behavioral.verify(c, self.CODE_RETURNS_NONE_INSTEAD)
        assert not ev.passed
        assert ev.metadata["status"] == "violated"


# ---------------------------------------------------------------------------
# ERROR_HANDLING — "Handle empty list gracefully"
# ---------------------------------------------------------------------------

class TestBehavioralHandleGracefully:
    CODE_GRACEFUL = """\
def find_max(lst):
    if not lst:
        return None
    return max(lst)
"""

    CODE_CRASHES = """\
def find_max(lst):
    return lst[0]  # IndexError on empty list
"""

    def test_graceful_handling_satisfied(self):
        c = _c("Handle an empty list gracefully")
        ev = behavioral.verify(c, self.CODE_GRACEFUL)
        assert ev.passed

    def test_crash_on_empty_violated(self):
        c = _c("Handle an empty list gracefully")
        ev = behavioral.verify(c, self.CODE_CRASHES)
        assert not ev.passed
        assert ev.metadata["status"] == "violated"


# ---------------------------------------------------------------------------
# Timeout handling
# ---------------------------------------------------------------------------

class TestBehavioralTimeout:
    CODE_INFINITE_LOOP = """\
def find_max(lst):
    while True:
        pass
"""

    def test_timeout_produces_uncertain(self):
        # Temporarily set timeout low to keep tests fast
        import constraint_guard.verifier.behavioral as bmod
        original = bmod._TIMEOUT_SECONDS
        bmod._TIMEOUT_SECONDS = 1.0
        try:
            c = _c("Return None for empty input")
            ev = bmod.verify(c, self.CODE_INFINITE_LOOP)
            assert ev.metadata["status"] == "uncertain"
            assert "timeout" in ev.message.lower() or "timed" in ev.message.lower()
        finally:
            bmod._TIMEOUT_SECONDS = original


# ---------------------------------------------------------------------------
# Invalid / broken code
# ---------------------------------------------------------------------------

class TestBehavioralInvalidCode:
    def test_syntax_error_produces_uncertain(self):
        c = _c("Return None for empty input")
        ev = behavioral.verify(c, "def f(lst  # broken syntax")
        assert ev.metadata["status"] == "uncertain"

    def test_no_function_defined_is_uncertain(self):
        c = _c("Return None for empty input")
        ev = behavioral.verify(c, "x = 1 + 2")
        assert ev.metadata["status"] == "uncertain"


# ---------------------------------------------------------------------------
# Unsupported constraint types → UNCERTAIN
# ---------------------------------------------------------------------------

class TestBehavioralUnsupportedTypes:
    def test_no_builtin_is_uncertain(self):
        c = _c("Do not use max()", ctype=ConstraintType.NO_BUILTIN, target="max")
        ev = behavioral.verify(c, "def f(lst): return max(lst)")
        assert ev.metadata["status"] == "uncertain"
        assert not ev.passed

    def test_algorithm_is_uncertain(self):
        c = _c("Use recursion", ctype=ConstraintType.ALGORITHM)
        ev = behavioral.verify(c, "def f(n): return f(n-1) if n > 0 else 0")
        assert ev.metadata["status"] == "uncertain"

    def test_naming_is_uncertain(self):
        c = _c("Name the function calc", ctype=ConstraintType.NAMING, target="calc")
        ev = behavioral.verify(c, "def calc(x): return x")
        assert ev.metadata["status"] == "uncertain"

    def test_complexity_is_uncertain(self):
        c = _c("O(n) time", ctype=ConstraintType.COMPLEXITY)
        ev = behavioral.verify(c, "def f(n): return n")
        assert ev.metadata["status"] == "uncertain"

    def test_general_is_uncertain(self):
        c = _c("Make sure it is efficient", ctype=ConstraintType.GENERAL)
        ev = behavioral.verify(c, "def f(n): return n")
        assert ev.metadata["status"] == "uncertain"

    def test_uncertain_never_becomes_satisfied(self):
        """Unsupported types must not report passed=True."""
        for ctype in (ConstraintType.NO_BUILTIN, ConstraintType.ALGORITHM,
                      ConstraintType.NAMING, ConstraintType.COMPLEXITY,
                      ConstraintType.GENERAL):
            c = _c("some constraint text", ctype=ctype)
            ev = behavioral.verify(c, "def f(): pass")
            assert not ev.passed, f"Expected not passed for type {ctype}"
