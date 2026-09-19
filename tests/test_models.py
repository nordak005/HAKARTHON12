"""
tests/test_models.py
====================
Tests for constraint_guard.models — enums, model creation,
serialization, default values, and validators.
"""

import json
import sys
import os
import pytest
from pydantic import ValidationError

# Make sure the Project directory is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from constraint_guard.models import (
    ConstraintStatus,
    ConstraintType,
    ConstraintEdgeType,
    Constraint,
    ConstraintEdge,
    Evidence,
    VerificationResult,
    VerificationReport,
)


# ===========================================================================
# Enum tests
# ===========================================================================

class TestConstraintStatus:
    def test_all_values_present(self):
        values = {s.value for s in ConstraintStatus}
        assert values == {"active", "superseded", "conflicting", "violated", "satisfied"}

    def test_string_comparison(self):
        assert ConstraintStatus.ACTIVE == "active"
        assert ConstraintStatus.VIOLATED == "violated"

    def test_membership(self):
        assert "superseded" in ConstraintStatus._value2member_map_


class TestConstraintType:
    def test_all_values_present(self):
        expected = {
            "no_builtin", "algorithm", "signature", "structure",
            "error_handling", "naming", "complexity", "general",
        }
        assert {t.value for t in ConstraintType} == expected

    def test_string_comparison(self):
        assert ConstraintType.NO_BUILTIN == "no_builtin"
        assert ConstraintType.GENERAL == "general"


class TestConstraintEdgeType:
    def test_all_values_present(self):
        expected = {"supersedes", "conflicts", "reinforces", "depends_on"}
        assert {e.value for e in ConstraintEdgeType} == expected


# ===========================================================================
# Constraint model tests
# ===========================================================================

class TestConstraint:
    def _make(self, **kwargs) -> Constraint:
        defaults = dict(text="Do not use max()", source_turn=1)
        defaults.update(kwargs)
        return Constraint(**defaults)

    def test_basic_creation(self):
        c = self._make()
        assert c.text == "Do not use max()"
        assert c.source_turn == 1
        assert c.status == ConstraintStatus.ACTIVE
        assert c.type == ConstraintType.GENERAL
        assert c.confidence == 1.0
        assert isinstance(c.id, str) and len(c.id) > 0
        assert c.evidence == []
        assert c.metadata == {}
        assert c.target is None

    def test_auto_id_unique(self):
        c1 = self._make()
        c2 = self._make()
        assert c1.id != c2.id

    def test_explicit_id(self):
        c = self._make(id="my-custom-id")
        assert c.id == "my-custom-id"

    def test_all_fields(self):
        c = Constraint(
            id="c1",
            text="Use recursion",
            type=ConstraintType.ALGORITHM,
            source_turn=2,
            status=ConstraintStatus.SUPERSEDED,
            target="recursion",
            confidence=0.85,
            evidence=["keyword 'recursion' found"],
            metadata={"extractor": "regex"},
        )
        assert c.type == ConstraintType.ALGORITHM
        assert c.status == ConstraintStatus.SUPERSEDED
        assert c.target == "recursion"
        assert c.confidence == pytest.approx(0.85, abs=1e-5)
        assert c.evidence == ["keyword 'recursion' found"]
        assert c.metadata == {"extractor": "regex"}

    def test_confidence_boundary_values(self):
        c0 = self._make(confidence=0.0)
        c1 = self._make(confidence=1.0)
        assert c0.confidence == 0.0
        assert c1.confidence == 1.0

    def test_confidence_invalid_high(self):
        with pytest.raises(ValidationError) as exc_info:
            self._make(confidence=1.001)
        assert "confidence" in str(exc_info.value).lower()

    def test_confidence_invalid_low(self):
        with pytest.raises(ValidationError) as exc_info:
            self._make(confidence=-0.1)
        assert "confidence" in str(exc_info.value).lower()

    def test_source_turn_must_be_positive(self):
        with pytest.raises(ValidationError):
            self._make(source_turn=0)

    def test_text_cannot_be_empty(self):
        with pytest.raises(ValidationError):
            self._make(text="")

    def test_serialization_roundtrip(self):
        c = self._make(
            id="test-id",
            type=ConstraintType.NO_BUILTIN,
            target="max",
            confidence=0.9,
        )
        data = c.model_dump()
        c2 = Constraint(**data)
        assert c2.id == c.id
        assert c2.type == c.type
        assert c2.confidence == pytest.approx(c.confidence, abs=1e-5)

    def test_json_serialization(self):
        c = self._make(id="json-test")
        json_str = c.model_dump_json()
        data = json.loads(json_str)
        assert data["id"] == "json-test"
        assert data["status"] == "active"

    def test_invalid_type_enum(self):
        with pytest.raises(ValidationError):
            self._make(type="not_a_valid_type")

    def test_invalid_status_enum(self):
        with pytest.raises(ValidationError):
            self._make(status="unknown_status")


# ===========================================================================
# ConstraintEdge model tests
# ===========================================================================

class TestConstraintEdge:
    def _make(self, **kwargs) -> ConstraintEdge:
        defaults = dict(
            source_id="c2",
            target_id="c1",
            edge_type=ConstraintEdgeType.SUPERSEDES,
        )
        defaults.update(kwargs)
        return ConstraintEdge(**defaults)

    def test_basic_creation(self):
        e = self._make()
        assert e.source_id == "c2"
        assert e.target_id == "c1"
        assert e.edge_type == ConstraintEdgeType.SUPERSEDES
        assert e.confidence == 1.0
        assert e.reason == ""

    def test_all_edge_types(self):
        for et in ConstraintEdgeType:
            e = self._make(edge_type=et)
            assert e.edge_type == et

    def test_self_loop_rejected(self):
        with pytest.raises(ValidationError):
            self._make(source_id="same", target_id="same")

    def test_confidence_invalid(self):
        with pytest.raises(ValidationError):
            self._make(confidence=1.5)

    def test_reason_stored(self):
        e = self._make(reason="Turn 2 negates turn 1 recursion requirement")
        assert "recursion" in e.reason

    def test_serialization_roundtrip(self):
        e = self._make(confidence=0.75, reason="semantic similarity 0.95")
        data = e.model_dump()
        e2 = ConstraintEdge(**data)
        assert e2.edge_type == e.edge_type
        assert e2.confidence == pytest.approx(e.confidence, abs=1e-5)


# ===========================================================================
# Evidence model tests
# ===========================================================================

class TestEvidence:
    def _make(self, **kwargs) -> Evidence:
        defaults = dict(
            constraint_id="c1",
            verifier="lexical",
            passed=False,
        )
        defaults.update(kwargs)
        return Evidence(**defaults)

    def test_basic_creation(self):
        ev = self._make()
        assert ev.constraint_id == "c1"
        assert ev.verifier == "lexical"
        assert ev.passed is False
        assert ev.confidence == 1.0
        assert ev.message == ""
        assert ev.line_number is None
        assert ev.code_snippet is None
        assert ev.metadata == {}

    def test_with_line_number(self):
        ev = self._make(line_number=5, code_snippet="return max(lst)")
        assert ev.line_number == 5
        assert ev.code_snippet == "return max(lst)"

    def test_line_number_zero_rejected(self):
        with pytest.raises(ValidationError):
            self._make(line_number=0)

    def test_line_number_negative_rejected(self):
        with pytest.raises(ValidationError):
            self._make(line_number=-1)

    def test_confidence_invalid(self):
        with pytest.raises(ValidationError):
            self._make(confidence=2.0)

    def test_verifier_cannot_be_empty(self):
        with pytest.raises(ValidationError):
            self._make(verifier="")

    def test_passed_true(self):
        ev = self._make(passed=True, message="No banned builtin found")
        assert ev.passed is True
        assert "builtin" in ev.message

    def test_metadata_stored(self):
        ev = self._make(metadata={"token": "max", "ast_node": "Call"})
        assert ev.metadata["token"] == "max"

    def test_serialization_roundtrip(self):
        ev = self._make(passed=False, confidence=0.8, line_number=3)
        data = ev.model_dump()
        ev2 = Evidence(**data)
        assert ev2.passed == ev.passed
        assert ev2.line_number == ev.line_number

    def test_all_three_verifier_lanes(self):
        for lane in ("lexical", "structural", "behavioral"):
            ev = self._make(verifier=lane, passed=True)
            assert ev.verifier == lane


# ===========================================================================
# VerificationResult model tests
# ===========================================================================

class TestVerificationResult:
    def _make_evidence(self, passed: bool, verifier: str = "lexical") -> Evidence:
        return Evidence(
            constraint_id="c1",
            verifier=verifier,
            passed=passed,
            confidence=0.9,
        )

    def test_basic_creation(self):
        vr = VerificationResult(
            constraint_id="c1",
            status=ConstraintStatus.VIOLATED,
            final_pass=False,
            confidence=0.9,
        )
        assert vr.constraint_id == "c1"
        assert vr.status == ConstraintStatus.VIOLATED
        assert vr.final_pass is False
        assert vr.evidences == []

    def test_with_evidences(self):
        ev1 = self._make_evidence(False, "lexical")
        ev2 = self._make_evidence(False, "structural")
        vr = VerificationResult(
            constraint_id="c1",
            status=ConstraintStatus.VIOLATED,
            evidences=[ev1, ev2],
            final_pass=False,
            confidence=0.85,
        )
        assert len(vr.evidences) == 2

    def test_confidence_invalid(self):
        with pytest.raises(ValidationError):
            VerificationResult(
                constraint_id="c1",
                status=ConstraintStatus.ACTIVE,
                final_pass=True,
                confidence=-0.1,
            )

    def test_serialization_roundtrip(self):
        ev = self._make_evidence(True, "structural")
        vr = VerificationResult(
            constraint_id="c1",
            status=ConstraintStatus.SATISFIED,
            evidences=[ev],
            final_pass=True,
            confidence=0.95,
        )
        data = vr.model_dump()
        vr2 = VerificationResult(**data)
        assert vr2.status == vr.status
        assert len(vr2.evidences) == 1


# ===========================================================================
# VerificationReport model tests
# ===========================================================================

class TestVerificationReport:
    def _make_constraint(self, status: ConstraintStatus, turn: int = 1) -> Constraint:
        return Constraint(text="dummy constraint", source_turn=turn, status=status)

    def _make_result(self, c: Constraint, passed: bool) -> VerificationResult:
        status = ConstraintStatus.SATISFIED if passed else ConstraintStatus.VIOLATED
        return VerificationResult(
            constraint_id=c.id,
            status=status,
            final_pass=passed,
            confidence=0.9,
        )

    def test_empty_report(self):
        report = VerificationReport()
        assert report.total_constraints == 0
        assert report.overall_status == "PASS"
        assert report.results == []

    def test_from_results_all_satisfied(self):
        c1 = self._make_constraint(ConstraintStatus.ACTIVE, turn=1)
        c2 = self._make_constraint(ConstraintStatus.ACTIVE, turn=2)
        r1 = self._make_result(c1, passed=True)
        r2 = self._make_result(c2, passed=True)

        report = VerificationReport.from_results([c1, c2], [r1, r2])
        assert report.total_constraints == 2
        assert report.satisfied_constraints == 2
        assert report.violated_constraints == 0
        assert report.overall_status == "PASS"

    def test_from_results_with_violation(self):
        c1 = self._make_constraint(ConstraintStatus.ACTIVE, turn=1)
        r1 = self._make_result(c1, passed=False)

        report = VerificationReport.from_results([c1], [r1])
        assert report.violated_constraints == 1
        assert report.satisfied_constraints == 0
        assert report.overall_status == "FAIL"

    def test_from_results_with_superseded(self):
        c1 = self._make_constraint(ConstraintStatus.SUPERSEDED, turn=1)
        c2 = self._make_constraint(ConstraintStatus.ACTIVE, turn=2)
        r2 = self._make_result(c2, passed=True)

        report = VerificationReport.from_results([c1, c2], [r2])
        assert report.total_constraints == 2
        assert report.superseded_constraints == 1
        assert report.overall_status == "PASS"

    def test_overall_status_driven_by_results(self):
        # Explicitly set violated but no results → derive from results list
        c1 = self._make_constraint(ConstraintStatus.ACTIVE)
        r1 = self._make_result(c1, passed=False)
        report = VerificationReport.from_results([c1], [r1])
        assert report.overall_status == "FAIL"

    def test_json_serialization(self):
        report = VerificationReport()
        json_str = report.model_dump_json()
        data = json.loads(json_str)
        assert data["overall_status"] == "PASS"
        assert data["results"] == []

    def test_from_results_mixed(self):
        active1  = self._make_constraint(ConstraintStatus.ACTIVE, turn=1)
        active2  = self._make_constraint(ConstraintStatus.ACTIVE, turn=2)
        super1   = self._make_constraint(ConstraintStatus.SUPERSEDED, turn=1)
        conflict1 = self._make_constraint(ConstraintStatus.CONFLICTING, turn=3)

        r1 = self._make_result(active1, passed=True)
        r2 = self._make_result(active2, passed=False)

        report = VerificationReport.from_results(
            [active1, active2, super1, conflict1], [r1, r2]
        )
        assert report.total_constraints == 4
        assert report.superseded_constraints == 1
        assert report.conflicting_constraints == 1
        assert report.violated_constraints == 1
        assert report.satisfied_constraints == 1
        assert report.overall_status == "FAIL"
