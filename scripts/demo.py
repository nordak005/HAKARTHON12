"""
scripts/demo.py
================
Live demo runner for ConstraintGuard.

Runs 3 scenarios for hackathon judges:
  Scenario A — VIOLATION (find_max with max() prohibited)
  Scenario B — SUPERSESSION (factorial recursion superseded by no-recursion)
  Scenario C — CONFLICT (return None vs raise ValueError for empty input)

Uses rich formatting for terminal output.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from constraint_guard.extractor import extract
from constraint_guard.graph import VersionedConstraintGraph
from constraint_guard.resolver import ConstraintResolver
from constraint_guard.verifier.engine import VerificationEngine


console = Console()


def run_scenario(
    scenario_id: str,
    title: str,
    conversation: list[dict],
    code: str,
) -> None:
    console.print()
    console.rule(f"[bold cyan]SCENARIO {scenario_id}: {title}[/bold cyan]")
    console.print()

    # 1. Print Conversation
    conv_text = Text()
    for turn in conversation:
        conv_text.append(f"Turn {turn['turn']}: ", style="bold yellow")
        conv_text.append(f"{turn['text']}\n")
    console.print(Panel(conv_text, title="[bold]CONVERSATION HISTORY[/bold]", border_style="yellow"))

    # Pipeline execution
    extracted_res = extract(conversation)
    graph = VersionedConstraintGraph.build_from_constraints(extracted_res.constraints)

    resolver = ConstraintResolver()
    state = resolver.resolve(graph)

    engine = VerificationEngine()
    all_c = graph.get_all_constraints()
    report = engine.verify(code, all_c)

    # 2. Print Active Constraints Table
    active_table = Table(title="ACTIVE CONSTRAINTS (Post-Resolution)", show_header=True, header_style="bold magenta")
    active_table.add_column("ID", style="dim", width=8)
    active_table.add_column("Type", style="cyan")
    active_table.add_column("Target", style="blue")
    active_table.add_column("Text", style="white")
    active_table.add_column("Turn", style="yellow", justify="center")

    for c in state.active:
        active_table.add_row(
            c.id,
            c.type.value,
            c.target or "-",
            c.text,
            str(c.source_turn),
        )
    console.print(active_table)

    # 3. Print Superseded Constraints
    if state.superseded:
        sup_table = Table(title="SUPERSEDED CONSTRAINTS (Obsolete)", show_header=True, header_style="bold dim")
        sup_table.add_column("ID", style="dim", width=8)
        sup_table.add_column("Type", style="dim")
        sup_table.add_column("Text", style="dim")
        sup_table.add_column("Reason", style="italic gray50")
        for c in state.superseded:
            sup_table.add_row(c.id, c.type.value, c.text, "Superseded by later turn requirement")
        console.print(sup_table)
    else:
        console.print("[dim]Superseded Constraints: None[/dim]")

    # 4. Print Conflicting Constraints
    if state.conflicting:
        conf_table = Table(title="CONFLICTING CONSTRAINTS (Unresolved Ambiguity)", show_header=True, header_style="bold red")
        conf_table.add_column("ID", style="bold red", width=8)
        conf_table.add_column("Type", style="red")
        conf_table.add_column("Text", style="red")
        for c in state.conflicting:
            conf_table.add_row(c.id, c.type.value, c.text)
        console.print(conf_table)
    else:
        console.print("[dim]Conflicting Constraints: None[/dim]")

    # 5. Print Generated Code
    syntax = Syntax(code.strip(), "python", theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title="[bold]GENERATED PYTHON CODE[/bold]", border_style="blue"))

    # 6. Print Verification Evidence & Per-Constraint Results
    ev_table = Table(title="HYBRID VERIFICATION RESULTS", show_header=True, header_style="bold green")
    ev_table.add_column("Constraint ID", style="dim")
    ev_table.add_column("Status", style="bold")
    ev_table.add_column("Lanes / Verifier", style="magenta")
    ev_table.add_column("Evidence & Line Numbers", style="white")

    for res in report.results:
        status_color = (
            "green" if res.status.value == "SATISFIED"
            else "red" if res.status.value == "VIOLATED"
            else "yellow"
        )
        status_text = f"[{status_color}]{res.status.value}[/{status_color}]"
        lanes = ", ".join(e.verifier for e in res.evidences) or "N/A"
        evidence_msgs = []
        for e in res.evidences:
            msg = e.message
            if e.line_number is not None:
                msg = f"[Line {e.line_number}] {msg}"
            evidence_msgs.append(msg)
        evidence_str = " | ".join(evidence_msgs) if evidence_msgs else "No evidence recorded"
        ev_table.add_row(res.constraint_id, status_text, lanes, evidence_str)

    console.print(ev_table)

    # 7. Final Overall Status
    final_label = "VERIFIED" if report.overall_status == "PASS" else "NOT VERIFIED"
    overall_color = "bold green" if report.overall_status == "PASS" else "bold red"
    summary_text = (
        f"Overall Status   : [{overall_color}]{final_label}[/{overall_color}]\n"
        f"Active Constraints : {len(state.active)}\n"
        f"Superseded       : {len(state.superseded)}\n"
        f"Conflicting      : {len(state.conflicting)}"
    )
    console.print(Panel(summary_text, title="[bold]FINAL VERIFICATION SUMMARY[/bold]", border_style="bold cyan"))
    console.print("-" * 75)


def main():
    console.print("[bold green]========================================================================[/bold green]")
    console.print("[bold green]                   CONSTRAINTGUARD LIVE DEMO RUNNER                      [/bold green]")
    console.print("[bold green]========================================================================[/bold green]")

    # SCENARIO A — VIOLATION
    run_scenario(
        scenario_id="A",
        title="VIOLATION (Prohibited max() built-in used)",
        conversation=[
            {"turn": 1, "text": "Write a function that finds the maximum value. Do not use max()."},
            {"turn": 2, "text": "Also handle an empty list gracefully."},
            {"turn": 3, "text": "Keep the previous restrictions."},
        ],
        code="""\
def find_max(lst):
    if not lst:
        return None
    return max(lst)
""",
    )

    # SCENARIO B — SUPERSESSION
    run_scenario(
        scenario_id="B",
        title="SUPERSESSION (Recursion requirement superseded by no-recursion)",
        conversation=[
            {"turn": 1, "text": "Use recursion."},
            {"turn": 2, "text": "Do not use recursion."},
        ],
        code="""\
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)
""",
    )

    # SCENARIO C — CONFLICT
    run_scenario(
        scenario_id="C",
        title="CONFLICT (Unresolved contradiction: None vs ValueError)",
        conversation=[
            {"turn": 1, "text": "Return None for empty input."},
            {"turn": 2, "text": "Raise ValueError for empty input."},
        ],
        code="""\
def process_data(lst):
    if not lst:
        return None
    return lst[0]
""",
    )

    console.print("\n[bold green]DEMO COMPLETED SUCCESSFULLY.[/bold green]\n")


if __name__ == "__main__":
    main()
