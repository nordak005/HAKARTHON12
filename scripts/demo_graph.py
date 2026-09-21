"""
scripts/demo_graph.py
======================
Terminal Graph Visualizer for ConstraintGuard Versioned Constraint Graph (VCG).

Runs multi-turn demo prompts and prints the complete visual Versioned Constraint Graph
(nodes, statuses, directional edges, supersessions, conflicts) directly on the terminal.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.panel import Panel
from constraint_guard.extractor import extract
from constraint_guard.graph import VersionedConstraintGraph
from constraint_guard.resolver import ConstraintResolver

console = Console()


def visualize_prompt_graph(scenario_title: str, conversation: list[dict]):
    console.print()
    console.rule(f"[bold magenta]GRAPH VISUALIZATION: {scenario_title}[/bold magenta]")
    
    # Extract constraints and build graph
    extracted = extract(conversation)
    graph = VersionedConstraintGraph.build_from_constraints(extracted.constraints)
    
    # Resolve state
    resolver = ConstraintResolver()
    state = resolver.resolve(graph)

    # Output ASCII graph
    graph_text = graph.format_ascii_graph()
    console.print(Panel(graph_text, title=f"[bold cyan]VCG Topology ({scenario_title})[/bold cyan]", border_style="cyan"))


def main():
    console.print("[bold green]========================================================================[/bold green]")
    console.print("[bold green]         CONSTRAINTGUARD TERMINAL GRAPH VISUALIZER (VCG DEMO)           [/bold green]")
    console.print("[bold green]========================================================================[/bold green]")

    # Demo 1: Supersession Graph
    visualize_prompt_graph(
        "Supersession Scenario (Recursion -> No Recursion)",
        [
            {"turn": 1, "text": "Use recursion to compute factorial."},
            {"turn": 2, "text": "Do not use recursion."},
        ]
    )

    # Demo 2: Conflict Graph
    visualize_prompt_graph(
        "Conflict Scenario (Return None vs Raise ValueError)",
        [
            {"turn": 1, "text": "Return None when list is empty."},
            {"turn": 2, "text": "Raise ValueError when list is empty."},
        ]
    )

    # Demo 3: Multi-turn Feature Graph
    visualize_prompt_graph(
        "Multi-turn Complex Scenario",
        [
            {"turn": 1, "text": "Write a function to sort integers. Do not use sort() or sorted()."},
            {"turn": 2, "text": "Actually use bubble sort."},
            {"turn": 3, "text": "Do not use bubble sort, use quicksort instead."},
            {"turn": 4, "text": "Raise ValueError for non-list inputs."},
        ]
    )


if __name__ == "__main__":
    main()
