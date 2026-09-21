"""
constraint_guard.llm.parser
===========================
Robust parser for extracting Python code from raw LLM completions.
"""

import re


import ast
import re
from typing import List, Optional


def _try_parse_ast(source: str) -> bool:
    """Return True if source string is syntactically valid Python AST."""
    if not source or not source.strip():
        return False
    try:
        ast.parse(source)
        return True
    except SyntaxError:
        return False


def _sanitize_python_lines(raw_code: str) -> str:
    """Sanitize extracted python text by removing leading/trailing non-code prose or docstring/type fragments."""
    if not raw_code or not raw_code.strip():
        return ""

    lines = raw_code.strip().splitlines()

    # Primary code construct starters (functions, classes, decorators, imports)
    primary_starters = (
        "def ",
        "async def ",
        "class ",
        "@",
        "import ",
        "from ",
    )

    # Secondary code construct starters
    secondary_starters = (
        "if ",
        "for ",
        "while ",
        "try:",
        "with ",
        "return ",
        "#",
    )

    # Find candidate start line indices for primary starters first
    candidate_starts: List[int] = []
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if any(stripped.startswith(starter) for starter in primary_starters):
            candidate_starts.append(idx)

    # If no primary starters found, look for secondary starters
    if not candidate_starts:
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if any(stripped.startswith(starter) for starter in secondary_starters):
                candidate_starts.append(idx)

    # Always append index 0 as a last fallback candidate option
    if 0 not in candidate_starts:
        candidate_starts.append(0)

    # 1. Try candidate start lines with AST validation
    for start_idx in candidate_starts:
        sub_lines = lines[start_idx:]
        sub_text = "\n".join(sub_lines).strip()
        if not sub_text:
            continue

        if _try_parse_ast(sub_text):
            return sub_text

        # If sub_text fails due to trailing prose, try trimming lines from end
        for end_idx in range(len(sub_lines), 0, -1):
            trimmed_text = "\n".join(sub_lines[:end_idx]).strip()
            if trimmed_text and _try_parse_ast(trimmed_text):
                return trimmed_text

    # 2. Fallback: Filter leading prose up to first primary/secondary starter
    all_starters = primary_starters + secondary_starters
    cleaned_lines = []
    in_code = False
    for line in lines:
        stripped = line.strip()
        if any(stripped.startswith(starter) for starter in all_starters):
            in_code = True
        if in_code:
            cleaned_lines.append(line)

    if cleaned_lines:
        return "\n".join(cleaned_lines).strip()

    return raw_code.strip()



def extract_python_code(llm_output: str) -> str:
    """Extract Python source code from LLM string output.

    Handles:
    - ```python ... ``` code blocks
    - ``` ... ``` generic code blocks
    - Raw unformatted Python code
    - Cleans out leading docstring fragments (e.g. Union[...], Raises/ValueError),
      markdown headers, preambles, and trailing explanations.
    """
    if not llm_output or not llm_output.strip():
        return ""

    text = llm_output.strip()

    # 1. Search for explicit ```python ... ``` blocks
    pattern_py = r"```python\s*\n?(.*?)\n?\s*```"
    matches_py = re.findall(pattern_py, text, re.DOTALL | re.IGNORECASE)
    if matches_py:
        for match in matches_py:
            sanitized = _sanitize_python_lines(match)
            if "def " in sanitized or "class " in sanitized or _try_parse_ast(sanitized):
                return sanitized
        return _sanitize_python_lines(matches_py[0])

    # 2. Search for generic ``` ... ``` blocks
    pattern_generic = r"```\s*\n?(.*?)\n?\s*```"
    matches_generic = re.findall(pattern_generic, text, re.DOTALL)
    if matches_generic:
        for match in matches_generic:
            sanitized = _sanitize_python_lines(match)
            if "def " in sanitized or "class " in sanitized or _try_parse_ast(sanitized):
                return sanitized
        return _sanitize_python_lines(matches_generic[0])

    # 3. Handle raw unformatted output without code block backticks
    return _sanitize_python_lines(text)

