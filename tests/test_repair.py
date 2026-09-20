"""
tests/test_repair.py
====================
Unit tests for the repair engine (repairer.py).
"""

from constraint_guard.llm.provider import DeterministicMockProvider
from constraint_guard.models import ConstraintStatus, Evidence, VerificationReport, VerificationResult
from constraint_guard.repair.repairer import repair_code


class TestRepairer:
    def test_repair_code_when_no_violations(self):
        report = VerificationReport(
            overall_status="PASS",
            results=[
                VerificationResult(
                    constraint_id="C1",
                    status=ConstraintStatus.SATISFIED,
                    evidences=[Evidence(constraint_id="C1", verifier="lexical", passed=True, message="OK")],
                    final_pass=True,
                )
            ],
        )

        code = "def foo(): pass"
        repaired = repair_code(
            conversation=[{"turn": 1, "text": "test"}],
            code=code,
            verification_report=report,
        )
        assert repaired == code

    def test_repair_code_invokes_provider_when_violated(self):
        report = VerificationReport(
            overall_status="FAIL",
            results=[
                VerificationResult(
                    constraint_id="C1",
                    status=ConstraintStatus.VIOLATED,
                    evidences=[Evidence(constraint_id="C1", verifier="lexical", passed=False, message="max() banned", line_number=4)],
                    final_pass=False,
                )
            ],
        )

        mock_provider = DeterministicMockProvider(
            default_response="def find_max(lst):\n    return lst[0]"
        )

        repaired = repair_code(
            conversation=[{"turn": 1, "text": "Do not use max()"}],
            code="def find_max(lst):\n    return max(lst)",
            verification_report=report,
            provider=mock_provider,
        )

        assert "return max" not in repaired
        assert "return lst[0]" in repaired
