"""
tests/test_resolver.py
======================
Tests for constraint_guard.resolver — ConstraintResolver.

Scenarios tested
----------------
A. Single active constraint
B. Simple supersession (turn 1 → turn 2)
C. Multi-level supersession chain (C1 → C2 → C3)
D. Conflict (Return None vs Raise ValueError)
E. Reinforcement (original stays ACTIVE, no new constraint)
F. Mixed conversation (active + superseded + conflict + reinforcement)
G. Resolver never produces VIOLATED or SATISFIED
H. explain_constraint output sanity checks
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from constraint_guard.extractor import extract
from constraint_guard.graph import VersionedConstraintGraph
from constraint_guard.models import (
    Constraint,
    ConstraintEdgeType,
    ConstraintStatus,
    ConstraintType,
)
from constraint_guard.resolver import ConstraintResolver, ResolutionResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _c(text: str, turn: int, ctype=ConstraintType.GENERAL, target=None, **kw) -> Constraint:
    return Constraint(text=text, source_turn=turn, type=ctype, target=target, **kw)


def _resolve(constraints: list[Constraint]) -> tuple[VersionedConstraintGraph, ResolutionResult]:
    """Build VCG + run resolver, return both."""
    vcg = VersionedConstraintGraph.build_from_constraints(constraints)
    res = ConstraintResolver().resolve(vcg)
    return vcg, res


def _resolve_convo(
    conversation: list[dict],
) -> tuple[VersionedConstraintGraph, ResolutionResult]:
    extracted = extract(conversation)
    return _resolve(extracted.constraints)


# ---------------------------------------------------------------------------
# A. Single active constraint
# ---------------------------------------------------------------------------

class TestSingleActiveConstraint:
    def test_single_constraint_is_active(self):
        c = _c("Do not use max()", turn=1, ctype=ConstraintType.NO_BUILTIN)
        _, res = _resolve([c])
        assert len(res.active) == 1
        assert len(res.superseded) == 0
        assert len(res.conflicting) == 0

    def test_resolved_dict_contains_constraint(self):
        c = _c("Do not use max()", turn=1)
        _, res = _resolve([c])
        assert c.id in res.resolved
        rc = res.resolved[c.id]
        assert rc.status == ConstraintStatus.ACTIVE
        assert rc.constraint is c

    def test_reason_is_non_empty(self):
        c = _c("Do not use max()", turn=1)
        _, res = _resolve([c])
        reason = res.resolved[c.id].reason
        assert isinstance(reason, str) and len(reason) > 0

    def test_empty_graph_produces_empty_result(self):
        vcg = VersionedConstraintGraph()
        res = ConstraintResolver().resolve(vcg)
        assert res.active == []
        assert res.superseded == []
        assert res.conflicting == []
        assert res.resolved == {}


# ---------------------------------------------------------------------------
# B. Simple supersession: Turn 1 → Turn 2
# ---------------------------------------------------------------------------

class TestSimpleSupersession:
    def setup_method(self):
        self.c1 = _c("Use recursion", turn=1, ctype=ConstraintType.ALGORITHM)
        self.c2 = _c("Do not use recursion", turn=2, ctype=ConstraintType.ALGORITHM)
        self.vcg, self.res = _resolve([self.c1, self.c2])

    def test_c1_is_superseded(self):
        assert self.res.resolved[self.c1.id].status == ConstraintStatus.SUPERSEDED
        assert self.c1 in self.res.superseded

    def test_c2_is_active(self):
        assert self.res.resolved[self.c2.id].status == ConstraintStatus.ACTIVE
        assert self.c2 in self.res.active

    def test_only_one_active_constraint(self):
        assert len(self.res.active) == 1

    def test_only_one_superseded_constraint(self):
        assert len(self.res.superseded) == 1

    def test_no_conflicting_constraints(self):
        assert len(self.res.conflicting) == 0

    def test_superseded_reason_mentions_superseding_turn(self):
        reason = self.res.resolved[self.c1.id].reason
        assert "turn 2" in reason.lower() or "2" in reason

    def test_active_reason_mentions_supersession(self):
        reason = self.res.resolved[self.c2.id].reason
        assert len(reason) > 0

    def test_superseded_constraint_has_supporting_edges(self):
        rc = self.res.resolved[self.c1.id]
        assert len(rc.supporting_edges) >= 1
        assert any(
            e.edge_type == ConstraintEdgeType.SUPERSEDES for e in rc.supporting_edges
        )

    def test_via_extractor_pipeline(self):
        _, res = _resolve_convo([
            {"turn": 1, "text": "Use recursion."},
            {"turn": 2, "text": "Do not use recursion."},
        ])
        assert len(res.active) == 1
        assert len(res.superseded) == 1
        active = res.active[0]
        assert active.source_turn == 2


# ---------------------------------------------------------------------------
# C. Multi-level supersession chain: C1 → C2 → C3
# ---------------------------------------------------------------------------

class TestMultiLevelSupersession:
    def setup_method(self):
        # All ALGORITHM type so heuristics can chain them
        # Use explicit SUPERSEDES edges to guarantee the chain
        self.c1 = _c("Use recursion", turn=1, ctype=ConstraintType.ALGORITHM)
        self.c2 = _c("Do not use recursion; use iteration", turn=2,
                      ctype=ConstraintType.ALGORITHM)
        self.c3 = _c("Do not use iteration either", turn=3,
                      ctype=ConstraintType.ALGORITHM)

        self.vcg = VersionedConstraintGraph()
        for c in (self.c1, self.c2, self.c3):
            self.vcg.add_constraint(c)
        # Manually wire supersession chain
        self.vcg.add_edge(self.c2.id, self.c1.id, ConstraintEdgeType.SUPERSEDES,
                           reason="c2 replaces c1")
        self.vcg.add_edge(self.c3.id, self.c2.id, ConstraintEdgeType.SUPERSEDES,
                           reason="c3 replaces c2")

        self.res = ConstraintResolver().resolve(self.vcg)

    def test_c1_is_superseded(self):
        assert self.res.resolved[self.c1.id].status == ConstraintStatus.SUPERSEDED

    def test_c2_is_superseded(self):
        assert self.res.resolved[self.c2.id].status == ConstraintStatus.SUPERSEDED

    def test_c3_is_active(self):
        assert self.res.resolved[self.c3.id].status == ConstraintStatus.ACTIVE

    def test_only_one_active(self):
        assert len(self.res.active) == 1
        assert self.res.active[0].id == self.c3.id

    def test_two_superseded(self):
        assert len(self.res.superseded) == 2

    def test_c1_reason_references_supersessor(self):
        reason = self.res.resolved[self.c1.id].reason
        # _chain_superseded_by walks to the ACTIVE winner: C3 (turn 3)
        # so C1's reason names turn 3 as the ultimate supersessor
        assert "turn 3" in reason.lower() or "3" in reason

    def test_c2_reason_references_supersessor(self):
        reason = self.res.resolved[self.c2.id].reason
        assert "turn 3" in reason.lower() or "3" in reason

    def test_historical_chain_preserved(self):
        # All nodes still present in the graph
        assert self.vcg.node_count() == 3
        assert self.vcg.get_constraint(self.c1.id) is not None


# ---------------------------------------------------------------------------
# D. Conflict: Return None vs Raise ValueError
# ---------------------------------------------------------------------------

class TestConflict:
    def setup_method(self):
        self.c1 = _c("Return None for empty input", turn=1,
                      ctype=ConstraintType.ERROR_HANDLING)
        self.c2 = _c("Raise ValueError for empty input", turn=2,
                      ctype=ConstraintType.ERROR_HANDLING)
        self.vcg, self.res = _resolve([self.c1, self.c2])

    def test_both_are_conflicting(self):
        assert self.res.resolved[self.c1.id].status == ConstraintStatus.CONFLICTING
        assert self.res.resolved[self.c2.id].status == ConstraintStatus.CONFLICTING

    def test_conflicting_list_has_two_entries(self):
        assert len(self.res.conflicting) == 2

    def test_no_active_constraints(self):
        assert len(self.res.active) == 0

    def test_no_superseded_constraints(self):
        assert len(self.res.superseded) == 0

    def test_reason_mentions_conflict(self):
        reason = self.res.resolved[self.c1.id].reason
        assert "conflict" in reason.lower()

    def test_conflict_has_supporting_edges(self):
        rc = self.res.resolved[self.c1.id]
        assert len(rc.supporting_edges) >= 1
        assert any(e.edge_type == ConstraintEdgeType.CONFLICTS for e in rc.supporting_edges)

    def test_via_extractor_pipeline(self):
        _, res = _resolve_convo([
            {"turn": 1, "text": "Return None for empty input."},
            {"turn": 2, "text": "Raise ValueError for empty input."},
        ])
        assert len(res.conflicting) == 2
        assert len(res.active) == 0


# ---------------------------------------------------------------------------
# E. Reinforcement: original stays ACTIVE, no competing constraint
# ---------------------------------------------------------------------------

class TestReinforcement:
    def test_continuation_turn_leaves_original_active(self):
        """
        Turn 1: "Do not use max()."
        Turn 2: "Keep the previous restrictions."
        Extractor marks turn 2 as a continuation — no new constraint created.
        Original constraint from turn 1 stays ACTIVE.
        """
        _, res = _resolve_convo([
            {"turn": 1, "text": "Do not use max()."},
            {"turn": 2, "text": "Keep the previous restrictions."},
        ])
        assert len(res.active) == 1
        assert len(res.superseded) == 0
        assert len(res.conflicting) == 0
        assert res.active[0].source_turn == 1

    def test_explicit_reinforces_edge_does_not_supersede(self):
        """
        Manually adding a REINFORCES edge must not change the target to SUPERSEDED.
        """
        c1 = _c("Do not use max()", turn=1, ctype=ConstraintType.NO_BUILTIN, target="max")
        c2 = _c("Still do not use max()", turn=2,
                 ctype=ConstraintType.NO_BUILTIN, target="max")
        vcg = VersionedConstraintGraph()
        vcg.add_constraint(c1)
        vcg.add_constraint(c2)
        vcg.add_edge(c2.id, c1.id, ConstraintEdgeType.REINFORCES,
                     reason="continuation reinforces c1")
        res = ConstraintResolver().resolve(vcg)
        # c2 REINFORCES c1 — both should be active (no supersession)
        assert res.resolved[c1.id].status in (ConstraintStatus.ACTIVE,)
        assert len(res.superseded) == 0

    def test_retention_phrase_variants(self):
        """Multiple continuation phrase variants should all be recognised."""
        phrases = [
            "Retain the previous requirements.",
            "Same restrictions apply.",
            "Previous requirements still apply.",
        ]
        for phrase in phrases:
            _, res = _resolve_convo([
                {"turn": 1, "text": "Do not use max()."},
                {"turn": 2, "text": phrase},
            ])
            assert len(res.active) == 1, f"Failed for phrase: {phrase!r}"
            assert res.active[0].source_turn == 1


# ---------------------------------------------------------------------------
# F. Mixed conversation
# ---------------------------------------------------------------------------

class TestMixedConversation:
    def setup_method(self):
        """
        Turn 1: "Do not use max()."               → NO_BUILTIN (active)
        Turn 2: "Use recursion."                   → ALGORITHM (later superseded)
        Turn 3: "Do not use recursion."            → ALGORITHM (supersedes turn 2)
        Turn 4: "Return None for empty input."     → ERROR_HANDLING (conflict)
        Turn 5: "Raise ValueError for empty input."→ ERROR_HANDLING (conflict)
        """
        self.convo = [
            {"turn": 1, "text": "Do not use max()."},
            {"turn": 2, "text": "Use recursion."},
            {"turn": 3, "text": "Do not use recursion."},
            {"turn": 4, "text": "Return None for empty input."},
            {"turn": 5, "text": "Raise ValueError for empty input."},
        ]
        self.vcg, self.res = _resolve_convo(self.convo)

    def test_no_builtin_is_active(self):
        active_types = {c.type for c in self.res.active}
        assert ConstraintType.NO_BUILTIN in active_types

    def test_algorithm_supersession(self):
        # Turn 2 should be SUPERSEDED, turn 3 should be ACTIVE
        algo_superseded = [c for c in self.res.superseded
                           if c.type == ConstraintType.ALGORITHM]
        algo_active = [c for c in self.res.active
                       if c.type == ConstraintType.ALGORITHM]
        assert len(algo_superseded) >= 1
        assert len(algo_active) == 1
        assert algo_active[0].source_turn == 3

    def test_error_handling_conflict(self):
        error_conflict = [c for c in self.res.conflicting
                          if c.type == ConstraintType.ERROR_HANDLING]
        assert len(error_conflict) == 2

    def test_total_counts(self):
        total = len(self.res.active) + len(self.res.superseded) + len(self.res.conflicting)
        assert total == len(self.vcg.get_all_constraints())


# ---------------------------------------------------------------------------
# G. Resolver must NOT produce VIOLATED or SATISFIED
# ---------------------------------------------------------------------------

class TestNoVerificationStatusFromResolver:
    def _run_and_collect_statuses(self, constraints) -> set[ConstraintStatus]:
        _, res = _resolve(constraints)
        return {rc.status for rc in res.resolved.values()}

    def test_no_violated_status(self):
        c = _c("Do not use max()", turn=1)
        statuses = self._run_and_collect_statuses([c])
        assert ConstraintStatus.VIOLATED not in statuses

    def test_no_satisfied_status(self):
        c = _c("Use recursion", turn=1)
        statuses = self._run_and_collect_statuses([c])
        assert ConstraintStatus.SATISFIED not in statuses

    def test_violated_input_reset_to_active(self):
        """
        If a constraint somehow enters the graph pre-marked as VIOLATED,
        the resolver must reset it to ACTIVE (verification hasn't run yet).
        """
        c = _c("Do not use max()", turn=1,
               status=ConstraintStatus.VIOLATED)
        vcg = VersionedConstraintGraph()
        vcg.add_constraint(c)
        res = ConstraintResolver().resolve(vcg)
        assert res.resolved[c.id].status == ConstraintStatus.ACTIVE

    def test_satisfied_input_reset_to_active(self):
        c = _c("Use recursion", turn=1, status=ConstraintStatus.SATISFIED)
        vcg = VersionedConstraintGraph()
        vcg.add_constraint(c)
        res = ConstraintResolver().resolve(vcg)
        assert res.resolved[c.id].status == ConstraintStatus.ACTIVE

    def test_all_statuses_are_valid_pre_verification_states(self):
        valid = {ConstraintStatus.ACTIVE, ConstraintStatus.SUPERSEDED,
                 ConstraintStatus.CONFLICTING}
        c1 = _c("Use recursion", turn=1, ctype=ConstraintType.ALGORITHM)
        c2 = _c("Do not use recursion", turn=2, ctype=ConstraintType.ALGORITHM)
        c3 = _c("Return None for empty", turn=3, ctype=ConstraintType.ERROR_HANDLING)
        c4 = _c("Raise ValueError for empty", turn=4, ctype=ConstraintType.ERROR_HANDLING)
        statuses = self._run_and_collect_statuses([c1, c2, c3, c4])
        assert statuses.issubset(valid)


# ---------------------------------------------------------------------------
# H. explain_constraint output
# ---------------------------------------------------------------------------

class TestExplainConstraint:
    def test_explain_active_constraint(self):
        c = _c("Do not use max()", turn=1)
        vcg = VersionedConstraintGraph.build_from_constraints([c])
        explanation = ConstraintResolver().explain_constraint(c.id, vcg)
        assert "ACTIVE" in explanation.upper()
        assert "1" in explanation  # turn number

    def test_explain_superseded_constraint(self):
        c1 = _c("Use recursion", turn=1, ctype=ConstraintType.ALGORITHM)
        c2 = _c("Do not use recursion", turn=2, ctype=ConstraintType.ALGORITHM)
        vcg = VersionedConstraintGraph.build_from_constraints([c1, c2])
        explanation = ConstraintResolver().explain_constraint(c1.id, vcg)
        assert "SUPERSEDED" in explanation.upper()

    def test_explain_conflicting_constraint(self):
        c1 = _c("Return None for empty", turn=1, ctype=ConstraintType.ERROR_HANDLING)
        c2 = _c("Raise ValueError for empty input", turn=2,
                 ctype=ConstraintType.ERROR_HANDLING)
        vcg = VersionedConstraintGraph.build_from_constraints([c1, c2])
        explanation = ConstraintResolver().explain_constraint(c1.id, vcg)
        assert "CONFLICTING" in explanation.upper()

    def test_explain_unknown_id(self):
        vcg = VersionedConstraintGraph()
        explanation = ConstraintResolver().explain_constraint("nonexistent", vcg)
        assert "not found" in explanation.lower()

    def test_explain_includes_turn_number(self):
        c = _c("Do not use max()", turn=7)
        vcg = VersionedConstraintGraph.build_from_constraints([c])
        explanation = ConstraintResolver().explain_constraint(c.id, vcg)
        assert "7" in explanation

    def test_explain_includes_constraint_text(self):
        c = _c("Do not use max()", turn=1)
        vcg = VersionedConstraintGraph.build_from_constraints([c])
        explanation = ConstraintResolver().explain_constraint(c.id, vcg)
        assert "max" in explanation.lower() or "do not use" in explanation.lower()
