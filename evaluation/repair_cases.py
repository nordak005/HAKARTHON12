"""
evaluation/repair_cases.py
==========================
Reproducible repair benchmark cases for ConstraintGuard.
Contains multi-turn scenarios with initial code that intentionally violates active constraints,
along with expected repaired implementations for deterministic offline evaluation.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class RepairBenchmarkCase:
    id: str
    name: str
    conversation: List[Dict[str, Any]]
    initial_code: str
    repaired_code: str
    expected_initial_status: str = "FAIL"
    expected_repaired_status: str = "PASS"
    violated_constraint_types: List[str] = field(default_factory=list)


REPAIR_BENCHMARK_CASES: List[RepairBenchmarkCase] = [
    RepairBenchmarkCase(
        id="R1_NO_BUILTIN",
        name="Repair prohibited max() built-in usage",
        conversation=[
            {"turn": 1, "text": "Write a function that finds the maximum value in a list. Do not use max()."},
            {"turn": 2, "text": "Also handle an empty list gracefully by returning None."},
        ],
        initial_code="""\
def find_max(lst):
    if not lst:
        return None
    return max(lst)
""",
        repaired_code="""\
def find_max(lst):
    if not lst:
        return None
    curr = lst[0]
    for x in lst[1:]:
        if x > curr:
            curr = x
    return curr
""",
        violated_constraint_types=["NO_BUILTIN"],
    ),
    RepairBenchmarkCase(
        id="R2_RECURSION",
        name="Repair superseded recursion constraint violation",
        conversation=[
            {"turn": 1, "text": "Use recursion to compute factorial."},
            {"turn": 2, "text": "Do not use recursion. Write an iterative solution instead."},
        ],
        initial_code="""\
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)
""",
        repaired_code="""\
def factorial(n):
    res = 1
    for i in range(1, n + 1):
        res *= i
    return res
""",
        violated_constraint_types=["ALGORITHM"],
    ),
    RepairBenchmarkCase(
        id="R3_NAMING",
        name="Repair function name mismatch",
        conversation=[
            {"turn": 1, "text": "Write a function to compute square root."},
            {"turn": 2, "text": "Name it calculate_square_root."},
        ],
        initial_code="""\
def get_sqrt(x):
    return x ** 0.5
""",
        repaired_code="""\
def calculate_square_root(x):
    return x ** 0.5
""",
        violated_constraint_types=["NAMING"],
    ),
    RepairBenchmarkCase(
        id="R4_STRUCTURE",
        name="Repair missing class wrapper constraint",
        conversation=[
            {"turn": 1, "text": "Write a math helper utility."},
            {"turn": 2, "text": "Use a class to encapsulate the functionality."},
        ],
        initial_code="""\
def add(a, b):
    return a + b
""",
        repaired_code="""\
class MathHelper:
    @staticmethod
    def add(a, b):
        return a + b
""",
        violated_constraint_types=["STRUCTURE"],
    ),
    RepairBenchmarkCase(
        id="R5_MULTI_VIOLATION",
        name="Repair combined max() ban and function naming violation",
        conversation=[
            {"turn": 1, "text": "Write a function to find peak element. Name it find_peak. Do not use max()."},
        ],
        initial_code="""\
def get_peak(lst):
    return max(lst)
""",
        repaired_code="""\
def find_peak(lst):
    if not lst:
        return None
    res = lst[0]
    for val in lst:
        if val > res:
            res = val
    return res
""",
        violated_constraint_types=["NO_BUILTIN", "NAMING"],
    ),
]


def load_repair_cases() -> List[RepairBenchmarkCase]:
    """Return all repair benchmark cases."""
    return REPAIR_BENCHMARK_CASES
