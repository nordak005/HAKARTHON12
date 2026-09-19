"""
constraint_guard.evaluation.cases
===================================
ConstraintBench-Small — a custom multi-turn constraint benchmark.

IMPORTANT DISCLAIMER:
This is NOT the MBPP, HumanEval, or any other official benchmark.
These 18 hand-labeled cases were created specifically to evaluate
ConstraintGuard's constraint lifecycle tracking and hybrid verification.

Ground truth labels are deterministic and manually verified.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BenchmarkCase:
    """
    One labeled evaluation case.

    Ground truth labels use constraint TYPE names (strings matching ConstraintType values)
    rather than exact constraint text, so comparison is type-based rather than string-based.
    This tolerates minor extractor variation while still measuring correctness.

    expected_violated_types  : constraint types that should be VIOLATED by the code.
    expected_satisfied_types : constraint types that should be SATISFIED by the code.
    expected_uncertain_types : constraint types that should be UNCERTAIN (no verdict).
    expected_conflicting_types: constraint types that should be CONFLICTING.
    expected_superseded_types : constraint types that should be SUPERSEDED.
    expected_active_types     : constraint types that should be ACTIVE (in force).
    expected_overall          : "PASS" or "FAIL".
    """
    case_id:                  str
    description:              str
    category:                 str
    conversation:             list[dict]
    code:                     str
    expected_active_types:    list[str]        = field(default_factory=list)
    expected_superseded_types:list[str]        = field(default_factory=list)
    expected_conflicting_types:list[str]       = field(default_factory=list)
    expected_violated_types:  list[str]        = field(default_factory=list)
    expected_satisfied_types: list[str]        = field(default_factory=list)
    expected_uncertain_types: list[str]        = field(default_factory=list)
    expected_overall:         str              = "PASS"
    notes:                    str              = ""


# ---------------------------------------------------------------------------
# ConstraintBench-Small dataset (18 cases)
# ---------------------------------------------------------------------------

CONSTRAINT_BENCH_SMALL: list[BenchmarkCase] = [

    # ------------------------------------------------------------------ A: NO_BUILTIN

    BenchmarkCase(
        case_id="A1",
        description="max() forbidden — code USES max() → VIOLATED",
        category="NO_BUILTIN",
        conversation=[
            {"turn": 1, "text": "Write a function that finds the maximum value in a list."},
            {"turn": 2, "text": "Do not use max()."},
        ],
        code="""\
def find_max(lst):
    return max(lst)
""",
        expected_active_types=["no_builtin"],
        expected_violated_types=["no_builtin"],
        expected_overall="FAIL",
    ),

    BenchmarkCase(
        case_id="A2",
        description="max() forbidden — code does NOT use max() → SATISFIED",
        category="NO_BUILTIN",
        conversation=[
            {"turn": 1, "text": "Write a function that finds the maximum value in a list."},
            {"turn": 2, "text": "Do not use max()."},
        ],
        code="""\
def find_max(lst):
    if not lst:
        return None
    best = lst[0]
    for x in lst[1:]:
        if x > best:
            best = x
    return best
""",
        expected_active_types=["no_builtin"],
        expected_satisfied_types=["no_builtin"],
        expected_overall="PASS",
    ),

    BenchmarkCase(
        case_id="A3",
        description="eval() forbidden — code USES eval() → VIOLATED",
        category="NO_BUILTIN",
        conversation=[
            {"turn": 1, "text": "Write an expression evaluator."},
            {"turn": 2, "text": "Do not use eval()."},
        ],
        code="""\
def evaluate(expr):
    return eval(expr)
""",
        expected_active_types=["no_builtin"],
        expected_violated_types=["no_builtin"],
        expected_overall="FAIL",
    ),

    BenchmarkCase(
        case_id="A4",
        description="sorted() forbidden — code USES sorted() → VIOLATED",
        category="NO_BUILTIN",
        conversation=[
            {"turn": 1, "text": "Write a sort function."},
            {"turn": 2, "text": "Do not use sorted()."},
        ],
        code="""\
def my_sort(lst):
    return sorted(lst)
""",
        expected_active_types=["no_builtin"],
        expected_violated_types=["no_builtin"],
        expected_overall="FAIL",
    ),

    # ------------------------------------------------------------------ B: SUPERSESSION

    BenchmarkCase(
        case_id="B1",
        description="Supersession: use→don't use recursion. Iterative code → SATISFIED",
        category="SUPERSESSION",
        conversation=[
            {"turn": 1, "text": "Use recursion."},
            {"turn": 2, "text": "Do not use recursion."},
        ],
        code="""\
def factorial(n):
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result
""",
        expected_active_types=["algorithm"],
        expected_superseded_types=["algorithm"],
        expected_satisfied_types=["algorithm"],
        expected_overall="PASS",
        notes="Turn 1 (use recursion) superseded by turn 2 (no recursion). Iterative code satisfies active constraint.",
    ),

    BenchmarkCase(
        case_id="B2",
        description="Supersession: use→don't use recursion. Recursive code → VIOLATED",
        category="SUPERSESSION",
        conversation=[
            {"turn": 1, "text": "Use recursion."},
            {"turn": 2, "text": "Do not use recursion."},
        ],
        code="""\
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)
""",
        expected_active_types=["algorithm"],
        expected_superseded_types=["algorithm"],
        expected_violated_types=["algorithm"],
        expected_overall="FAIL",
        notes="Recursion is forbidden (active). Code uses recursion → VIOLATED.",
    ),

    # ------------------------------------------------------------------ C: MULTI-LEVEL SUPERSESSION

    BenchmarkCase(
        case_id="C1",
        description="3-turn supersession chain. Final: use iteration. Loop code → SATISFIED",
        category="MULTI_SUPERSESSION",
        conversation=[
            {"turn": 1, "text": "Use recursion."},
            {"turn": 2, "text": "Do not use recursion."},
            {"turn": 3, "text": "Use iteration."},
        ],
        code="""\
def factorial(n):
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result
""",
        expected_active_types=["algorithm"],
        expected_superseded_types=["algorithm"],
        expected_satisfied_types=["algorithm"],
        expected_overall="PASS",
        notes="Turn 3 (use iteration) is the final active requirement. Loop code satisfies it.",
    ),

    # ------------------------------------------------------------------ D: REINFORCEMENT

    BenchmarkCase(
        case_id="D1",
        description="Reinforcement: no max() + 'keep previous restrictions'. Clean code → PASS",
        category="REINFORCEMENT",
        conversation=[
            {"turn": 1, "text": "Do not use max()."},
            {"turn": 2, "text": "Keep the previous restrictions."},
        ],
        code="""\
def find_max(lst):
    if not lst:
        return None
    best = lst[0]
    for x in lst[1:]:
        if x > best:
            best = x
    return best
""",
        expected_active_types=["no_builtin"],
        expected_satisfied_types=["no_builtin"],
        expected_overall="PASS",
        notes="Turn 2 is a continuation phrase. Original NO_BUILTIN stays ACTIVE.",
    ),

    # ------------------------------------------------------------------ E: CONFLICT

    BenchmarkCase(
        case_id="E1",
        description="Conflict: return None vs raise ValueError — both CONFLICTING → FAIL",
        category="CONFLICT",
        conversation=[
            {"turn": 1, "text": "Return None for empty input."},
            {"turn": 2, "text": "Raise ValueError for empty input."},
        ],
        code="""\
def find_max(lst):
    if not lst:
        return None
    return lst[0]
""",
        expected_conflicting_types=["error_handling"],
        expected_overall="FAIL",
        notes="Both constraints are CONFLICTING. Engine reports ambiguity without choosing winner.",
    ),

    # ------------------------------------------------------------------ F: ERROR_HANDLING

    BenchmarkCase(
        case_id="F1",
        description="Return None for empty input. Code returns None → SATISFIED",
        category="ERROR_HANDLING",
        conversation=[
            {"turn": 1, "text": "Write a function. Return None for empty input."},
        ],
        code="""\
def find_max(lst):
    if not lst:
        return None
    return lst[0]
""",
        expected_active_types=["error_handling"],
        expected_satisfied_types=["error_handling"],
        expected_overall="PASS",
    ),

    BenchmarkCase(
        case_id="F2",
        description="Raise ValueError for empty input. Code raises → SATISFIED",
        category="ERROR_HANDLING",
        conversation=[
            {"turn": 1, "text": "Raise ValueError for empty input."},
        ],
        code="""\
def find_max(lst):
    if not lst:
        raise ValueError("List is empty")
    return lst[0]
""",
        expected_active_types=["error_handling"],
        expected_satisfied_types=["error_handling"],
        expected_overall="PASS",
    ),

    # ------------------------------------------------------------------ G: NAMING

    BenchmarkCase(
        case_id="G1",
        description="Naming: function named correctly → SATISFIED",
        category="NAMING",
        conversation=[
            {"turn": 1, "text": "Name the function calculate_max."},
        ],
        code="""\
def calculate_max(lst):
    if not lst:
        return None
    return max(lst)
""",
        expected_active_types=["naming"],
        expected_satisfied_types=["naming"],
        expected_overall="PASS",
    ),

    BenchmarkCase(
        case_id="G2",
        description="Naming: function named INCORRECTLY → VIOLATED",
        category="NAMING",
        conversation=[
            {"turn": 1, "text": "Name the function calculate_max."},
        ],
        code="""\
def find_maximum(lst):
    return max(lst) if lst else None
""",
        expected_active_types=["naming"],
        expected_violated_types=["naming"],
        expected_overall="FAIL",
    ),

    # ------------------------------------------------------------------ I: STRUCTURE

    BenchmarkCase(
        case_id="I1",
        description="Use a class. Code has class → SATISFIED",
        category="STRUCTURE",
        conversation=[
            {"turn": 1, "text": "Use a class to wrap your solution."},
        ],
        code="""\
class MaxFinder:
    def find_max(self, lst):
        if not lst:
            return None
        return max(lst)
""",
        expected_active_types=["structure"],
        expected_satisfied_types=["structure"],
        expected_overall="PASS",
    ),

    # ------------------------------------------------------------------ J: COMPLEXITY

    BenchmarkCase(
        case_id="J1",
        description="O(n) time complexity — always UNCERTAIN (not provable statically)",
        category="COMPLEXITY",
        conversation=[
            {"turn": 1, "text": "Write a function with O(n) time complexity."},
        ],
        code="""\
def linear_scan(lst):
    total = 0
    for x in lst:
        total += x
    return total
""",
        expected_active_types=["complexity"],
        expected_uncertain_types=["complexity"],
        expected_overall="PASS",
        notes="Complexity is always UNCERTAIN. Uncertain != VIOLATED so overall is PASS.",
    ),

    # ------------------------------------------------------------------ K: MIXED

    BenchmarkCase(
        case_id="K1",
        description="Mixed: no max() + handle empty gracefully. Code USES max() → FAIL",
        category="MIXED",
        conversation=[
            {"turn": 1, "text": "Do not use max()."},
            {"turn": 2, "text": "Handle an empty list gracefully."},
        ],
        code="""\
def find_max(lst):
    if not lst:
        return None
    return max(lst)
""",
        expected_active_types=["no_builtin", "error_handling"],
        expected_violated_types=["no_builtin"],
        expected_satisfied_types=["error_handling"],
        expected_overall="FAIL",
        notes="max() is violated even though empty handling is correct.",
    ),

    BenchmarkCase(
        case_id="K2",
        description="Mixed: no sorted() + correct naming. Both SATISFIED → PASS",
        category="MIXED",
        conversation=[
            {"turn": 1, "text": "Do not use sorted()."},
            {"turn": 2, "text": "Name the function my_sort."},
        ],
        code="""\
def my_sort(lst):
    n = len(lst)
    for i in range(n):
        for j in range(0, n - i - 1):
            if lst[j] > lst[j + 1]:
                lst[j], lst[j + 1] = lst[j + 1], lst[j]
    return lst
""",
        expected_active_types=["no_builtin", "naming"],
        expected_satisfied_types=["no_builtin", "naming"],
        expected_overall="PASS",
    ),

    BenchmarkCase(
        case_id="K3",
        description="Mixed: superseded recursion + no max(). No max, iterative → PASS",
        category="MIXED",
        conversation=[
            {"turn": 1, "text": "Use recursion."},
            {"turn": 2, "text": "Do not use recursion."},
            {"turn": 3, "text": "Do not use max()."},
        ],
        code="""\
def find_max(lst):
    if not lst:
        return None
    best = lst[0]
    for x in lst[1:]:
        if x > best:
            best = x
    return best
""",
        expected_active_types=["algorithm", "no_builtin"],
        expected_superseded_types=["algorithm"],
        expected_satisfied_types=["algorithm", "no_builtin"],
        expected_overall="PASS",
        notes="Use-recursion superseded. Active: no-recursion + no-max. Both satisfied by iterative code.",
    ),
]


def load_cases() -> list[BenchmarkCase]:
    """Return all benchmark cases. Deterministic order."""
    return list(CONSTRAINT_BENCH_SMALL)


def get_case(case_id: str) -> BenchmarkCase:
    """Return a specific case by ID."""
    for case in CONSTRAINT_BENCH_SMALL:
        if case.case_id == case_id:
            return case
    raise KeyError(f"Case '{case_id}' not found in ConstraintBench-Small.")
