"""
tests/test_graph.py
===================
Tests for constraint_guard.graph — VersionedConstraintGraph.
Includes unit tests and one end-to-end test as specified.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from constraint_guard.graph import VersionedConstraintGraph
from constraint_guard.models import (
    Constraint,
    ConstraintEdgeType,
    ConstraintStatus,
    ConstraintType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _c(text: str, turn: int, ctype=ConstraintType.GENERAL, target=None, **kw) -> Constraint:
    return Constraint(text=text, source_turn=turn, type=ctype, target=target, **kw)


# ---------------------------------------------------------------------------
# add_constraint / get_constraint
# ---------------------------------------------------------------------------

class TestAddConstraint:
    def test_add_single_constraint(self):
        vcg = VersionedConstraintGraph()
        c = _c("Do not use max()", turn=1)
        vcg.add_constraint(c)
        assert vcg.node_count() == 1

    def test_retrieve_by_id(self):
        vcg = VersionedConstraintGraph()
        c = _c("Do not use max()", turn=1, id="my-id")
        vcg.add_constraint(c)
        retrieved = vcg.get_constraint("my-id")
        assert retrieved is not None
        assert retrieved.id == "my-id"

    def test_unknown_id_returns_none(self):
        vcg = VersionedConstraintGraph()
        assert vcg.get_constraint("nonexistent") is None

    def test_add_multiple_constraints(self):
        vcg = VersionedConstraintGraph()
        for i in range(5):
            vcg.add_constraint(_c(f"Constraint {i}", turn=i + 1))
        assert vcg.node_count() == 5


# ---------------------------------------------------------------------------
# get_active / superseded / conflicting
# ---------------------------------------------------------------------------

class TestStatusQueries:
    def test_new_constraints_are_active(self):
        vcg = VersionedConstraintGraph()
        c1 = _c("Use recursion", turn=1)
        c2 = _c("Handle empty list", turn=2)
        vcg.add_constraint(c1)
        vcg.add_constraint(c2)
        active = vcg.get_active_constraints()
        assert len(active) == 2

    def test_superseded_constraint_excluded_from_active(self):
        vcg = VersionedConstraintGraph()
        c1 = _c("Use recursion", turn=1)
        c2 = _c("Do not use recursion", turn=2)
        vcg.add_constraint(c1)
        vcg.add_constraint(c2)
        vcg.add_edge(c2.id, c1.id, ConstraintEdgeType.SUPERSEDES,
                     reason="negation")
        active = vcg.get_active_constraints()
        assert c2 in active
        assert c1 not in active

    def test_superseded_constraint_still_in_graph(self):
        vcg = VersionedConstraintGraph()
        c1 = _c("Use recursion", turn=1)
        c2 = _c("Do not use recursion", turn=2)
        vcg.add_constraint(c1)
        vcg.add_constraint(c2)
        vcg.add_edge(c2.id, c1.id, ConstraintEdgeType.SUPERSEDES)
        superseded = vcg.get_superseded_constraints()
        assert c1 in superseded

    def test_conflicting_constraints(self):
        vcg = VersionedConstraintGraph()
        c1 = _c("Return None for empty", turn=1, ctype=ConstraintType.ERROR_HANDLING)
        c2 = _c("Raise ValueError for empty", turn=2, ctype=ConstraintType.ERROR_HANDLING)
        vcg.add_constraint(c1)
        vcg.add_constraint(c2)
        # Add bidirectional conflict edges
        vcg.add_edge(c1.id, c2.id, ConstraintEdgeType.CONFLICTS)
        vcg.add_edge(c2.id, c1.id, ConstraintEdgeType.CONFLICTS)
        conflicting = vcg.get_conflicting_constraints()
        assert c1 in conflicting
        assert c2 in conflicting
        assert len(vcg.get_active_constraints()) == 0


# ---------------------------------------------------------------------------
# add_edge / get_edges_for_constraint
# ---------------------------------------------------------------------------

class TestEdges:
    def test_add_supersedes_edge(self):
        vcg = VersionedConstraintGraph()
        c1 = _c("Use recursion", turn=1)
        c2 = _c("Do not use recursion", turn=2)
        vcg.add_constraint(c1)
        vcg.add_constraint(c2)
        edge = vcg.add_edge(c2.id, c1.id, ConstraintEdgeType.SUPERSEDES,
                             confidence=0.95, reason="test")
        assert edge.edge_type == ConstraintEdgeType.SUPERSEDES
        assert edge.confidence == pytest.approx(0.95, abs=1e-5)
        assert vcg.edge_count() == 1

    def test_add_reinforces_edge(self):
        vcg = VersionedConstraintGraph()
        c1 = _c("Do not use max()", turn=1)
        c2 = _c("Keep the previous restriction", turn=2)
        vcg.add_constraint(c1)
        vcg.add_constraint(c2)
        vcg.add_edge(c2.id, c1.id, ConstraintEdgeType.REINFORCES, reason="continuation")
        edges = vcg.get_edges_for_constraint(c1.id)
        assert any(e.edge_type == ConstraintEdgeType.REINFORCES for e in edges)

    def test_get_edges_for_constraint_includes_both_directions(self):
        vcg = VersionedConstraintGraph()
        c1 = _c("Use recursion", turn=1)
        c2 = _c("Do not use recursion", turn=2)
        vcg.add_constraint(c1)
        vcg.add_constraint(c2)
        vcg.add_edge(c2.id, c1.id, ConstraintEdgeType.SUPERSEDES)
        # c1 is the target — incoming edge should appear in its edge list
        edges_for_c1 = vcg.get_edges_for_constraint(c1.id)
        assert len(edges_for_c1) == 1
        assert edges_for_c1[0].target_id == c1.id

    def test_supersedes_edge_marks_target_as_superseded(self):
        vcg = VersionedConstraintGraph()
        c1 = _c("Use recursion", turn=1)
        c2 = _c("Do not use recursion", turn=2)
        vcg.add_constraint(c1)
        vcg.add_constraint(c2)
        vcg.add_edge(c2.id, c1.id, ConstraintEdgeType.SUPERSEDES)
        assert vcg.get_constraint(c1.id).status == ConstraintStatus.SUPERSEDED
        assert vcg.get_constraint(c2.id).status == ConstraintStatus.ACTIVE

    def test_conflicts_edge_marks_both_as_conflicting(self):
        vcg = VersionedConstraintGraph()
        c1 = _c("Return None for empty", turn=1, ctype=ConstraintType.ERROR_HANDLING)
        c2 = _c("Raise ValueError for empty", turn=2, ctype=ConstraintType.ERROR_HANDLING)
        vcg.add_constraint(c1)
        vcg.add_constraint(c2)
        vcg.add_edge(c1.id, c2.id, ConstraintEdgeType.CONFLICTS)
        vcg.add_edge(c2.id, c1.id, ConstraintEdgeType.CONFLICTS)
        assert vcg.get_constraint(c1.id).status == ConstraintStatus.CONFLICTING
        assert vcg.get_constraint(c2.id).status == ConstraintStatus.CONFLICTING


# ---------------------------------------------------------------------------
# build_from_constraints (auto-resolve)
# ---------------------------------------------------------------------------

class TestBuildFromConstraints:
    def test_build_two_active_unrelated_constraints(self):
        c1 = _c("Do not use max()", turn=1, ctype=ConstraintType.NO_BUILTIN, target="max")
        c2 = _c("Handle empty list", turn=2, ctype=ConstraintType.ERROR_HANDLING)
        vcg = VersionedConstraintGraph.build_from_constraints([c1, c2])
        assert vcg.node_count() == 2
        assert len(vcg.get_active_constraints()) == 2
        assert vcg.edge_count() == 0

    def test_supersession_auto_detected_same_type_and_target(self):
        # Both are NO_BUILTIN for "max"; later one supersedes earlier
        c1 = _c("Do not use max()", turn=1, ctype=ConstraintType.NO_BUILTIN, target="max")
        c2 = _c("You can use max() now", turn=2, ctype=ConstraintType.NO_BUILTIN, target="max")
        vcg = VersionedConstraintGraph.build_from_constraints([c1, c2])
        assert c1.status == ConstraintStatus.SUPERSEDED
        assert c2.status == ConstraintStatus.ACTIVE
        # SUPERSEDES edge exists c2 → c1
        edges = vcg.get_edges_for_constraint(c1.id)
        assert any(e.edge_type == ConstraintEdgeType.SUPERSEDES for e in edges)

    def test_algorithm_supersession_recursion_to_no_recursion(self):
        c1 = _c("Use recursion", turn=1, ctype=ConstraintType.ALGORITHM)
        c2 = _c("Do not use recursion", turn=2, ctype=ConstraintType.ALGORITHM)
        vcg = VersionedConstraintGraph.build_from_constraints([c1, c2])
        assert c1.status == ConstraintStatus.SUPERSEDED
        assert c2.status == ConstraintStatus.ACTIVE

    def test_conflict_auto_detected_for_contradictory_active_constraints(self):
        # Two error-handling constraints that cannot both be true
        c1 = _c("Return None for empty", turn=1, ctype=ConstraintType.ERROR_HANDLING)
        c2 = _c("Raise ValueError for empty input", turn=2,
                 ctype=ConstraintType.ERROR_HANDLING)
        vcg = VersionedConstraintGraph.build_from_constraints([c1, c2])
        conflicting = vcg.get_conflicting_constraints()
        assert len(conflicting) == 2

    def test_no_auto_resolve(self):
        c1 = _c("Use recursion", turn=1, ctype=ConstraintType.ALGORITHM)
        c2 = _c("Do not use recursion", turn=2, ctype=ConstraintType.ALGORITHM)
        vcg = VersionedConstraintGraph.build_from_constraints([c1, c2], auto_resolve=False)
        # No edges added, both still ACTIVE
        assert vcg.edge_count() == 0
        assert len(vcg.get_active_constraints()) == 2

    def test_historical_constraints_preserved_after_supersession(self):
        c1 = _c("Use recursion", turn=1, ctype=ConstraintType.ALGORITHM)
        c2 = _c("Do not use recursion", turn=2, ctype=ConstraintType.ALGORITHM)
        vcg = VersionedConstraintGraph.build_from_constraints([c1, c2])
        # c1 is superseded but still in graph
        assert vcg.get_constraint(c1.id) is not None
        assert vcg.node_count() == 2


# ---------------------------------------------------------------------------
# End-to-End: "Use recursion" → "Do not use recursion"
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def test_recursion_supersession_full_pipeline(self):
        """
        Turn 1: "Use recursion."
        Turn 2: "Do not use recursion."

        Expected:
        - 2 constraints in the graph
        - 1 SUPERSEDES edge (c2 → c1)
        - c1 status == SUPERSEDED
        - c2 status == ACTIVE
        - get_active_constraints() returns only [c2]
        - get_superseded_constraints() returns only [c1]
        """
        from constraint_guard.extractor import extract

        conversation = [
            {"turn": 1, "text": "Use recursion."},
            {"turn": 2, "text": "Do not use recursion."},
        ]

        result = extract(conversation)
        assert len(result.constraints) == 2, (
            f"Expected 2 constraints, got {len(result.constraints)}: "
            f"{[c.text for c in result.constraints]}"
        )

        vcg = VersionedConstraintGraph.build_from_constraints(result.constraints)

        # Node count
        assert vcg.node_count() == 2

        # Active / Superseded partition
        active = vcg.get_active_constraints()
        superseded = vcg.get_superseded_constraints()
        assert len(active) == 1, f"Expected 1 active, got {len(active)}: {[c.text for c in active]}"
        assert len(superseded) == 1

        # The ACTIVE one should be the "do not use recursion" turn
        assert "not" in active[0].text.lower() or "don" in active[0].text.lower()

        # SUPERSEDES edge
        edges_on_superseded = vcg.get_edges_for_constraint(superseded[0].id)
        supersedes_edges = [e for e in edges_on_superseded
                            if e.edge_type == ConstraintEdgeType.SUPERSEDES]
        assert len(supersedes_edges) == 1

        # Turn ordering preserved
        assert superseded[0].source_turn == 1
        assert active[0].source_turn == 2

    def test_conflict_full_pipeline(self):
        """
        Turn 1: "Return None for empty input."
        Turn 2: "Raise ValueError for empty input."

        Expected:
        - 2 constraints, both ERROR_HANDLING
        - bidirectional CONFLICTS edges
        - both status == CONFLICTING
        """
        from constraint_guard.extractor import extract

        conversation = [
            {"turn": 1, "text": "Return None for empty input."},
            {"turn": 2, "text": "Raise ValueError for empty input."},
        ]

        result = extract(conversation)
        assert len(result.constraints) == 2

        vcg = VersionedConstraintGraph.build_from_constraints(result.constraints)
        conflicting = vcg.get_conflicting_constraints()
        assert len(conflicting) == 2
        assert len(vcg.get_active_constraints()) == 0

    def test_continuation_turn_creates_no_extra_constraint(self):
        """
        Turn 1: "Do not use max()."
        Turn 2: "Keep the previous restrictions."

        Expected:
        - continuation_turns = [2]
        - only 1 constraint (from turn 1)
        """
        from constraint_guard.extractor import extract

        conversation = [
            {"turn": 1, "text": "Do not use max()."},
            {"turn": 2, "text": "Keep the previous restrictions."},
        ]

        result = extract(conversation)
        assert 2 in result.continuation_turns
        assert len(result.constraints) == 1
        assert result.constraints[0].source_turn == 1
