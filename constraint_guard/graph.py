"""
constraint_guard.graph
======================
Versioned Constraint Graph (VCG).

Constraints are nodes in a NetworkX DiGraph.  Edges encode the temporal /
semantic relationship between constraints (SUPERSEDES, CONFLICTS, REINFORCES,
DEPENDS_ON).  History is never deleted — superseded constraints remain in the
graph with their status updated.

Typical usage
-------------
    vcg = VersionedConstraintGraph()
    vcg.add_constraint(c1)
    vcg.add_constraint(c2)
    vcg.add_edge(c2.id, c1.id, ConstraintEdgeType.SUPERSEDES,
                 confidence=0.95, reason="same algorithm type, negated")
    vcg.get_active_constraints()     # [c2]
    vcg.get_superseded_constraints() # [c1]
"""

from __future__ import annotations

import re
from typing import Optional

import networkx as nx

from .models import (
    Constraint,
    ConstraintEdge,
    ConstraintEdgeType,
    ConstraintStatus,
    ConstraintType,
)


# ---------------------------------------------------------------------------
# Supersession heuristics
# ---------------------------------------------------------------------------

# Negation words that flip the polarity of a requirement.
_NEGATION_WORDS = re.compile(
    r"\b(?:do\s+not|don'?t|avoid|no|without|never)\b", re.I
)

# Pairs of opposite algorithm terms.
_ALGORITHM_OPPOSITES = [
    ({"recursion", "recursive", "recurse"}, {"iteration", "iterative", "loop", "loops"}),
]


def _polarity(text: str) -> str:
    """Return 'negative' if the text is negated, else 'positive'."""
    return "negative" if _NEGATION_WORDS.search(text) else "positive"


def _algorithm_keyword(text: str) -> Optional[str]:
    """
    Return the dominant algorithm keyword group present in text,
    or None if none is detected.
    """
    lower = text.lower()
    for pos_set, neg_set in _ALGORITHM_OPPOSITES:
        if any(k in lower for k in pos_set):
            return "recursion_family"
        if any(k in lower for k in neg_set):
            return "iteration_family"
    return None


def _same_target(a: Constraint, b: Constraint) -> bool:
    """True when two constraints refer to the same target (case-insensitive)."""
    if a.target and b.target:
        return a.target.lower() == b.target.lower()
    return False


def _supersedes(newer: Constraint, older: Constraint) -> Optional[str]:
    """
    Heuristically decide whether *newer* supersedes *older*.

    Returns a human-readable reason string on success, None otherwise.
    Rules (checked in order — first match wins):
    1. Same ConstraintType + same target → explicit replacement.
    2. ALGORITHM: same keyword-family but opposite polarity.
    3. Same ConstraintType + opposite polarity (for types where polarity matters).
    """
    if newer.source_turn <= older.source_turn:
        return None  # older turn can't supersede newer

    # Rule 1: same type, same named target  (e.g. two NO_BUILTIN for "max")
    if newer.type == older.type and _same_target(newer, older):
        return (
            f"Turn {newer.source_turn} replaces turn {older.source_turn}: "
            f"same type ({newer.type.value}) and same target ({newer.target})"
        )

    # Rule 2: ALGORITHM with opposite polarity
    if newer.type == ConstraintType.ALGORITHM and older.type == ConstraintType.ALGORITHM:
        new_kw = _algorithm_keyword(newer.text)
        old_kw = _algorithm_keyword(older.text)
        new_pol = _polarity(newer.text)
        old_pol = _polarity(older.text)

        if new_kw and old_kw and new_kw == old_kw and new_pol != old_pol:
            return (
                f"Turn {newer.source_turn} negates turn {older.source_turn}: "
                f"'{older.text[:50]}' → '{newer.text[:50]}'"
            )

    # Rule 3: Same type, one positive one negative (covers ERROR_HANDLING, STRUCTURE…)
    if newer.type == older.type:
        new_pol = _polarity(newer.text)
        old_pol = _polarity(older.text)
        if new_pol != old_pol:
            return (
                f"Turn {newer.source_turn} overrides turn {older.source_turn}: "
                f"opposite polarity for type {newer.type.value}"
            )

    return None



# Mutually exclusive keyword groups — if two constraints of the same type
# each contain a word from *different* groups, they conflict semantically.
_CONFLICT_GROUPS: dict[ConstraintType, list[set[str]]] = {
    ConstraintType.ERROR_HANDLING: [
        {"return none", "return null", "return empty", "return -1"},
        {"raise", "throw", "valueerror", "typeerror", "exception"},
    ],
    ConstraintType.ALGORITHM: [
        {"recursion", "recursive", "recurse"},
        {"iteration", "iterative", "loop", "loops", "iteratively"},
    ],
    ConstraintType.STRUCTURE: [
        {"class", "oop", "object"},
        {"function", "single function", "no class"},
    ],
}


def _semantic_conflict_group(ctype: ConstraintType, text: str) -> Optional[int]:
    """
    Return the index of the conflict group that *text* belongs to for *ctype*,
    or None if text doesn't match any group.
    """
    groups = _CONFLICT_GROUPS.get(ctype)
    if not groups:
        return None
    lower = text.lower()
    for idx, keyword_set in enumerate(groups):
        if any(kw in lower for kw in keyword_set):
            return idx
    return None


def _conflicts(a: Constraint, b: Constraint) -> Optional[str]:
    """
    Detect a conflict between two ACTIVE constraints.

    A conflict exists when either:
    1. Same type + opposite negation polarity.
    2. Same type + each belongs to a mutually exclusive semantic keyword group.
    """
    if a.id == b.id:
        return None
    if a.type != b.type:
        return None
    if a.status != ConstraintStatus.ACTIVE or b.status != ConstraintStatus.ACTIVE:
        return None

    # Check 1: polarity-based conflict
    pol_a = _polarity(a.text)
    pol_b = _polarity(b.text)
    if pol_a != pol_b:
        return (
            f"Conflict: turn {a.source_turn} says '{a.text[:40]}' "
            f"but turn {b.source_turn} says '{b.text[:40]}'"
        )

    # Check 2: semantic keyword group conflict
    grp_a = _semantic_conflict_group(a.type, a.text)
    grp_b = _semantic_conflict_group(b.type, b.text)
    if grp_a is not None and grp_b is not None and grp_a != grp_b:
        return (
            f"Semantic conflict: turn {a.source_turn} (group {grp_a}) vs "
            f"turn {b.source_turn} (group {grp_b}) for type {a.type.value}"
        )

    return None


# ---------------------------------------------------------------------------
# VersionedConstraintGraph
# ---------------------------------------------------------------------------

class VersionedConstraintGraph:
    """
    Directed graph of constraints over a multi-turn conversation.

    Node attributes
    ---------------
    'constraint': Constraint object (Pydantic model)

    Edge attributes
    ---------------
    'edge': ConstraintEdge object (Pydantic model)
    """

    def __init__(self) -> None:
        self._graph: nx.DiGraph = nx.DiGraph()

    # ------------------------------------------------------------------ mutators

    def add_constraint(self, constraint: Constraint) -> None:
        """Add a constraint node to the graph."""
        self._graph.add_node(constraint.id, constraint=constraint)

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: ConstraintEdgeType,
        confidence: float = 1.0,
        reason: str = "",
    ) -> ConstraintEdge:
        """
        Add a directed edge and update node statuses.

        SUPERSEDES: target's status → SUPERSEDED.
        CONFLICTS:  both nodes' statuses → CONFLICTING (if they are ACTIVE).
        REINFORCES / DEPENDS_ON: no automatic status change.
        """
        edge = ConstraintEdge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            confidence=confidence,
            reason=reason,
        )
        self._graph.add_edge(source_id, target_id, edge=edge)

        if edge_type == ConstraintEdgeType.SUPERSEDES:
            target_c = self._get_constraint_obj(target_id)
            if target_c is not None:
                target_c.status = ConstraintStatus.SUPERSEDED

        elif edge_type == ConstraintEdgeType.CONFLICTS:
            for nid in (source_id, target_id):
                c = self._get_constraint_obj(nid)
                if c is not None and c.status == ConstraintStatus.ACTIVE:
                    c.status = ConstraintStatus.CONFLICTING

        return edge

    # ------------------------------------------------------------------ queries

    def get_constraint(self, constraint_id: str) -> Optional[Constraint]:
        """Return the Constraint with the given id, or None."""
        return self._get_constraint_obj(constraint_id)

    def get_all_constraints(self) -> list[Constraint]:
        """Return every constraint in insertion order."""
        return [
            data["constraint"]
            for _, data in self._graph.nodes(data=True)
            if "constraint" in data
        ]

    def get_active_constraints(self) -> list[Constraint]:
        return [c for c in self.get_all_constraints() if c.status == ConstraintStatus.ACTIVE]

    def get_superseded_constraints(self) -> list[Constraint]:
        return [c for c in self.get_all_constraints() if c.status == ConstraintStatus.SUPERSEDED]

    def get_conflicting_constraints(self) -> list[Constraint]:
        return [c for c in self.get_all_constraints() if c.status == ConstraintStatus.CONFLICTING]

    def get_edges_for_constraint(self, constraint_id: str) -> list[ConstraintEdge]:
        """Return all edges where constraint_id is source OR target."""
        edges: list[ConstraintEdge] = []
        # outgoing
        for _, tgt, data in self._graph.out_edges(constraint_id, data=True):
            if "edge" in data:
                edges.append(data["edge"])
        # incoming
        for src, _, data in self._graph.in_edges(constraint_id, data=True):
            if "edge" in data:
                edges.append(data["edge"])
        return edges

    def get_all_edges(self) -> list[tuple[str, str, ConstraintEdgeType]]:
        """Return all edges in the graph as (source_id, target_id, edge_type) tuples."""
        edges: list[tuple[str, str, ConstraintEdgeType]] = []
        for src, tgt, data in self._graph.edges(data=True):
            if "edge" in data:
                edge_obj = data["edge"]
                edges.append((src, tgt, edge_obj.edge_type))
        return edges

    def node_count(self) -> int:
        return self._graph.number_of_nodes()

    def edge_count(self) -> int:
        return self._graph.number_of_edges()

    def format_ascii_graph(self) -> str:
        """Return a human-readable ASCII representation of the Versioned Constraint Graph."""
        lines = []
        lines.append("🕸️  VERSIONED CONSTRAINT GRAPH (VCG)")
        lines.append("=" * 60)
        lines.append(f"Nodes: {self.node_count()} | Edges: {self.edge_count()}\n")

        lines.append("┌─ GRAPH NODES (Constraints) ──────────────────────────┐")
        all_c = self.get_all_constraints()
        if not all_c:
            lines.append("  (No constraint nodes in graph)")
        for c in all_c:
            status_icon = (
                "[ACTIVE 🟢]" if c.status.value == "ACTIVE"
                else "[SUPERSEDED 🟡]" if c.status.value == "SUPERSEDED"
                else "[CONFLICTING 🔴]"
            )
            target_str = f" target={c.target}" if c.target else ""
            lines.append(f"  ● {c.id:<8} {status_icon:<16} (Turn {c.source_turn} | {c.type.value}{target_str})")
            lines.append(f"    Text: \"{c.text}\"")

        lines.append("\n┌─ GRAPH EDGES (Temporal & Semantic Relations) ────────┐")

        raw_edges = []
        for src, tgt, data in self._graph.edges(data=True):
            if "edge" in data:
                raw_edges.append(data["edge"])

        if not raw_edges:
            lines.append("  (No directional edges / relationships detected)")
        else:
            processed_pairs = set()
            for edge in raw_edges:
                pair = frozenset({edge.source_id, edge.target_id})
                if edge.edge_type == ConstraintEdgeType.CONFLICTS and pair in processed_pairs:
                    continue

                if edge.edge_type == ConstraintEdgeType.SUPERSEDES:
                    arrow = "───( SUPERSEDES )───►"
                    lines.append(f"  [{edge.source_id}] {arrow} [{edge.target_id}]")
                    if edge.reason:
                        lines.append(f"      Reason: {edge.reason}")
                elif edge.edge_type == ConstraintEdgeType.CONFLICTS:
                    arrow = "◄───( CONFLICTS )───►"
                    lines.append(f"  [{edge.source_id}] {arrow} [{edge.target_id}]")
                    if edge.reason:
                        lines.append(f"      Reason: {edge.reason}")
                    processed_pairs.add(pair)
                else:
                    arrow = f"───( {edge.edge_type.value} )───►"
                    lines.append(f"  [{edge.source_id}] {arrow} [{edge.target_id}]")
                    if edge.reason:
                        lines.append(f"      Reason: {edge.reason}")

        lines.append("└──────────────────────────────────────────────────────┘")
        return "\n".join(lines)


    # ------------------------------------------------------------------ builders

    @classmethod
    def build_from_constraints(
        cls,
        constraints: list[Constraint],
        auto_resolve: bool = True,
    ) -> "VersionedConstraintGraph":
        """
        Build a VCG from an ordered list of Constraint objects.

        When *auto_resolve* is True (default), the graph automatically:
        - Adds SUPERSEDES edges where a later constraint replaces an earlier one.
        - Adds CONFLICTS edges where two active constraints contradict each other.

        The constraints list should be ordered by source_turn ascending.
        """
        vcg = cls()
        sorted_constraints = sorted(constraints, key=lambda c: c.source_turn)

        for c in sorted_constraints:
            vcg.add_constraint(c)

        if not auto_resolve:
            return vcg

        # Supersession pass: for each pair (older, newer), check if newer supersedes older
        for i, newer in enumerate(sorted_constraints):
            for older in sorted_constraints[:i]:
                reason = _supersedes(newer, older)
                if reason and older.status != ConstraintStatus.SUPERSEDED:
                    vcg.add_edge(
                        newer.id, older.id,
                        ConstraintEdgeType.SUPERSEDES,
                        confidence=0.90,
                        reason=reason,
                    )

        # Conflict pass: among all remaining ACTIVE constraints, detect contradictions
        active = vcg.get_active_constraints()
        seen_conflict_pairs: set[frozenset[str]] = set()
        for i, a in enumerate(active):
            for b in active[i + 1:]:
                pair = frozenset({a.id, b.id})
                if pair in seen_conflict_pairs:
                    continue
                reason = _conflicts(a, b)
                if reason:
                    vcg.add_edge(
                        a.id, b.id,
                        ConstraintEdgeType.CONFLICTS,
                        confidence=0.85,
                        reason=reason,
                    )
                    vcg.add_edge(
                        b.id, a.id,
                        ConstraintEdgeType.CONFLICTS,
                        confidence=0.85,
                        reason=reason,
                    )
                    seen_conflict_pairs.add(pair)

        return vcg

    # ------------------------------------------------------------------ private

    def _get_constraint_obj(self, constraint_id: str) -> Optional[Constraint]:
        if constraint_id not in self._graph:
            return None
        return self._graph.nodes[constraint_id].get("constraint")
