"""
constraint_guard.evaluation.baseline
======================================
Simple flat-state + AST-only baseline for comparison.

Architecture (deliberately simple):
  Conversation → flat constraint list → latest-per-type only → AST verification

Key limitations vs ConstraintGuard:
  1. No VCG or multi-edge supersession chains — uses naive "keep latest per type"
  2. No conflict detection — treats conflicting constraints independently
  3. AST-only verification — no lexical (tokenize) or behavioral (subprocess) checks
  4. No evidence aggregation — single-lane, binary pass/fail per constraint

This baseline is intentionally simple to establish a meaningful comparison baseline.
It is NOT a copy of any reference implementation.
"""

from __future__ import annotations

import ast
import re
import textwrap
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Simple flat constraint extraction (no graph, no pydantic)
# ---------------------------------------------------------------------------

@dataclass
class FlatConstraint:
    text: str
    ctype: str        # e.g. "no_builtin", "algorithm", etc.
    target: Optional[str]
    source_turn: int


# Minimal rule set for baseline extraction — much simpler than extractor.py
_RULES = [
    # NO_BUILTIN
    (re.compile(r"\b(?:do\s+not|don'?t|never)\s+use\s+(?:the\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\(?", re.I),
     "no_builtin", 1),
    (re.compile(r"\bavoid\s+(?:using\s+)?([A-Za-z_][A-Za-z0-9_.]+)\b", re.I),
     "no_builtin", 1),
    # ALGORITHM
    (re.compile(r"\b(?:do\s+not|don'?t|avoid|no)\s+(?:use\s+)?(?:recursion|recursive)\b", re.I),
     "algorithm", None),
    (re.compile(r"\buse\s+recursion\b", re.I), "algorithm", None),
    (re.compile(r"\buse\s+iteration\b", re.I), "algorithm", None),
    # ERROR_HANDLING
    (re.compile(r"\breturn\s+None\s+for\s+empty\b", re.I), "error_handling", None),
    (re.compile(r"\braise\s+ValueError\b", re.I), "error_handling", None),
    (re.compile(r"\bhandle\s+(?:an?\s+)?empty\b", re.I), "error_handling", None),
    # NAMING
    (re.compile(r"\bname\s+the\s+function\s+([A-Za-z_][A-Za-z0-9_]*)\b", re.I), "naming", 1),
    (re.compile(r"\bfunction\s+should\s+be\s+called\s+([A-Za-z_][A-Za-z0-9_]*)\b", re.I), "naming", 1),
    # STRUCTURE
    (re.compile(r"\buse\s+a\s+class\b", re.I), "structure", None),
    # COMPLEXITY
    (re.compile(r"O\(n\)", re.I), "complexity", None),
    (re.compile(r"\blinear\s+time\b", re.I), "complexity", None),
    # SIGNATURE
    (re.compile(r"\baccept\s+a\s+list\b", re.I), "signature", None),
    (re.compile(r"\breturn\s+an?\s+integer\b", re.I), "signature", None),
]

_CONTINUATION_PHRASES = re.compile(
    r"\b(?:keep|retain|same|previous|still\s+apply|as\s+before)\b.{0,30}?"
    r"(?:restriction|requirement|constraint|rule)\b",
    re.I,
)


def _extract_flat(conversation: list[dict]) -> list[FlatConstraint]:
    """
    Extract constraints from all turns WITHOUT graph/lifecycle reasoning.
    Returns ALL matched constraints (multiple per type allowed).
    """
    results: list[FlatConstraint] = []
    for turn in conversation:
        text = turn["text"]
        turn_n = turn["turn"]
        if _CONTINUATION_PHRASES.search(text):
            continue  # skip continuation phrases
        for pattern, ctype, target_group in _RULES:
            m = pattern.search(text)
            if m:
                target = None
                if target_group is not None:
                    try:
                        target = m.group(target_group).strip("()")
                    except IndexError:
                        pass
                results.append(FlatConstraint(
                    text=text.strip(),
                    ctype=ctype,
                    target=target,
                    source_turn=turn_n,
                ))
    return results


def _keep_latest_per_type(constraints: list[FlatConstraint]) -> list[FlatConstraint]:
    """
    Naive supersession: for each type, keep only the LATEST turn's constraint.
    This is wrong for cases where both "use X" and "don't use X" apply
    (keeps the later one without understanding the relationship).
    """
    latest: dict[str, FlatConstraint] = {}
    for c in sorted(constraints, key=lambda x: x.source_turn):
        latest[c.ctype] = c
    return list(latest.values())


# ---------------------------------------------------------------------------
# AST-only verification (no lexical, no behavioral)
# ---------------------------------------------------------------------------

def _ast_verify_no_builtin(target: Optional[str], code: str) -> str:
    if not target:
        return "uncertain"
    try:
        tree = ast.parse(textwrap.dedent(code))
    except SyntaxError:
        return "uncertain"
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else (
                func.attr if isinstance(func, ast.Attribute) else None
            )
            if name == target:
                return "violated"
    return "satisfied"


def _ast_verify_algorithm(constraint_text: str, code: str) -> str:
    is_negated = bool(re.search(r"\b(?:not|don'?t|avoid|no)\b", constraint_text, re.I))
    try:
        tree = ast.parse(textwrap.dedent(code))
    except SyntaxError:
        return "uncertain"

    def has_recursion(tree):
        for func in ast.walk(tree):
            if isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for node in ast.walk(func):
                    if isinstance(node, ast.Call):
                        fn = node.func
                        name = fn.id if isinstance(fn, ast.Name) else None
                        if name == func.name:
                            return True
        return False

    recursion_present = has_recursion(tree)
    has_loop = any(isinstance(n, (ast.For, ast.While)) for n in ast.walk(tree))

    if "recursion" in constraint_text.lower():
        if is_negated:
            return "violated" if recursion_present else "satisfied"
        else:
            return "satisfied" if recursion_present else "violated"

    if any(k in constraint_text.lower() for k in ("iteration", "loop")):
        if is_negated:
            return "violated" if has_loop else "satisfied"
        else:
            return "satisfied" if has_loop else "violated"

    return "uncertain"


def _ast_verify_naming(target: Optional[str], code: str) -> str:
    if not target:
        return "uncertain"
    try:
        tree = ast.parse(textwrap.dedent(code))
    except SyntaxError:
        return "uncertain"
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == target:
                return "satisfied"
    return "violated"


def _ast_verify_structure(constraint_text: str, code: str) -> str:
    is_negated = bool(re.search(r"\b(?:not|don'?t|no)\b", constraint_text, re.I))
    try:
        tree = ast.parse(textwrap.dedent(code))
    except SyntaxError:
        return "uncertain"
    has_class = any(isinstance(n, ast.ClassDef) for n in ast.walk(tree))
    if "class" in constraint_text.lower():
        if is_negated:
            return "violated" if has_class else "satisfied"
        else:
            return "satisfied" if has_class else "violated"
    return "uncertain"


def _ast_verify_error_handling(constraint_text: str, code: str) -> str:
    """
    Baseline uses AST only (no subprocess behavioral test).
    This is a key weakness vs ConstraintGuard.
    """
    try:
        tree = ast.parse(textwrap.dedent(code))
    except SyntaxError:
        return "uncertain"

    has_raise = any(isinstance(n, ast.Raise) for n in ast.walk(tree))
    has_if = any(isinstance(n, ast.If) for n in ast.walk(tree))
    has_return_none = any(
        isinstance(n, ast.Return) and isinstance(n.value, ast.Constant) and n.value.value is None
        for n in ast.walk(tree)
    )

    text = constraint_text.lower()
    if "return none" in text:
        return "satisfied" if has_return_none else "uncertain"
    if "raise valueerror" in text.replace(" ", ""):
        return "satisfied" if has_raise else "uncertain"
    if "empty" in text or "gracefully" in text:
        return "satisfied" if (has_if or has_raise) else "uncertain"
    return "uncertain"


def _ast_verify(constraint: FlatConstraint, code: str) -> str:
    """Route to appropriate AST-only verifier. Returns 'satisfied'/'violated'/'uncertain'."""
    if constraint.ctype == "no_builtin":
        return _ast_verify_no_builtin(constraint.target, code)
    if constraint.ctype == "algorithm":
        return _ast_verify_algorithm(constraint.text, code)
    if constraint.ctype == "naming":
        return _ast_verify_naming(constraint.target, code)
    if constraint.ctype == "structure":
        return _ast_verify_structure(constraint.text, code)
    if constraint.ctype == "error_handling":
        return _ast_verify_error_handling(constraint.text, code)
    return "uncertain"   # complexity, signature, general


# ---------------------------------------------------------------------------
# BaselineResult + BaselineVerifier
# ---------------------------------------------------------------------------

@dataclass
class BaselineResult:
    case_id:          str
    constraints:      list[FlatConstraint]         = field(default_factory=list)
    per_constraint:   dict[str, str]               = field(default_factory=dict)  # ctype→status
    overall_status:   str                          = "PASS"   # "PASS" or "FAIL"
    active_types:     list[str]                    = field(default_factory=list)
    violated_types:   list[str]                    = field(default_factory=list)
    satisfied_types:  list[str]                    = field(default_factory=list)
    uncertain_types:  list[str]                    = field(default_factory=list)


class BaselineVerifier:
    """
    Flat-state + AST-only baseline verifier.

    Pipeline:
      1. Extract all constraints from conversation (regex-based, no graph)
      2. Keep latest per type (naive supersession)
      3. Verify each with AST only (no lexical / behavioral lanes)
      4. FAIL if any constraint is violated; PASS otherwise

    Does NOT detect conflicts.
    Does NOT track supersession chains properly (uses naive "latest wins").
    Does NOT run behavioral subprocess tests.
    """

    def verify(self, case_id: str, conversation: list[dict], code: str) -> BaselineResult:
        all_constraints = _extract_flat(conversation)
        active = _keep_latest_per_type(all_constraints)

        per_constraint: dict[str, str] = {}
        violated: list[str] = []
        satisfied: list[str] = []
        uncertain: list[str] = []

        for c in active:
            status = _ast_verify(c, code)
            per_constraint[c.ctype] = status
            if status == "violated":
                violated.append(c.ctype)
            elif status == "satisfied":
                satisfied.append(c.ctype)
            else:
                uncertain.append(c.ctype)

        overall = "FAIL" if violated else "PASS"

        return BaselineResult(
            case_id=case_id,
            constraints=active,
            per_constraint=per_constraint,
            overall_status=overall,
            active_types=[c.ctype for c in active],
            violated_types=violated,
            satisfied_types=satisfied,
            uncertain_types=uncertain,
        )
