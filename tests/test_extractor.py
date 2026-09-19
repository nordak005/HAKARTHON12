"""
tests/test_extractor.py
=======================
Tests for constraint_guard.extractor — rule-based constraint extraction.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from constraint_guard.extractor import extract, is_continuation, ExtractionResult
from constraint_guard.models import ConstraintType, ConstraintStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _single_turn(text: str, turn: int = 1) -> ExtractionResult:
    return extract([{"turn": turn, "text": text}])


def _find(result: ExtractionResult, ctype: ConstraintType):
    """Return the first constraint of the given type, or None."""
    return next((c for c in result.constraints if c.type == ctype), None)


# ---------------------------------------------------------------------------
# Continuation-phrase detection
# ---------------------------------------------------------------------------

class TestIsContinuation:
    def test_keep_previous_restrictions(self):
        assert is_continuation("Keep the previous restrictions.")

    def test_retain_previous_requirements(self):
        assert is_continuation("Retain the previous requirements.")

    def test_same_restrictions(self):
        assert is_continuation("Same restrictions apply.")

    def test_previous_requirements_phrase(self):
        assert is_continuation("Previous requirements still apply.")

    def test_normal_instruction_is_not_continuation(self):
        assert not is_continuation("Do not use max()")

    def test_keep_alone_is_not_continuation(self):
        # "keep" without "previous" or "restrictions" should not trigger
        assert not is_continuation("Keep the list sorted.")

    def test_empty_string_is_not_continuation(self):
        assert not is_continuation("")


# ---------------------------------------------------------------------------
# NO_BUILTIN extraction
# ---------------------------------------------------------------------------

class TestNoBuiltin:
    def test_do_not_use_max(self):
        r = _single_turn("Do not use max()")
        c = _find(r, ConstraintType.NO_BUILTIN)
        assert c is not None, "Expected NO_BUILTIN constraint"
        assert c.target == "max"
        assert c.confidence >= 0.90

    def test_dont_use_sorted(self):
        r = _single_turn("Don't use sorted()")
        c = _find(r, ConstraintType.NO_BUILTIN)
        assert c is not None
        assert c.target == "sorted"

    def test_avoid_using_numpy(self):
        r = _single_turn("avoid using numpy")
        c = _find(r, ConstraintType.NO_BUILTIN)
        assert c is not None
        assert c.target == "numpy"

    def test_without_using_min(self):
        r = _single_turn("Implement it without using min()")
        c = _find(r, ConstraintType.NO_BUILTIN)
        assert c is not None
        assert c.target == "min"

    def test_do_not_use_the_max_function(self):
        r = _single_turn("Do not use the max function")
        c = _find(r, ConstraintType.NO_BUILTIN)
        assert c is not None
        assert c.target == "max"

    def test_source_turn_preserved(self):
        r = _single_turn("Do not use max()", turn=3)
        c = _find(r, ConstraintType.NO_BUILTIN)
        assert c is not None
        assert c.source_turn == 3

    def test_status_defaults_to_active(self):
        r = _single_turn("Do not use max()")
        c = _find(r, ConstraintType.NO_BUILTIN)
        assert c.status == ConstraintStatus.ACTIVE


# ---------------------------------------------------------------------------
# ALGORITHM extraction
# ---------------------------------------------------------------------------

class TestAlgorithm:
    def test_use_recursion(self):
        r = _single_turn("Use recursion")
        c = _find(r, ConstraintType.ALGORITHM)
        assert c is not None

    def test_dont_use_recursion(self):
        r = _single_turn("Don't use recursion")
        c = _find(r, ConstraintType.ALGORITHM)
        assert c is not None
        assert c.confidence >= 0.90

    def test_do_not_use_recursion(self):
        r = _single_turn("Do not use recursion")
        c = _find(r, ConstraintType.ALGORITHM)
        assert c is not None

    def test_use_iteration(self):
        r = _single_turn("Use iteration instead of recursion")
        c = _find(r, ConstraintType.ALGORITHM)
        assert c is not None

    def test_implement_recursively(self):
        r = _single_turn("Implement it recursively")
        c = _find(r, ConstraintType.ALGORITHM)
        assert c is not None


# ---------------------------------------------------------------------------
# ERROR_HANDLING extraction
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_handle_empty_list(self):
        r = _single_turn("Handle an empty list")
        c = _find(r, ConstraintType.ERROR_HANDLING)
        assert c is not None

    def test_return_none_for_empty(self):
        r = _single_turn("Return None for empty input")
        c = _find(r, ConstraintType.ERROR_HANDLING)
        assert c is not None

    def test_raise_value_error(self):
        r = _single_turn("Raise ValueError for empty input")
        c = _find(r, ConstraintType.ERROR_HANDLING)
        assert c is not None
        assert c.target == "ValueError"

    def test_gracefully_handle(self):
        r = _single_turn("Gracefully handle edge cases")
        c = _find(r, ConstraintType.ERROR_HANDLING)
        assert c is not None


# ---------------------------------------------------------------------------
# STRUCTURE extraction
# ---------------------------------------------------------------------------

class TestStructure:
    def test_use_a_class(self):
        r = _single_turn("Use a class to encapsulate the logic")
        c = _find(r, ConstraintType.STRUCTURE)
        assert c is not None

    def test_use_single_function(self):
        r = _single_turn("Use a single function only")
        c = _find(r, ConstraintType.STRUCTURE)
        assert c is not None

    def test_no_classes(self):
        r = _single_turn("No classes allowed")
        c = _find(r, ConstraintType.STRUCTURE)
        assert c is not None


# ---------------------------------------------------------------------------
# NAMING extraction
# ---------------------------------------------------------------------------

class TestNaming:
    def test_name_the_function(self):
        r = _single_turn("Name the function calculate_max")
        c = _find(r, ConstraintType.NAMING)
        assert c is not None
        assert c.target == "calculate_max"

    def test_function_should_be_called(self):
        r = _single_turn("The function should be called find_max")
        c = _find(r, ConstraintType.NAMING)
        assert c is not None
        assert c.target == "find_max"


# ---------------------------------------------------------------------------
# SIGNATURE extraction
# ---------------------------------------------------------------------------

class TestSignature:
    def test_accept_a_list(self):
        r = _single_turn("The function should accept a list")
        c = _find(r, ConstraintType.SIGNATURE)
        assert c is not None

    def test_return_an_integer(self):
        r = _single_turn("Return an integer")
        c = _find(r, ConstraintType.SIGNATURE)
        assert c is not None


# ---------------------------------------------------------------------------
# COMPLEXITY extraction
# ---------------------------------------------------------------------------

class TestComplexity:
    def test_big_o_n(self):
        r = _single_turn("The solution should run in O(n) time")
        c = _find(r, ConstraintType.COMPLEXITY)
        assert c is not None
        assert c.confidence >= 0.90

    def test_linear_time(self):
        r = _single_turn("Use linear time algorithm")
        c = _find(r, ConstraintType.COMPLEXITY)
        assert c is not None

    def test_constant_space(self):
        r = _single_turn("Use constant space")
        c = _find(r, ConstraintType.COMPLEXITY)
        assert c is not None


# ---------------------------------------------------------------------------
# GENERAL fallback
# ---------------------------------------------------------------------------

class TestGeneral:
    def test_unmatched_requirement_becomes_general(self):
        # Requirement-like language but no specific pattern
        r = _single_turn("Make sure the output is deterministic")
        c = _find(r, ConstraintType.GENERAL)
        assert c is not None
        assert c.confidence == pytest.approx(0.60, abs=0.01)

    def test_non_requirement_text_not_extracted(self):
        # A greeting is not a constraint
        r = _single_turn("Hello, how are you?")
        assert len(r.constraints) == 0

    def test_avoid_keyword_triggers_general_if_no_specific_type(self):
        r = _single_turn("Avoid redundant computation where possible")
        # May match NO_BUILTIN or GENERAL; should produce at least one constraint
        assert len(r.constraints) >= 1


# ---------------------------------------------------------------------------
# Multi-turn and turn preservation
# ---------------------------------------------------------------------------

class TestMultiTurn:
    def test_source_turn_preserved_per_constraint(self):
        r = extract([
            {"turn": 1, "text": "Do not use max()"},
            {"turn": 2, "text": "Handle an empty list"},
        ])
        turns = {c.source_turn for c in r.constraints}
        assert 1 in turns
        assert 2 in turns

    def test_multiple_types_from_multiple_turns(self):
        r = extract([
            {"turn": 1, "text": "Do not use max()"},
            {"turn": 2, "text": "Use recursion"},
            {"turn": 3, "text": "Handle an empty list"},
        ])
        types = {c.type for c in r.constraints}
        assert ConstraintType.NO_BUILTIN in types
        assert ConstraintType.ALGORITHM in types
        assert ConstraintType.ERROR_HANDLING in types

    def test_continuation_turn_not_extracted_as_constraint(self):
        r = extract([
            {"turn": 1, "text": "Do not use max()"},
            {"turn": 2, "text": "Keep the previous restrictions."},
        ])
        assert 2 in r.continuation_turns
        # Only one constraint from turn 1
        assert len(r.constraints) == 1
        assert r.constraints[0].source_turn == 1

    def test_all_constraints_have_ids(self):
        r = extract([
            {"turn": 1, "text": "Do not use max()"},
            {"turn": 2, "text": "Use recursion"},
        ])
        ids = [c.id for c in r.constraints]
        assert len(ids) == len(set(ids)), "IDs must be unique"

    def test_empty_conversation(self):
        r = extract([])
        assert r.constraints == []
        assert r.continuation_turns == []

    def test_single_turn_multiple_patterns(self):
        # A single instruction that could match two types
        r = _single_turn("Do not use max() and handle an empty list")
        types = {c.type for c in r.constraints}
        # Must find at least NO_BUILTIN; ERROR_HANDLING is a bonus
        assert ConstraintType.NO_BUILTIN in types
