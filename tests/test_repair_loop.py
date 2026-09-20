"""
tests/test_repair_loop.py
=========================
Integration tests for the closed-loop repair controller (loop.py).
"""

from constraint_guard.llm.provider import DeterministicMockProvider
from constraint_guard.repair.loop import run_repair_loop


class TestRepairLoop:
    def test_no_repair_needed_if_code_passes(self):
        conv = [
            {"turn": 1, "text": "Write a function named calculate_sum."},
        ]
        passing_code = "def calculate_sum(a, b):\n    return a + b"

        history = run_repair_loop(
            conversation=conv,
            initial_code=passing_code,
            max_iterations=2,
        )

        assert history.success is True
        assert history.iterations_used == 0
        assert len(history.attempts) == 0
        assert history.final_code == passing_code

    def test_successful_repair_in_one_iteration(self):
        conv = [
            {"turn": 1, "text": "Write a function that finds max. Do not use max()."},
            {"turn": 2, "text": "Also handle empty list."},
        ]
        initial_violating_code = """\
def find_max(lst):
    if not lst:
        return None
    return max(lst)
"""
        repaired_compliant_code = """\
def find_max(lst):
    if not lst:
        return None
    curr = lst[0]
    for x in lst[1:]:
        if x > curr:
            curr = x
    return curr
"""
        provider = DeterministicMockProvider(
            response_map={"Do not use max()": repaired_compliant_code}
        )

        history = run_repair_loop(
            conversation=conv,
            initial_code=initial_violating_code,
            max_iterations=2,
            provider=provider,
        )

        assert history.initial_report.overall_status == "FAIL"
        assert history.success is True
        assert history.iterations_used == 1
        assert len(history.attempts) == 1
        assert history.attempts[0].status == "PASS"
        assert history.final_report.overall_status == "PASS"
        assert "return max" not in history.final_code

    def test_loop_terminates_at_max_iterations_if_unresolved(self):
        conv = [
            {"turn": 1, "text": "Do not use max()."},
        ]
        violating_code = "def f(lst): return max(lst)"

        # Provider keeps returning violating code
        stubborn_provider = DeterministicMockProvider(
            default_response="def f(lst): return max(lst)"
        )

        history = run_repair_loop(
            conversation=conv,
            initial_code=violating_code,
            max_iterations=2,
            provider=stubborn_provider,
        )

        assert history.success is False
        assert history.iterations_used == 2
        assert len(history.attempts) == 2
        assert history.attempts[0].status == "FAIL"
        assert history.attempts[1].status == "FAIL"
        assert history.final_report.overall_status == "FAIL"

    def test_active_constraints_preserved_in_repair(self):
        conv = [
            {"turn": 1, "text": "Name the function process_data."},
            {"turn": 2, "text": "Do not use max()."},
        ]
        # Initial code has right name, but uses max()
        initial_code = "def process_data(lst): return max(lst)"
        repaired_code = "def process_data(lst): return sorted(lst)[-1]"

        provider = DeterministicMockProvider(
            default_response=repaired_code
        )

        history = run_repair_loop(
            conversation=conv,
            initial_code=initial_code,
            max_iterations=2,
            provider=provider,
        )

        assert history.success is True
        # Verify function name is still process_data
        assert "def process_data" in history.final_code
