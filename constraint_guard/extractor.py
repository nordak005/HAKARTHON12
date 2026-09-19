"""
constraint_guard.extractor
==========================
Deterministic, rule-based constraint extractor.

Parses ordered conversation turns and returns a list of Constraint objects.
No LLM API is used — all logic is regex + keyword heuristics.

Turn format expected by extract():
    [{"turn": 1, "text": "..."}, {"turn": 2, "text": "..."}, ...]
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .models import Constraint, ConstraintType, ConstraintStatus


# ---------------------------------------------------------------------------
# Continuation-phrase detection
# Turns that only reinforce earlier constraints should be flagged so the
# graph builder can add REINFORCES edges instead of creating new constraints.
# ---------------------------------------------------------------------------

_CONTINUATION_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bkeep\b.{0,30}\bprevious\b", re.I),
    re.compile(r"\bretain\b.{0,30}\bprevious\b", re.I),
    re.compile(r"\bsame\b.{0,20}\brestrictions?\b", re.I),
    re.compile(r"\bsame\b.{0,20}\brequirements?\b", re.I),
    re.compile(r"\bprevious\b.{0,20}\brestrictions?\b", re.I),
    re.compile(r"\bprevious\b.{0,20}\brequirements?\b", re.I),
    re.compile(r"\bkeep\b.{0,20}\brestrictions?\b", re.I),
    re.compile(r"\bkeep\b.{0,20}\brules?\b", re.I),
    re.compile(r"\bstill\b.{0,15}\bapply\b", re.I),
    re.compile(r"\bno\s+changes?\s+to\s+the\s+requirements?\b", re.I),
]


def is_continuation(text: str) -> bool:
    """Return True if the turn is purely a continuation/reinforcement phrase."""
    stripped = text.strip()
    return any(p.search(stripped) for p in _CONTINUATION_PATTERNS)


# ---------------------------------------------------------------------------
# Per-type extraction rules
# Each rule is a (pattern, confidence, target_group) tuple.
# target_group is the regex group index that captures the specific target
# (builtin name, function name, etc.), or None if not applicable.
# ---------------------------------------------------------------------------

@dataclass
class _Rule:
    pattern:      re.Pattern
    ctype:        ConstraintType
    confidence:   float
    target_group: Optional[int] = None        # regex group that holds target


def _build_rules() -> list[_Rule]:
    R = _Rule
    C = ConstraintType

    return [
        # ------------------------------------------------------------------ ALGORITHM (negation first — highest priority for recursion/iteration)
        # "do not use recursion"  /  "don't use recursion"
        R(re.compile(
            r"\b(?:do\s+not|don'?t|avoid|no)\s+(?:use\s+)?(recursion|recursive|recurse)\b",
            re.I), C.ALGORITHM, 0.97, 1),   # higher than NO_BUILTIN (0.95) so it wins
        # "do not use loops"  /  "no iteration"
        R(re.compile(
            r"\b(?:do\s+not|don'?t|avoid|no)\s+(?:use\s+)?(loop|loops|iteration|iterative)\b",
            re.I), C.ALGORITHM, 0.95, 1),
        # "use recursion"
        R(re.compile(
            r"\buse\s+(recursion|recursive\s+approach|recursion\s+only)\b",
            re.I), C.ALGORITHM, 0.92, 1),
        # "use iteration"  /  "use a loop"
        R(re.compile(
            r"\buse\s+(iteration|iterative\s+approach|a?\s*loop)\b",
            re.I), C.ALGORITHM, 0.90, 1),
        # "implement recursively"
        R(re.compile(
            r"\bimplement\s+(?:it\s+)?(recursively)\b",
            re.I), C.ALGORITHM, 0.88, 1),
        # "implement iteratively"
        R(re.compile(
            r"\bimplement\s+(?:it\s+)?(iteratively)\b",
            re.I), C.ALGORITHM, 0.88, 1),

        # ------------------------------------------------------------------ NO_BUILTIN
        # "avoid using numpy" / "avoid numpy" (standalone avoid, no 'use' required)
        R(re.compile(
            r"\bavoid\s+(?:using\s+)?([A-Za-z_][A-Za-z0-9_.]+)\b",
            re.I), C.NO_BUILTIN, 0.90, 1),
        # "do not use max()"  /  "don't use sorted()"  /  "do not use the max function"
        # Use direct token capture: 'use (?:the )? TOKEN' so group(1) is always the name
        R(re.compile(
            r"\b(?:do\s+not|don'?t|never)\s+use\s+(?:the\s+)?([A-Za-z_][A-Za-z0-9_.]*)\s*\(?",
            re.I), C.NO_BUILTIN, 0.95, 1),
        # "do not use the max function"  (explicit function/method suffix, also fires with above)
        R(re.compile(
            r"\b(?:do\s+not|don'?t|avoid)\s+use\s+(?:the\s+)?([A-Za-z_][A-Za-z0-9_]*)\s+(?:function|method|builtin|built-in)",
            re.I), C.NO_BUILTIN, 0.95, 1),
        # "without using max"  /  "without max()"
        R(re.compile(
            r"\bwithout\s+(?:using\s+)?([A-Za-z_][A-Za-z0-9_.]*)\s*\(?",
            re.I), C.NO_BUILTIN, 0.90, 1),
        # "no use of max"  /  "no built-in max"
        R(re.compile(
            r"\bno\s+(?:use\s+of|builtin\s+|built-in\s+)([A-Za-z_][A-Za-z0-9_.]*)\s*\(?",
            re.I), C.NO_BUILTIN, 0.88, 1),



        # ------------------------------------------------------------------ ERROR_HANDLING
        R(re.compile(
            r"\bhandle\s+(?:an?\s+)?empty\b",
            re.I), C.ERROR_HANDLING, 0.92),
        R(re.compile(
            r"\breturn\s+(?:None|null|empty|\"\"|-1)\s+(?:for|if|when)\s+(?:empty|no|zero)",
            re.I), C.ERROR_HANDLING, 0.90),
        R(re.compile(
            r"\braise\s+([A-Za-z][A-Za-z0-9_]*Error)\b",
            re.I), C.ERROR_HANDLING, 0.92, 1),
        R(re.compile(
            r"\bthrow\s+(?:an?\s+)?([A-Za-z][A-Za-z0-9_]*(?:Error|Exception))\b",
            re.I), C.ERROR_HANDLING, 0.90, 1),
        R(re.compile(
            r"\bif\s+(?:the\s+)?(?:list\s+is\s+empty|input\s+is\s+(?:empty|None|null))\b",
            re.I), C.ERROR_HANDLING, 0.85),
        R(re.compile(
            r"\bhandle\s+(?:edge|error|exception|invalid)\s+case\b",
            re.I), C.ERROR_HANDLING, 0.82),
        R(re.compile(
            r"\bgracefully\s+handle\b",
            re.I), C.ERROR_HANDLING, 0.80),

        # ------------------------------------------------------------------ STRUCTURE
        R(re.compile(r"\buse\s+a\s+class\b", re.I), C.STRUCTURE, 0.92),
        R(re.compile(r"\buse\s+(?:a\s+)?single\s+function\b", re.I), C.STRUCTURE, 0.90),
        R(re.compile(r"\bno\s+classes?\b", re.I), C.STRUCTURE, 0.88),
        R(re.compile(r"\bdo\s+not\s+use\s+(?:a\s+)?class\b", re.I), C.STRUCTURE, 0.88),
        R(re.compile(r"\buse\s+(?:a\s+)?module\b", re.I), C.STRUCTURE, 0.82),
        R(re.compile(r"\bseparate\s+(?:the\s+)?functions?\b", re.I), C.STRUCTURE, 0.78),

        # ------------------------------------------------------------------ NAMING
        R(re.compile(
            r"\b(?:name|call)\s+(?:it\s+|the\s+function\s+)?[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?",
            re.I), C.NAMING, 0.92, 1),
        R(re.compile(
            r"\bfunction\s+should\s+be\s+called\s+[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?",
            re.I), C.NAMING, 0.92, 1),
        R(re.compile(
            r"\bfunction\s+(?:named?|called?)\s+[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?",
            re.I), C.NAMING, 0.88, 1),

        # ------------------------------------------------------------------ SIGNATURE
        R(re.compile(r"\baccept\s+a\s+list\b", re.I), C.SIGNATURE, 0.88),
        R(re.compile(r"\btakes?\s+a\s+list\b", re.I), C.SIGNATURE, 0.85),
        R(re.compile(r"\breturn\s+an?\s+int(?:eger)?\b", re.I), C.SIGNATURE, 0.88),
        R(re.compile(r"\breturn\s+a\s+(?:string|str|list|dict|bool|float|tuple)\b", re.I),
          C.SIGNATURE, 0.88),
        R(re.compile(r"\bshould\s+return\b.{0,40}", re.I), C.SIGNATURE, 0.75),
        R(re.compile(r"\bparameter(?:s)?\s+should\s+be\b", re.I), C.SIGNATURE, 0.78),

        # ------------------------------------------------------------------ COMPLEXITY
        R(re.compile(r"\bO\s*\(\s*(?:[0-9a-z\s*+^log]+)\s*\)", re.I), C.COMPLEXITY, 0.95),
        R(re.compile(r"\blinear\s+time\b", re.I), C.COMPLEXITY, 0.90),
        R(re.compile(r"\bconstant\s+(?:time|space)\b", re.I), C.COMPLEXITY, 0.90),
        R(re.compile(r"\bquadratic\s+time\b", re.I), C.COMPLEXITY, 0.88),
        R(re.compile(r"\blogarithmic\s+time\b", re.I), C.COMPLEXITY, 0.88),
        R(re.compile(r"\btime\s+complexity\s+(?:of|should\s+be)\b", re.I), C.COMPLEXITY, 0.85),
    ]


_RULES: list[_Rule] = _build_rules()

# Patterns that indicate a general requirement if nothing else matched
_GENERAL_INDICATORS: list[re.Pattern] = [
    re.compile(r"\b(?:make|ensure|should|must|require)\b", re.I),
    re.compile(r"\bdo\s+not\b", re.I),
    re.compile(r"\bdon'?t\b", re.I),
    re.compile(r"\bwithout\b", re.I),
    re.compile(r"\bavoid\b", re.I),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_target(raw: Optional[str]) -> Optional[str]:
    """Strip punctuation / common noise words from a captured target."""
    if not raw:
        return None
    raw = raw.strip().strip("\"'.,;:!")
    noise = {"the", "a", "an", "it", "function", "method"}
    if raw.lower() in noise or len(raw) < 2:
        return None
    return raw


# Algorithm keyword sets used to detect cross-type priority conflicts.
# If text matches ALGORITHM keywords, the NO_BUILTIN match for that same word
# should be suppressed (e.g. "do not use recursion" is ALGORITHM, not NO_BUILTIN).
_ALGO_KEYWORDS = re.compile(
    r"\b(?:recursion|recursive|recurse|iteration|iterative|loop)\b", re.I
)


def _extract_from_text(text: str, source_turn: int) -> list[Constraint]:
    """
    Apply all rules against a single turn's text.
    Returns deduplicated Constraint objects, one per matched type per turn.

    Priority rule: when ALGORITHM and NO_BUILTIN both fire on the same text
    that contains algorithm keywords (recursion, loop, etc.), keep only the
    higher-confidence match (ALGORITHM wins with confidence 0.97 vs 0.95).
    """
    matched_types: dict[ConstraintType, Constraint] = {}

    for rule in _RULES:
        m = rule.pattern.search(text)
        if not m:
            continue

        # Only keep the highest-confidence match per type per turn
        if rule.ctype in matched_types:
            existing = matched_types[rule.ctype]
            if existing.confidence >= rule.confidence:
                continue

        target: Optional[str] = None
        if rule.target_group is not None:
            try:
                raw = m.group(rule.target_group)
                target = _clean_target(raw)
            except IndexError:
                pass

        c = Constraint(
            text=text.strip(),
            type=rule.ctype,
            source_turn=source_turn,
            status=ConstraintStatus.ACTIVE,
            target=target,
            confidence=rule.confidence,
            evidence=[f"pattern matched: {rule.pattern.pattern[:60]}"],
        )
        matched_types[rule.ctype] = c

    # Cross-type dedup: if text contains algorithm keywords and both
    # ALGORITHM and NO_BUILTIN fired, keep only the higher-confidence one.
    if (
        ConstraintType.ALGORITHM in matched_types
        and ConstraintType.NO_BUILTIN in matched_types
        and _ALGO_KEYWORDS.search(text)
    ):
        algo_conf = matched_types[ConstraintType.ALGORITHM].confidence
        builtin_conf = matched_types[ConstraintType.NO_BUILTIN].confidence
        if algo_conf >= builtin_conf:
            del matched_types[ConstraintType.NO_BUILTIN]
        else:
            del matched_types[ConstraintType.ALGORITHM]

    # If nothing matched but the text looks like a requirement, store as GENERAL
    if not matched_types and any(p.search(text) for p in _GENERAL_INDICATORS):
        matched_types[ConstraintType.GENERAL] = Constraint(
            text=text.strip(),
            type=ConstraintType.GENERAL,
            source_turn=source_turn,
            status=ConstraintStatus.ACTIVE,
            target=None,
            confidence=0.60,
            evidence=["general requirement indicator matched"],
        )

    return list(matched_types.values())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class ExtractionResult:
    """
    Full result of constraint extraction over a conversation.

    Attributes
    ----------
    constraints         : All extracted Constraint objects.
    continuation_turns  : Turn numbers that were identified as pure continuations.
    """
    constraints:        list[Constraint] = field(default_factory=list)
    continuation_turns: list[int]        = field(default_factory=list)


def extract(conversation: list[dict]) -> ExtractionResult:
    """
    Extract constraints from an ordered list of conversation turns.

    Parameters
    ----------
    conversation : list of dicts with keys "turn" (int) and "text" (str).

    Returns
    -------
    ExtractionResult with .constraints and .continuation_turns.
    """
    constraints: list[Constraint] = []
    continuation_turns: list[int] = []

    for entry in conversation:
        turn_num: int = int(entry["turn"])
        text: str = str(entry["text"]).strip()

        if not text:
            continue

        if is_continuation(text):
            continuation_turns.append(turn_num)
            continue

        extracted = _extract_from_text(text, source_turn=turn_num)
        constraints.extend(extracted)

    return ExtractionResult(
        constraints=constraints,
        continuation_turns=continuation_turns,
    )
