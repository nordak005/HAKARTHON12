"""
constraint_guard.verifier.lexical
==================================
Lexical verifier — token-level inspection of generated Python code.

Uses Python's tokenize module so that occurrences inside strings, comments,
and multi-line continuations are correctly classified.

Outputs Evidence objects with verifier="lexical".

Status convention (stored in Evidence.metadata["status"]):
  "satisfied"  → passed=True,  evidence supports constraint is met
  "violated"   → passed=False, evidence of a definite violation
  "uncertain"  → passed=False, confidence=0.0, cannot determine
"""

from __future__ import annotations

import io
import tokenize
from typing import Optional

from ..models import Constraint, ConstraintType, Evidence


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uncertain(constraint_id: str, message: str) -> Evidence:
    return Evidence(
        constraint_id=constraint_id,
        verifier="lexical",
        passed=False,
        confidence=0.0,
        message=message,
        metadata={"status": "uncertain"},
    )


def _violated(
    constraint_id: str,
    message: str,
    line_number: Optional[int] = None,
    code_snippet: Optional[str] = None,
    confidence: float = 0.95,
) -> Evidence:
    return Evidence(
        constraint_id=constraint_id,
        verifier="lexical",
        passed=False,
        confidence=confidence,
        message=message,
        line_number=line_number,
        code_snippet=code_snippet,
        metadata={"status": "violated"},
    )


def _satisfied(
    constraint_id: str,
    message: str,
    confidence: float = 0.80,
) -> Evidence:
    return Evidence(
        constraint_id=constraint_id,
        verifier="lexical",
        passed=True,
        confidence=confidence,
        message=message,
        metadata={"status": "satisfied"},
    )


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def _tokenize_code(code: str) -> list[tokenize.TokenInfo]:
    """
    Tokenize Python source code.  Returns an empty list if code cannot
    be tokenized (e.g. syntax errors).
    """
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(code).readline))
        return tokens
    except tokenize.TokenError:
        return []


def _find_calls(tokens: list[tokenize.TokenInfo]) -> list[tuple[str, int]]:
    """
    Find all function / builtin calls in the token stream.

    Returns a list of (name, line_number) for every NAME token that is
    immediately followed by a LPAR ('(') token.
    This avoids false positives from identifiers that merely share a name
    with a builtin.
    """
    calls: list[tuple[str, int]] = []
    for i, tok in enumerate(tokens):
        if tok.type == tokenize.NAME:
            # Look ahead for '('
            j = i + 1
            while j < len(tokens) and tokens[j].type in (tokenize.NL, tokenize.NEWLINE,
                                                          tokenize.COMMENT, tokenize.INDENT,
                                                          tokenize.DEDENT):
                j += 1
            if j < len(tokens) and tokens[j].type == tokenize.OP and tokens[j].string == "(":
                calls.append((tok.string, tok.start[0]))
    return calls


def _find_imports(tokens: list[tokenize.TokenInfo]) -> list[tuple[str, int]]:
    """
    Find all top-level import names: `import X`, `from X import ...`.
    Returns a list of (module_name, line_number).
    """
    imports: list[tuple[str, int]] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == tokenize.NAME and tok.string == "import":
            # import X[, Y, ...]
            line = tok.start[0]
            i += 1
            while i < len(tokens) and tokens[i].type in (tokenize.NAME, tokenize.OP, tokenize.NL):
                if tokens[i].type == tokenize.NAME and tokens[i].string not in ("as",):
                    imports.append((tokens[i].string, line))
                if tokens[i].type == tokenize.NEWLINE:
                    break
                i += 1
        elif tok.type == tokenize.NAME and tok.string == "from":
            # from X import ...
            line = tok.start[0]
            i += 1
            if i < len(tokens) and tokens[i].type == tokenize.NAME:
                imports.append((tokens[i].string, line))
        i += 1
    return imports


def _first_call_line(
    calls: list[tuple[str, int]],
    name: str,
    code_lines: list[str],
) -> tuple[Optional[int], Optional[str]]:
    """Return (line_number, snippet) for the first call matching *name*."""
    for call_name, lineno in calls:
        if call_name == name:
            snippet = code_lines[lineno - 1].strip() if lineno <= len(code_lines) else None
            return lineno, snippet
    return None, None


# ---------------------------------------------------------------------------
# Per-constraint-type verifiers
# ---------------------------------------------------------------------------

def _verify_no_builtin(constraint: Constraint, code: str) -> Evidence:
    """
    Verify a NO_BUILTIN constraint via token scanning.

    Checks for function calls with the forbidden name AND for bare
    import statements that import the forbidden module.
    """
    cid = constraint.id
    target = constraint.target

    if not target:
        return _uncertain(cid, "NO_BUILTIN constraint has no extracted target name.")

    tokens = _tokenize_code(code)
    if not tokens:
        return _uncertain(cid, "Code could not be tokenized (possible syntax error).")

    code_lines = code.splitlines()
    calls = _find_calls(tokens)
    imports = _find_imports(tokens)

    # Check for function call matching target
    lineno, snippet = _first_call_line(calls, target, code_lines)
    if lineno is not None:
        return _violated(
            cid,
            f"Forbidden call '{target}()' found at line {lineno}.",
            line_number=lineno,
            code_snippet=snippet,
            confidence=0.97,
        )

    # Check for import of the forbidden module (e.g. "avoid using numpy")
    for mod_name, iline in imports:
        if mod_name == target:
            isnippet = code_lines[iline - 1].strip() if iline <= len(code_lines) else None
            return _violated(
                cid,
                f"Forbidden import '{target}' found at line {iline}.",
                line_number=iline,
                code_snippet=isnippet,
                confidence=0.95,
            )

    return _satisfied(
        cid,
        f"No call or import of '{target}' found in code.",
        confidence=0.85,
    )


def _verify_algorithm_lexical(constraint: Constraint, code: str) -> Evidence:
    """
    Light lexical check for ALGORITHM constraints (recursion/iteration).

    Does NOT detect recursive calls structurally — that is left to the AST
    verifier.  Here we check for obvious lexical signals.
    """
    cid = constraint.id
    text = constraint.text.lower()
    tokens = _tokenize_code(code)
    if not tokens:
        return _uncertain(cid, "Code could not be tokenized.")

    # Determine expected direction
    if "not" in text or "don" in text or "avoid" in text or "no " in text:
        # Forbidden algorithm — lexical can't definitively detect absence; delegate to AST
        return _uncertain(cid, "Algorithm constraint (negated) — deferred to AST verifier.")
    else:
        # Positive algorithm requirement — lexical can't confirm structure; delegate
        return _uncertain(cid, "Algorithm constraint (positive) — deferred to AST verifier.")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def verify(constraint: Constraint, code: str) -> Evidence:
    """
    Verify *constraint* against *code* using lexical (token-level) analysis.

    Returns a single Evidence object.  Callers should always check
    evidence.metadata["status"] in {"satisfied","violated","uncertain"}.
    """
    if constraint.type == ConstraintType.NO_BUILTIN:
        return _verify_no_builtin(constraint, code)

    if constraint.type == ConstraintType.ALGORITHM:
        return _verify_algorithm_lexical(constraint, code)

    # All other types: not applicable at lexical level
    return _uncertain(
        constraint.id,
        f"Lexical verifier not applicable for constraint type '{constraint.type.value}'.",
    )
