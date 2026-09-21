"""
constraint_guard.llm.prompts
============================
System prompts and user prompt formatting utilities for code generation and repair.
"""

from typing import Any, Dict, List

CODE_GENERATION_SYSTEM_PROMPT = """\
You are an expert Python software engineer.
Generate clean, production-grade, bug-free Python code strictly fulfilling the user's conversation requirements.
OUTPUT FORMAT: Return ONLY valid Python code inside a ```python ``` code block. Do not include markdown explanations outside the code block.
"""

REPAIR_SYSTEM_PROMPT = """\
You are an expert Python code repair engine.
Your goal is to modify the provided Python code to satisfy ALL active constraints while preserving satisfied behavior.

CRITICAL OUTPUT FORMAT REQUIREMENTS:
- Output ONLY valid, executable Python source code inside a ```python ``` code block.
- Do NOT output type signature descriptions (e.g. Union[...]), docstring specification blocks (e.g. Raises/Returns/Parameters), preamble text, markdown explanations, or prose commentary outside or inside the code block.
- Return ONLY clean Python code.
"""


def build_code_generation_prompt(conversation: List[Dict[str, Any]]) -> str:
    """Format conversation turns into a code generation user prompt."""
    prompt_lines = [
        "Please write Python code based on the following multi-turn user conversation history:\n"
    ]
    for turn in conversation:
        t_num = turn.get("turn", turn.get("turn_id", 1))
        text = turn.get("text", turn.get("content", ""))
        prompt_lines.append(f"Turn {t_num}: {text}")

    prompt_lines.append(
        "\nInstruction: Write Python code that satisfies all active requirements from this conversation history."
    )
    prompt_lines.append("Return ONLY the Python code in a ```python ... ``` block.")
    return "\n".join(prompt_lines)


def build_repair_prompt(
    conversation: List[Dict[str, Any]],
    code: str,
    active_constraints: List[Any],
    violated_results: List[Any],
) -> str:
    """Format prompt for repairing code that violated constraints."""
    prompt_lines = [
        "The generated Python code failed verification against active user requirements.\n",
        "=== ORIGINAL CONVERSATION ===",
    ]
    for turn in conversation:
        t_num = turn.get("turn", turn.get("turn_id", 1))
        text = turn.get("text", turn.get("content", ""))
        prompt_lines.append(f"Turn {t_num}: {text}")

    prompt_lines.append("\n=== ACTIVE CONSTRAINTS ===")
    for c in active_constraints:
        c_id = getattr(c, "id", "C")
        c_type = getattr(getattr(c, "type", None), "value", str(getattr(c, "type", "")))
        c_text = getattr(c, "text", str(c))
        prompt_lines.append(f"- [{c_id}] ({c_type}): {c_text}")

    prompt_lines.append("\n=== CURRENT GENERATED CODE ===")
    prompt_lines.append(f"```python\n{code.strip()}\n```")

    prompt_lines.append("\n=== VERIFICATION VIOLATIONS & EVIDENCE ===")
    for res in violated_results:
        c_id = getattr(res, "constraint_id", "C")
        ev_strings = []
        for ev in getattr(res, "evidences", []):
            line_str = f" [Line {ev.line_number}]" if getattr(ev, "line_number", None) is not None else ""
            ev_strings.append(f"{ev.message}{line_str}")
        ev_msg = " | ".join(ev_strings) if ev_strings else "Constraint violated"
        prompt_lines.append(f"Constraint {c_id} VIOLATED: {ev_msg}")

    prompt_lines.append("\n=== REPAIR INSTRUCTION ===")
    prompt_lines.append(
        "Modify the code so that ALL VIOLATED constraints are resolved and ALL ACTIVE constraints are satisfied."
    )
    prompt_lines.append(
        "IMPORTANT: Return ONLY the repaired Python code inside a ```python ``` block. "
        "Do NOT include explanations, markdown text outside the code block, type specifications (e.g. Union[...]), or docstring fragments."
    )

    return "\n".join(prompt_lines)

