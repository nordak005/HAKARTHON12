"""
constraint_guard.verifier.structural
=====================================
Structural verifier — Python AST-based analysis of generated code.

Uses Python's standard `ast` module (no external dependencies).

Supports:
  NO_BUILTIN     - Detect forbidden function calls via Call nodes
  ALGORITHM      - Detect recursion via self-referential Call nodes
  NAMING         - Verify FunctionDef names
  SIGNATURE      - Inspect function arguments
  STRUCTURE      - Detect presence / absence of ClassDef or FunctionDef
  COMPLEXITY     - Always UNCERTAIN (heuristic depth only, no proof)
  ERROR_HANDLING - Basic structural check for guard clauses
  GENERAL        - UNCERTAIN (no structural rule available)

Outputs Evidence objects with verifier="structural".
"""

from __future__ import annotations

import ast
import textwrap
from typing import Optional

from ..models import Constraint, ConstraintType, Evidence


# ---------------------------------------------------------------------------
# Evidence factories (mirrors lexical.py conventions)
# ---------------------------------------------------------------------------

def _uncertain(constraint_id: str, message: str) -> Evidence:
    return Evidence(
        constraint_id=constraint_id,
        verifier="structural",
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
    ast_node_type: Optional[str] = None,
) -> Evidence:
    meta: dict = {"status": "violated"}
    if ast_node_type:
        meta["ast_node_type"] = ast_node_type
    return Evidence(
        constraint_id=constraint_id,
        verifier="structural",
        passed=False,
        confidence=confidence,
        message=message,
        line_number=line_number,
        code_snippet=code_snippet,
        metadata=meta,
    )


def _satisfied(
    constraint_id: str,
    message: str,
    confidence: float = 0.88,
    ast_node_type: Optional[str] = None,
) -> Evidence:
    meta: dict = {"status": "satisfied"}
    if ast_node_type:
        meta["ast_node_type"] = ast_node_type
    return Evidence(
        constraint_id=constraint_id,
        verifier="structural",
        passed=True,
        confidence=confidence,
        message=message,
        metadata=meta,
    )


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def _parse(code: str) -> Optional[ast.Module]:
    """Parse *code* into an AST, returning None on syntax error."""
    try:
        return ast.parse(textwrap.dedent(code))
    except SyntaxError:
        return None


def _get_code_line(code: str, lineno: int) -> Optional[str]:
    lines = code.splitlines()
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1].strip()
    return None


def _collect_calls(tree: ast.AST) -> list[ast.Call]:
    """Return all ast.Call nodes in *tree*."""
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call)]


def _call_name(call: ast.Call) -> Optional[str]:
    """
    Return the simple name of a Call's function if it is a bare name or an
    attribute access (e.g. itertools.chain → 'chain'), else None.
    """
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _function_defs(tree: ast.AST) -> list[ast.FunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _class_defs(tree: ast.AST) -> list[ast.ClassDef]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]


def _is_recursive(func_def: ast.FunctionDef) -> Optional[int]:
    """
    Return the line number of the first self-recursive Call inside *func_def*,
    or None if no recursion is detected.
    """
    func_name = func_def.name
    for node in ast.walk(func_def):
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name == func_name:
                return getattr(node, "lineno", None)
    return None


def _loop_nesting_depth(tree: ast.AST) -> int:
    """Return the maximum loop-nesting depth as a crude complexity heuristic."""
    max_depth = 0

    class DepthVisitor(ast.NodeVisitor):
        def __init__(self):
            self.depth = 0

        def visit_For(self, node):
            self.depth += 1
            nonlocal max_depth
            max_depth = max(max_depth, self.depth)
            self.generic_visit(node)
            self.depth -= 1

        def visit_While(self, node):
            self.depth += 1
            nonlocal max_depth
            max_depth = max(max_depth, self.depth)
            self.generic_visit(node)
            self.depth -= 1

    DepthVisitor().visit(tree)
    return max_depth


# ---------------------------------------------------------------------------
# Per-type verifiers
# ---------------------------------------------------------------------------

def _verify_no_builtin(constraint: Constraint, code: str, tree: ast.Module) -> Evidence:
    cid = constraint.id
    target = constraint.target
    if not target:
        return _uncertain(cid, "NO_BUILTIN constraint has no extracted target.")

    for call in _collect_calls(tree):
        name = _call_name(call)
        if name == target:
            lineno = getattr(call, "lineno", None)
            snippet = _get_code_line(code, lineno) if lineno else None
            return _violated(
                cid,
                f"Forbidden call '{target}()' found at line {lineno}.",
                line_number=lineno,
                code_snippet=snippet,
                confidence=0.97,
                ast_node_type="Call",
            )

    return _satisfied(
        cid,
        f"No AST Call node for '{target}' found in code.",
        confidence=0.90,
        ast_node_type="Call",
    )


def _verify_algorithm(constraint: Constraint, code: str, tree: ast.Module) -> Evidence:
    cid = constraint.id
    text = constraint.text.lower()
    funcs = _function_defs(tree)

    is_negated = any(w in text for w in ("not", "don't", "dont", "avoid", "no "))

    recursion_lines: list[int] = []
    for func_def in funcs:
        line = _is_recursive(func_def)
        if line is not None:
            recursion_lines.append(line)

    has_recursion = bool(recursion_lines)

    # "Use recursion" constraint
    if not is_negated and "recursion" in text:
        if has_recursion:
            return _satisfied(cid, f"Recursion detected in function(s) at line(s) {recursion_lines}.",
                              confidence=0.93, ast_node_type="Call")
        else:
            return _violated(cid, "No recursive function calls found; recursion required.",
                             confidence=0.88, ast_node_type="FunctionDef")

    # "Do not use recursion" constraint
    if is_negated and "recursion" in text:
        if has_recursion:
            lineno = recursion_lines[0]
            snippet = _get_code_line(code, lineno)
            return _violated(cid,
                             f"Recursive call found at line {lineno} (recursion forbidden).",
                             line_number=lineno, code_snippet=snippet, confidence=0.95,
                             ast_node_type="Call")
        else:
            return _satisfied(cid, "No recursive calls found; recursion is absent as required.",
                              confidence=0.90)

    # "Use iteration" / "do not use loops" — check for For/While nodes
    has_loop = bool([n for n in ast.walk(tree) if isinstance(n, (ast.For, ast.While))])

    if not is_negated and any(k in text for k in ("iteration", "loop", "iterative")):
        if has_loop:
            return _satisfied(cid, "Loop statement found; iteration is present as required.",
                              confidence=0.88)
        else:
            return _violated(cid, "No loop found; iteration required.", confidence=0.85)

    if is_negated and any(k in text for k in ("iteration", "loop", "iterative")):
        if has_loop:
            loop_lines = [getattr(n, "lineno", None)
                          for n in ast.walk(tree) if isinstance(n, (ast.For, ast.While))]
            return _violated(cid, f"Loop found at line(s) {loop_lines}; iteration forbidden.",
                             line_number=loop_lines[0] if loop_lines else None, confidence=0.90)
        else:
            return _satisfied(cid, "No loop found; iteration is absent as required.", confidence=0.88)

    return _uncertain(cid, "Could not classify algorithm constraint direction precisely.")


def _verify_naming(constraint: Constraint, code: str, tree: ast.Module) -> Evidence:
    cid = constraint.id
    expected_name = constraint.target
    if not expected_name:
        return _uncertain(cid, "NAMING constraint has no extracted target name.")

    func_defs = _function_defs(tree)
    for fd in func_defs:
        if fd.name == expected_name:
            return _satisfied(cid,
                              f"Function named '{expected_name}' found at line {fd.lineno}.",
                              confidence=0.97, ast_node_type="FunctionDef")

    found_names = [fd.name for fd in func_defs]
    return _violated(cid,
                     f"No function named '{expected_name}' found. Defined: {found_names}.",
                     confidence=0.93, ast_node_type="FunctionDef")


def _verify_signature(constraint: Constraint, code: str, tree: ast.Module) -> Evidence:
    cid = constraint.id
    text = constraint.text.lower()
    func_defs = _function_defs(tree)

    if not func_defs:
        return _uncertain(cid, "No function definition found in code.")

    func = func_defs[0]

    # Check "accept a list" / "takes a list"
    if "list" in text and ("accept" in text or "tak" in text or "parameter" in text):
        # Can't inspect runtime types but we can check arg count >= 1
        n_args = len(func.args.args)
        if n_args >= 1:
            return _satisfied(cid,
                              f"Function '{func.name}' accepts {n_args} argument(s); "
                              "list parameter likely present.",
                              confidence=0.70)
        else:
            return _violated(cid,
                             f"Function '{func.name}' accepts no arguments; list parameter missing.",
                             line_number=func.lineno, confidence=0.85)

    # "return an integer / string / list" — check return annotation if present
    if "return" in text:
        if func.returns:
            ann = ast.unparse(func.returns) if hasattr(ast, "unparse") else str(func.returns)
            return _satisfied(cid,
                              f"Return annotation '{ann}' found on function '{func.name}'.",
                              confidence=0.75)
        else:
            return _uncertain(cid,
                              f"No return type annotation on '{func.name}'; cannot confirm return type.")

    return _uncertain(cid, "Could not extract a checkable signature requirement.")


def _verify_structure(constraint: Constraint, code: str, tree: ast.Module) -> Evidence:
    cid = constraint.id
    text = constraint.text.lower()
    is_negated = any(w in text for w in ("not", "don't", "dont", "avoid", "no "))

    has_class = bool(_class_defs(tree))
    has_func = bool(_function_defs(tree))

    if "class" in text:
        if is_negated:
            if has_class:
                return _violated(cid, "Class definition found; classes are forbidden.",
                                 confidence=0.92, ast_node_type="ClassDef")
            return _satisfied(cid, "No class definition found; class use is absent as required.",
                              confidence=0.88)
        else:
            if has_class:
                return _satisfied(cid, "Class definition found as required.",
                                  confidence=0.93, ast_node_type="ClassDef")
            return _violated(cid, "No class definition found; class required.", confidence=0.90)

    if "single function" in text or ("function" in text and "single" in text):
        n_funcs = len(_function_defs(tree))
        if n_funcs == 1:
            return _satisfied(cid, f"Exactly one function definition found.", confidence=0.92)
        return _violated(cid, f"{n_funcs} function definitions found; single function required.",
                         confidence=0.88)

    return _uncertain(cid, "Could not map structure constraint to a checkable AST rule.")


def _verify_error_handling_structural(constraint: Constraint, code: str, tree: ast.Module) -> Evidence:
    cid = constraint.id
    text = constraint.text.lower()

    # Look for any guard clause: if not lst / if len == 0 / try-except / raise
    has_if_guard = any(
        isinstance(n, ast.If) for n in ast.walk(tree)
    )
    has_try = any(isinstance(n, ast.Try) for n in ast.walk(tree))
    has_raise = any(isinstance(n, ast.Raise) for n in ast.walk(tree))
    has_return_none = any(
        isinstance(n, ast.Return) and isinstance(n.value, ast.Constant) and n.value.value is None
        for n in ast.walk(tree)
    )

    if "raise" in text or "valueerror" in text.replace(" ", ""):
        if has_raise:
            return _satisfied(cid, "Raise statement found; error is raised as required.",
                              confidence=0.82, ast_node_type="Raise")
        return _violated(cid, "No raise statement found; ValueError/exception raise expected.",
                         confidence=0.78, ast_node_type="Raise")

    if "return none" in text or "return null" in text:
        if has_return_none:
            return _satisfied(cid, "Return None statement found.", confidence=0.82,
                              ast_node_type="Return")
        return _violated(cid, "No 'return None' statement found.", confidence=0.75)

    if "empty" in text or "gracefully" in text:
        has_guard = has_if_guard or has_try
        if has_guard:
            return _satisfied(cid,
                              "Guard clause (if/try) found; empty input likely handled.",
                              confidence=0.72)
        return _uncertain(cid, "No obvious guard clause; behavioral check recommended.")

    return _uncertain(cid, "Error-handling structural check inconclusive.")


def _verify_complexity(constraint: Constraint, code: str, tree: ast.Module) -> Evidence:
    """
    Complexity is fundamentally non-trivial to prove statically.
    Provide a heuristic loop-depth indicator but always mark as UNCERTAIN.
    """
    cid = constraint.id
    depth = _loop_nesting_depth(tree)
    return _uncertain(
        cid,
        f"Complexity analysis is heuristic only. "
        f"Maximum loop-nesting depth found: {depth}. "
        "Cannot prove time/space complexity statically.",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def verify(constraint: Constraint, code: str) -> Evidence:
    """
    Verify *constraint* against *code* using structural AST analysis.

    Returns a single Evidence object.
    """
    tree = _parse(code)
    if tree is None:
        return _uncertain(
            constraint.id,
            "Code has a syntax error; AST cannot be built.",
        )

    dispatch = {
        ConstraintType.NO_BUILTIN:     _verify_no_builtin,
        ConstraintType.ALGORITHM:      _verify_algorithm,
        ConstraintType.NAMING:         _verify_naming,
        ConstraintType.SIGNATURE:      _verify_signature,
        ConstraintType.STRUCTURE:      _verify_structure,
        ConstraintType.ERROR_HANDLING: _verify_error_handling_structural,
        ConstraintType.COMPLEXITY:     _verify_complexity,
    }

    handler = dispatch.get(constraint.type)
    if handler is None:
        return _uncertain(
            constraint.id,
            f"Structural verifier has no rule for constraint type '{constraint.type.value}'.",
        )

    return handler(constraint, code, tree)
