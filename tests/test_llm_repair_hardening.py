"""
tests/test_llm_repair_hardening.py
===================================
Unit tests for closed-loop repair verification, regression protection during
re-verification, model payload binding, and iteration limits.
"""

import json
from unittest.mock import MagicMock, patch
import pytest

from constraint_guard.llm.provider import (
    DeterministicMockProvider,
    OpenAICompatibleProvider,
)
from constraint_guard.models import (
    Constraint,
    ConstraintStatus,
    ConstraintType,
    VerificationReport,
)

from constraint_guard.repair.loop import RepairHistory, run_repair_loop
from constraint_guard.repair.repairer import repair_code
from constraint_guard.verifier.engine import VerificationEngine


class TestRepairFlowHardening:
    def test_no_repair_when_no_violation(self):
        conv = [{"turn": 1, "text": "Write a function find_max(lst). Do not use max()."}]
        already_valid_code = """\
def find_max(lst):
    if not lst:
        return None
    curr = lst[0]
    for x in lst[1:]:
        if x > curr:
            curr = x
    return curr
"""
        provider = DeterministicMockProvider()
        history = run_repair_loop(
            conversation=conv,
            initial_code=already_valid_code,
            max_iterations=2,
            provider=provider,
        )

        assert history.success is True
        assert history.iterations_used == 0
        assert len(history.attempts) == 0
        assert history.final_report.overall_status == "PASS"

    def test_repair_success_flow(self):
        conv = [{"turn": 1, "text": "Write a function find_max(lst). Do not use max()."}]
        initial_bad_code = "def find_max(lst):\n    return max(lst)"

        provider = DeterministicMockProvider(
            response_map={
                "do not use max": """\
def find_max(lst):
    if not lst:
        return None
    curr = lst[0]
    for x in lst[1:]:
        if x > curr:
            curr = x
    return curr
"""
            }
        )

        history = run_repair_loop(
            conversation=conv,
            initial_code=initial_bad_code,
            max_iterations=2,
            provider=provider,
        )

        assert history.initial_report.overall_status == "FAIL"
        assert history.iterations_used == 1
        assert history.success is True
        assert history.final_report.overall_status == "PASS"

    def test_repair_failure_and_max_iteration_enforcement(self):
        """When repair candidate continues to violate constraint, loop stops at max_iterations=2."""
        conv = [{"turn": 1, "text": "Write a function find_max(lst). Do not use max()."}]
        initial_bad_code = "def find_max(lst):\n    return max(lst)"

        # Provider that repeatedly returns violating code
        provider = DeterministicMockProvider(
            default_response="def find_max(lst):\n    return max(lst)"
        )

        history = run_repair_loop(
            conversation=conv,
            initial_code=initial_bad_code,
            max_iterations=2,
            provider=provider,
        )

        assert history.initial_report.overall_status == "FAIL"
        assert history.iterations_used == 2
        assert len(history.attempts) == 2
        assert history.success is False
        assert history.final_report.overall_status == "FAIL"

    def test_repair_regression_protection(self):
        """Repair fixes C1 (no max) but breaks C2 (recursion required). Engine detects C2 failure."""
        c1 = Constraint(
            text="Do not use max()",
            type=ConstraintType.NO_BUILTIN,
            target="max",
            source_turn=1,
            status=ConstraintStatus.ACTIVE,
        )
        c2 = Constraint(
            text="Use recursion to compute factorial",
            type=ConstraintType.ALGORITHM,
            target="recursion",
            source_turn=2,
            status=ConstraintStatus.ACTIVE,
        )
        all_constraints = [c1, c2]

        # Initial code satisfies C2 (uses recursion) BUT violates C1 (uses max)
        initial_code = "def factorial(n):\n    if n <= 1:\n        return 1\n    return max([n]) * factorial(n - 1)"

        engine = VerificationEngine()
        initial_report = engine.verify(initial_code, all_constraints)
        assert initial_report.overall_status == "FAIL"

        # Provider proposes repair candidate that removes max() BUT removes recursion (breaks C2)
        regressed_repaired_code = "def factorial(n):\n    return n"

        # Re-verify ALL active constraints against repaired candidate
        # Reset statuses to ACTIVE first
        c1.status = ConstraintStatus.ACTIVE
        c2.status = ConstraintStatus.ACTIVE
        re_report = engine.verify(regressed_repaired_code, all_constraints)

        # C1 is satisfied (no max), C2 is VIOLATED (no recursion) -> overall status MUST BE FAIL!
        assert re_report.overall_status == "FAIL"
        c1_res = next(r for r in re_report.results if r.constraint_id == c1.id)
        c2_res = next(r for r in re_report.results if r.constraint_id == c2.id)

        assert c1_res.status == ConstraintStatus.SATISFIED
        assert c2_res.status == ConstraintStatus.VIOLATED


    def test_selected_model_used_for_repair_payload(self):
        provider = OpenAICompatibleProvider(
            api_key="sk-test-key",
            model="openai/gpt-oss-20b",
        )
        captured_payloads = []

        def mock_urlopen(req, timeout=30):
            payload = json.loads(req.data.decode("utf-8"))
            captured_payloads.append(payload)
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(
                {"choices": [{"message": {"content": "def repaired(): pass"}}]}
            ).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            return mock_resp

        mock_report = MagicMock(spec=VerificationReport)
        mock_result = MagicMock()
        mock_result.status = ConstraintStatus.VIOLATED
        mock_report.results = [mock_result]

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            repair_code(
                conversation=[{"turn": 1, "text": "Do not use max()."}],
                code="def find_max(x): return max(x)",
                verification_report=mock_report,
                provider=provider,
            )

            assert len(captured_payloads) == 1
            assert captured_payloads[0]["model"] == "openai/gpt-oss-20b"
