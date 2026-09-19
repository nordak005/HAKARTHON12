"""
constraint_guard.resolver
=========================
Lifecycle & Relationship Resolver.

Takes a VersionedConstraintGraph that already contains raw SUPERSEDES / CONFLICTS /
REINFORCES edges (produced by VersionedConstraintGraph.build_from_constraints) and
produces a fully resolved ResolutionResult that answers:

  - Which constraints are ACTIVE?
  - Which are SUPERSEDED (including supersession chains)?
  - Which are CONFLICTING?
  - Why is each constraint in its current state?

Responsibility boundary
-----------------------
Resolver   → conversation-state only (ACTIVE / SUPERSEDED / CONFLICTING).
Verifier   → code compliance (VIOLATED / SATISFIED).

The resolver NEVER marks a constraint VIOLATED or SATISFIED.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .graph import VersionedConstraintGraph
from .models import (
    Constraint,
    ConstraintEdge,
    ConstraintEdgeType,
    ConstraintStatus,
)


# ---------------------------------------------------------------------------
# Result data-classes
# ---------------------------------------------------------------------------

@dataclass
class ResolvedConstraint:
    """
    The resolved state of one constraint, including a human-readable explanation
    and the graph edges that justify the conclusion.
    """
    constraint:         Constraint
    status:             ConstraintStatus
    reason:             str
    supporting_edges:   list[ConstraintEdge] = field(default_factory=list)


@dataclass
class ResolutionResult:
    """
    Full output of a resolution pass over a VersionedConstraintGraph.

    Attributes
    ----------
    resolved    : Maps constraint_id -> ResolvedConstraint for every node.
    active      : Constraints that are currently in force.
    superseded  : Constraints that have been replaced by a later turn.
    conflicting : Active constraints that contradict each other.
    """
    resolved:    dict[str, ResolvedConstraint]   = field(default_factory=dict)
    active:      list[Constraint]                = field(default_factory=list)
    superseded:  list[Constraint]                = field(default_factory=list)
    conflicting: list[Constraint]                = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _outgoing_supersedes(
    constraint_id: str,
    graph: VersionedConstraintGraph,
) -> list[ConstraintEdge]:
    """Return all SUPERSEDES edges where *constraint_id* is the source (newer node)."""
    edges = graph.get_edges_for_constraint(constraint_id)
    return [
        e for e in edges
        if e.edge_type == ConstraintEdgeType.SUPERSEDES and e.source_id == constraint_id
    ]


def _incoming_supersedes(
    constraint_id: str,
    graph: VersionedConstraintGraph,
) -> list[ConstraintEdge]:
    """Return all SUPERSEDES edges where *constraint_id* is the target (older, superseded node)."""
    edges = graph.get_edges_for_constraint(constraint_id)
    return [
        e for e in edges
        if e.edge_type == ConstraintEdgeType.SUPERSEDES and e.target_id == constraint_id
    ]


def _conflict_edges(
    constraint_id: str,
    graph: VersionedConstraintGraph,
) -> list[ConstraintEdge]:
    """Return all CONFLICTS edges incident to *constraint_id*."""
    edges = graph.get_edges_for_constraint(constraint_id)
    return [e for e in edges if e.edge_type == ConstraintEdgeType.CONFLICTS]


def _reinforces_edges(
    constraint_id: str,
    graph: VersionedConstraintGraph,
) -> list[ConstraintEdge]:
    """Return all REINFORCES edges where *constraint_id* is the source."""
    edges = graph.get_edges_for_constraint(constraint_id)
    return [
        e for e in edges
        if e.edge_type == ConstraintEdgeType.REINFORCES and e.source_id == constraint_id
    ]


def _find_supersession_root(
    constraint_id: str,
    graph: VersionedConstraintGraph,
    visited: Optional[set[str]] = None,
) -> Optional[str]:
    """
    Walk SUPERSEDES edges forward (source → target) to find the oldest ancestor
    that *constraint_id* eventually supersedes.

    Returns the ancestor's id, or None if *constraint_id* is itself the root.
    Used to detect transitive supersession chains.
    """
    if visited is None:
        visited = set()
    if constraint_id in visited:
        return None  # cycle guard
    visited.add(constraint_id)

    outgoing = _outgoing_supersedes(constraint_id, graph)
    if not outgoing:
        return None   # no outgoing supersession — this node is a root candidate

    # Follow the chain (take the highest-confidence edge in case of branches)
    outgoing_sorted = sorted(outgoing, key=lambda e: e.confidence, reverse=True)
    for edge in outgoing_sorted:
        deeper = _find_supersession_root(edge.target_id, graph, visited)
        if deeper is not None:
            return deeper
    return outgoing_sorted[0].target_id


def _chain_superseded_by(
    constraint_id: str,
    graph: VersionedConstraintGraph,
) -> Optional[str]:
    """
    For a given constraint, return the id of the newest constraint that directly
    or transitively supersedes it (i.e., the ACTIVE replacement).
    Returns None if nothing supersedes it.
    """
    incoming = _incoming_supersedes(constraint_id, graph)
    if not incoming:
        return None
    # Among all nodes that supersede this one, find the one with the highest turn
    candidates: list[Constraint] = []
    for edge in incoming:
        c = graph.get_constraint(edge.source_id)
        if c:
            candidates.append(c)
    if not candidates:
        return None
    # Sort by turn descending — the highest turn is the final winner
    candidates.sort(key=lambda c: c.source_turn, reverse=True)
    winner = candidates[0]
    # Walk further: if the winner is itself superseded, follow the chain
    deeper = _chain_superseded_by(winner.id, graph)
    return deeper if deeper else winner.id


# ---------------------------------------------------------------------------
# ConstraintResolver
# ---------------------------------------------------------------------------

class ConstraintResolver:
    """
    Resolves the lifecycle state of every constraint in a VersionedConstraintGraph.

    The resolver does NOT modify the graph in place — it reads existing edges and
    returns a ResolutionResult.  The graph's node.status fields ARE updated as a
    side-effect (to keep the graph queryable after resolution), but the canonical
    answer lives in ResolutionResult.resolved.

    Usage
    -----
        vcg  = VersionedConstraintGraph.build_from_constraints(constraints)
        res  = ConstraintResolver().resolve(vcg)
        print(res.active)
        print(resolver.explain_constraint(some_id, vcg))
    """

    # ------------------------------------------------------------------ public API

    def resolve(self, graph: VersionedConstraintGraph) -> ResolutionResult:
        """
        Perform a full resolution pass over *graph*.

        Steps
        -----
        1. Walk all SUPERSEDES chains to determine final ACTIVE / SUPERSEDED status.
        2. Among remaining ACTIVE nodes, propagate CONFLICTING status.
        3. Verify no constraint is incorrectly marked VIOLATED / SATISFIED.
        4. Build ResolvedConstraint objects with explanations.
        """
        result = ResolutionResult()
        all_constraints = graph.get_all_constraints()

        # --- Step 1: supersession chain resolution ---
        # For each constraint, decide its status purely from graph topology.
        # A constraint is SUPERSEDED iff there is at least one incoming SUPERSEDES
        # edge AND its supersessor is not itself superseded (i.e., it's in the
        # transitive shadow of a later active node).

        for c in all_constraints:
            superseded_by_id = _chain_superseded_by(c.id, graph)
            if superseded_by_id:
                # Mark as SUPERSEDED (graph node is updated too for consistency)
                c.status = ConstraintStatus.SUPERSEDED
            else:
                # Check if it already had CONFLICTING from graph builder; keep it
                if c.status not in (ConstraintStatus.CONFLICTING,):
                    c.status = ConstraintStatus.ACTIVE

        # --- Step 2: conflict propagation ---
        # Among nodes that ended up ACTIVE, re-confirm CONFLICTING status
        # from existing CONFLICTS edges.
        active_now = [c for c in all_constraints if c.status == ConstraintStatus.ACTIVE]
        for c in active_now:
            edges = _conflict_edges(c.id, graph)
            if edges:
                # Confirm the other endpoint is also still active / conflicting
                for e in edges:
                    peer_id = e.target_id if e.source_id == c.id else e.source_id
                    peer = graph.get_constraint(peer_id)
                    if peer and peer.status in (ConstraintStatus.ACTIVE,
                                                ConstraintStatus.CONFLICTING):
                        c.status = ConstraintStatus.CONFLICTING
                        peer.status = ConstraintStatus.CONFLICTING
                        break

        # --- Step 3: safety guard — resolver must not produce VIOLATED / SATISFIED ---
        for c in all_constraints:
            if c.status in (ConstraintStatus.VIOLATED, ConstraintStatus.SATISFIED):
                # Reset to ACTIVE; verification hasn't run yet
                c.status = ConstraintStatus.ACTIVE

        # --- Step 4: build ResolvedConstraint with explanations ---
        for c in all_constraints:
            rc = self._build_resolved(c, graph)
            result.resolved[c.id] = rc

        # Populate convenience lists
        result.active      = [r.constraint for r in result.resolved.values()
                               if r.status == ConstraintStatus.ACTIVE]
        result.superseded  = [r.constraint for r in result.resolved.values()
                               if r.status == ConstraintStatus.SUPERSEDED]
        result.conflicting = [r.constraint for r in result.resolved.values()
                               if r.status == ConstraintStatus.CONFLICTING]

        return result

    def get_active_constraints(self, graph: VersionedConstraintGraph) -> list[Constraint]:
        """Resolve and return only the ACTIVE constraints."""
        return self.resolve(graph).active

    def get_superseded_constraints(self, graph: VersionedConstraintGraph) -> list[Constraint]:
        """Resolve and return only the SUPERSEDED constraints."""
        return self.resolve(graph).superseded

    def get_conflicting_constraints(self, graph: VersionedConstraintGraph) -> list[Constraint]:
        """Resolve and return only the CONFLICTING constraints."""
        return self.resolve(graph).conflicting

    def explain_constraint(
        self,
        constraint_id: str,
        graph: VersionedConstraintGraph,
    ) -> str:
        """
        Return a human-readable explanation of why a constraint has its resolved status.

        Delegates to the cached ResolutionResult from a fresh resolve() call.
        """
        result = self.resolve(graph)
        rc = result.resolved.get(constraint_id)
        if rc is None:
            return f"Constraint '{constraint_id}' not found in graph."
        return (
            f"[{rc.status.value.upper()}] Turn {rc.constraint.source_turn} — "
            f'"{rc.constraint.text[:70]}"\n'
            f"  Reason: {rc.reason}"
        )

    # ------------------------------------------------------------------ private helpers

    def _build_resolved(
        self,
        constraint: Constraint,
        graph: VersionedConstraintGraph,
    ) -> ResolvedConstraint:
        """Build a ResolvedConstraint with reason text and supporting edges."""
        status = constraint.status
        supporting: list[ConstraintEdge] = []

        if status == ConstraintStatus.SUPERSEDED:
            in_edges = _incoming_supersedes(constraint.id, graph)
            supporting.extend(in_edges)
            superseder_id = _chain_superseded_by(constraint.id, graph)
            if superseder_id:
                superseder = graph.get_constraint(superseder_id)
                if superseder:
                    reason = (
                        f"Superseded by constraint from turn {superseder.source_turn} "
                        f'("{superseder.text[:50]}")'
                    )
                else:
                    reason = f"Superseded by constraint '{superseder_id}'."
            else:
                reason = "Superseded (supersessor not found in graph)."

        elif status == ConstraintStatus.CONFLICTING:
            conflict_edges_list = _conflict_edges(constraint.id, graph)
            supporting.extend(conflict_edges_list)
            peer_ids = {
                (e.target_id if e.source_id == constraint.id else e.source_id)
                for e in conflict_edges_list
            }
            peers_desc = ", ".join(
                f"turn {graph.get_constraint(pid).source_turn}"
                for pid in peer_ids
                if graph.get_constraint(pid)
            )
            reason = (
                f"Conflicts with constraint(s) from {peers_desc}. "
                "No supersession relationship resolves this ambiguity. "
                "Manual disambiguation required."
            )

        elif status == ConstraintStatus.ACTIVE:
            # Check for REINFORCES outgoing edges
            reinf_edges = _reinforces_edges(constraint.id, graph)
            if reinf_edges:
                supporting.extend(reinf_edges)
                targets_desc = ", ".join(
                    f"turn {graph.get_constraint(e.target_id).source_turn}"
                    for e in reinf_edges
                    if graph.get_constraint(e.target_id)
                )
                reason = (
                    f"Active. Reinforces constraint(s) from {targets_desc}. "
                    "Latest in its constraint lineage."
                )
            else:
                # Check if it was reinforced by a later turn
                all_reinforces = [
                    e for e in graph.get_edges_for_constraint(constraint.id)
                    if e.edge_type == ConstraintEdgeType.REINFORCES
                    and e.target_id == constraint.id
                ]
                if all_reinforces:
                    supporting.extend(all_reinforces)
                    reason = (
                        "Active. Reinforced by a continuation phrase in a later turn."
                    )
                else:
                    in_super = _incoming_supersedes(constraint.id, graph)
                    if not in_super:
                        out_super = _outgoing_supersedes(constraint.id, graph)
                        if out_super:
                            targets = ", ".join(
                                f"turn {graph.get_constraint(e.target_id).source_turn}"
                                for e in out_super
                                if graph.get_constraint(e.target_id)
                            )
                            supporting.extend(out_super)
                            reason = (
                                f"Active. Supersedes earlier constraint(s) from "
                                f"{targets}. This is the current requirement."
                            )
                        else:
                            reason = (
                                "Active. No supersession or conflict relationships found. "
                                "Stands as stated."
                            )
                    else:
                        reason = "Active (supersessor of this node is no longer active)."

        else:
            reason = f"Status: {status.value}."

        return ResolvedConstraint(
            constraint=constraint,
            status=status,
            reason=reason,
            supporting_edges=supporting,
        )
