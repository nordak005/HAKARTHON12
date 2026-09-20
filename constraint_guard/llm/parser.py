"""
constraint_guard.llm.parser
===========================
Robust parser for extracting Python code from raw LLM completions.
"""

import re


def extract_python_code(llm_output: str) -> str:
    """Extract Python source code from LLM string output.

    Handles:
    - ```python ... ``` code blocks
    - ``` ... ``` generic code blocks
    - Raw unformatted Python code
    """
    if not llm_output or not llm_output.strip():
        return ""

    text = llm_output.strip()

    # 1. Match explicit ```python ... ```
    pattern_py = r"```python\s*\n?(.*?)\n?\s*```"
    match_py = re.search(pattern_py, text, re.DOTALL | re.IGNORECASE)
    if match_py:
        return match_py.group(1).strip()

    # 2. Match generic ``` ... ```
    pattern_generic = r"```\s*\n?(.*?)\n?\s*```"
    match_generic = re.search(pattern_generic, text, re.DOTALL)
    if match_generic:
        return match_generic.group(1).strip()

    # 3. If lines start with python code constructs, return stripped text
    lines = text.splitlines()
    cleaned_lines = []
    in_code = False

    for line in lines:
        if line.strip().startswith(("def ", "class ", "import ", "from ", "#", "if ", "for ", "while ", "return ")):
            in_code = True
        if in_code:
            cleaned_lines.append(line)

    if cleaned_lines:
        return "\n".join(cleaned_lines).strip()

    return text
