"""
constraint_guard.verifier.behavioral
=====================================
Behavioral verifier — runs a lightweight subprocess sandbox to observe
runtime behavior of generated Python code.

SECURITY NOTE:
This is a lightweight evaluation sandbox suitable for a hackathon /
development environment. It is NOT a hardened security boundary. Do not
use it in production without proper sandboxing (containers, seccomp, etc.).

Isolation measures used:
  - Temporary directory (cleaned up after each run)
  - subprocess.run() with timeout
  - Sanitized environment (no PYTHONPATH, minimal PATH)
  - Captured stdout / stderr (no interactive input)

Outputs Evidence objects with verifier="behavioral".

Currently supported behavioral constraint patterns:
  ERROR_HANDLING — "Return None for empty", "Raise ValueError for empty",
                   "Handle empty list gracefully"
  All others     — UNCERTAIN
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
import textwrap
from typing import Optional

from ..models import Constraint, ConstraintType, Evidence


# ---------------------------------------------------------------------------
# Evidence factories
# ---------------------------------------------------------------------------

def _uncertain(constraint_id: str, message: str) -> Evidence:
    return Evidence(
        constraint_id=constraint_id,
        verifier="behavioral",
        passed=False,
        confidence=0.0,
        message=message,
        metadata={"status": "uncertain"},
    )


def _violated(constraint_id: str, message: str, confidence: float = 0.90) -> Evidence:
    return Evidence(
        constraint_id=constraint_id,
        verifier="behavioral",
        passed=False,
        confidence=confidence,
        message=message,
        metadata={"status": "violated"},
    )


def _satisfied(constraint_id: str, message: str, confidence: float = 0.88) -> Evidence:
    return Evidence(
        constraint_id=constraint_id,
        verifier="behavioral",
        passed=True,
        confidence=confidence,
        message=message,
        metadata={"status": "satisfied"},
    )


# ---------------------------------------------------------------------------
# Function name extraction
# ---------------------------------------------------------------------------

def _extract_function_name(code: str) -> Optional[str]:
    """Return the name of the first function defined in *code*, or None."""
    try:
        tree = ast.parse(textwrap.dedent(code))
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node.name
    return None


# ---------------------------------------------------------------------------
# Subprocess execution
# ---------------------------------------------------------------------------

_HARNESS_TEMPLATE = """\
import sys as _sys

# --- User Code (unmodified) ---
{code}
# --- End User Code ---

_func = {func_name}

try:
    _result = _func([])
    print(f"BEHAVIORAL:returned:{{_result!r}}")
except Exception as _exc:
    print(f"BEHAVIORAL:raised:{{type(_exc).__name__}}:{{_exc!r}}")
"""

_TIMEOUT_SECONDS = 5.0


def _run_harness(code: str, func_name: str) -> tuple[str, str, int]:
    """
    Write and execute the behavioral harness in a temporary directory.

    Returns (stdout, stderr, returncode).
    returncode == -999 signals a timeout.
    """
    harness = _HARNESS_TEMPLATE.format(
        code=textwrap.dedent(code),
        func_name=func_name,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = os.path.join(tmpdir, "constraint_guard_btest.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(harness)

        # Minimal environment: inherit only PATH, strip PYTHONPATH
        env = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),  # needed on Windows
            "TEMP": tmpdir,
            "TMP": tmpdir,
        }

        try:
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
                cwd=tmpdir,
                env=env,
            )
            return result.stdout.strip(), result.stderr.strip(), result.returncode
        except subprocess.TimeoutExpired:
            return "", "TIMEOUT", -999


def _parse_harness_output(stdout: str) -> dict:
    """
    Parse the harness output line starting with "BEHAVIORAL:".

    Returns dict with keys: "event", "value", "exc_type" (optional).
    """
    for line in stdout.splitlines():
        if line.startswith("BEHAVIORAL:"):
            parts = line.split(":", 3)
            if len(parts) >= 3:
                event = parts[1]  # "returned" or "raised"
                value = parts[2] if len(parts) > 2 else ""
                exc_detail = parts[3] if len(parts) > 3 else ""
                return {"event": event, "value": value, "detail": exc_detail}
    return {}


# ---------------------------------------------------------------------------
# Per-constraint behavioral verifiers
# ---------------------------------------------------------------------------

def _verify_error_handling_behavioral(constraint: Constraint, code: str) -> Evidence:
    cid = constraint.id
    text = constraint.text.lower()

    func_name = _extract_function_name(code)
    if not func_name:
        return _uncertain(cid, "Could not extract a function name from code.")

    stdout, stderr, returncode = _run_harness(code, func_name)

    if returncode == -999:
        return _uncertain(
            cid,
            f"Behavioral test timed out after {_TIMEOUT_SECONDS}s; cannot verify.",
        )

    if stderr and "SyntaxError" in stderr:
        return _uncertain(cid, f"Code has a syntax error: {stderr[:120]}")

    parsed = _parse_harness_output(stdout)
    if not parsed:
        # Possibly a crash in user code before the harness could print
        err_preview = stderr[:120] if stderr else "(no stderr)"
        return _uncertain(
            cid,
            f"Behavioral harness produced no parseable output. stderr: {err_preview}",
        )

    event = parsed.get("event", "")
    value = parsed.get("value", "")
    exc_detail = parsed.get("detail", "")

    # "Return None for empty input" / "Return None for empty list"
    if ("return none" in text or "return null" in text or "returns none" in text):
        if event == "returned" and value == "None":
            return _satisfied(
                cid,
                f"Function '{func_name}' returned None for empty list input.",
                confidence=0.93,
            )
        elif event == "raised":
            return _violated(
                cid,
                f"Function '{func_name}' raised {value} instead of returning None.",
                confidence=0.92,
            )
        else:
            return _violated(
                cid,
                f"Function '{func_name}' returned {value!r} instead of None.",
                confidence=0.88,
            )

    # "Raise ValueError for empty input"
    if "raise valueerror" in text.replace(" ", "") or (
        "raise" in text and "valueerror" in text
    ):
        if event == "raised" and value == "ValueError":
            return _satisfied(
                cid,
                f"Function '{func_name}' raised ValueError for empty input as required.",
                confidence=0.93,
            )
        elif event == "returned":
            return _violated(
                cid,
                f"Function '{func_name}' returned {value!r} instead of raising ValueError.",
                confidence=0.90,
            )
        else:
            return _violated(
                cid,
                f"Function '{func_name}' raised {value} (expected ValueError).",
                confidence=0.85,
            )

    # "Handle empty list gracefully" / "Handle an empty list"
    if "handle" in text and ("empty" in text or "gracefully" in text):
        crash_types = {"RuntimeError", "AttributeError", "TypeError", "IndexError",
                       "NameError", "ZeroDivisionError", "OverflowError"}
        if event == "raised" and value in crash_types:
            return _violated(
                cid,
                f"Function '{func_name}' crashed with {value} on empty input.",
                confidence=0.90,
            )
        # Any non-crash outcome (return or graceful exception like ValueError) is acceptable
        return _satisfied(
            cid,
            f"Function '{func_name}' handled empty input without crashing "
            f"(event={event}, value={value!r}).",
            confidence=0.80,
        )

    return _uncertain(
        cid,
        f"Behavioral verifier could not map text to a known test pattern. "
        f"Harness result: event={event!r}, value={value!r}.",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def verify(constraint: Constraint, code: str) -> Evidence:
    """
    Verify *constraint* against *code* by executing a sandboxed behavioral test.

    Returns a single Evidence object.  Unsupported constraint types receive
    an UNCERTAIN result rather than a false SATISFIED.
    """
    if constraint.type == ConstraintType.ERROR_HANDLING:
        return _verify_error_handling_behavioral(constraint, code)

    return _uncertain(
        constraint.id,
        f"Behavioral verifier not applicable for constraint type '{constraint.type.value}'. "
        "No behavioral test is defined for this category.",
    )
