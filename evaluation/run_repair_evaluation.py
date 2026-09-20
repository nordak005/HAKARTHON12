"""
evaluation/run_repair_evaluation.py
===================================
Offline reproducible evaluation runner for ConstraintGuard Closed-Loop Repair Layer.

Usage:
    python evaluation/run_repair_evaluation.py

Outputs:
    - Printed terminal report
    - evaluation/repair_results.json
    - evaluation/repair_results.md
"""

from __future__ import annotations

import json
import os
import sys

# Allow imports from project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from evaluation.repair_cases import load_repair_cases
from evaluation.repair_metrics import compute_repair_metrics
from constraint_guard.llm.provider import DeterministicMockProvider
from constraint_guard.repair.loop import run_repair_loop


def run_repair_evaluation(out_dir: str):
    cases = load_repair_cases()

    # Build deterministic mock provider for 100% reproducible evaluation
    mock_response_map = {}
    for case in cases:
        # Map conversation keywords to repaired implementations
        first_turn_text = case.conversation[0]["text"]
        mock_response_map[first_turn_text] = case.repaired_code

    provider = DeterministicMockProvider(response_map=mock_response_map)

    histories = []
    print(f"Running Repair Benchmark on {len(cases)} cases using DeterministicMockProvider...")
    print("=" * 70)

    for case in cases:
        print(f"[{case.id}] {case.name}...", end=" ")
        history = run_repair_loop(
            conversation=case.conversation,
            initial_code=case.initial_code,
            max_iterations=2,
            provider=provider,
        )
        histories.append(history)

        init_status = history.initial_report.overall_status
        final_status = history.final_report.overall_status
        result_icon = "REPAIRED" if history.success else "UNRESOLVED"
        print(f"Initial: {init_status} -> Final: {final_status} ([{result_icon}], {history.iterations_used} iter)")

    metrics = compute_repair_metrics(histories)

    print("\n" + "=" * 70)
    print("REPAIR EVALUATION METRICS REPORT")
    print("=" * 70)
    print(f"Total Benchmark Cases        : {metrics.total_cases}")
    print(f"Initial Violation Rate       : {metrics.initial_violation_rate:.1f}% ({metrics.initial_violations}/{metrics.total_cases})")
    print(f"Repair Success Rate          : {metrics.repair_success_rate:.1f}% ({metrics.repaired_successes}/{metrics.initial_violations})")
    print(f"Residual Violation Rate      : {metrics.residual_violation_rate:.1f}% ({metrics.residual_violations}/{metrics.initial_violations})")
    print(f"Average Repair Iterations    : {metrics.average_iterations:.2f}")
    print(f"Constraint Preservation Rate : {metrics.constraint_preservation_rate:.1f}%")
    print("=" * 70)

    # Save Markdown report
    md_content = f"""# ConstraintGuard — Repair Layer Evaluation Report

**Benchmark Dataset**: ConstraintBench-Repair (Offline Reproducible Set)  
**Provider**: `DeterministicMockProvider` (100% Reproducible, No API Key Required)  
**Max Iterations Budget**: 2

## Summary Metrics

| Metric | Value | Definition |
| :--- | :---: | :--- |
| **Total Benchmark Cases** | **{metrics.total_cases}** | Total multi-turn repair test scenarios |
| **Initial Violation Rate** | **{metrics.initial_violation_rate:.1f}%** | Percentage of initial code snippets violating active constraints |
| **Repair Success Rate** | **{metrics.repair_success_rate:.1f}%** | Percentage of initially violated cases resolved to `VERIFIED` |
| **Residual Violation Rate** | **{metrics.residual_violation_rate:.1f}%** | Percentage of cases remaining violated after repair budget |
| **Average Repair Iterations** | **{metrics.average_iterations:.2f}** | Mean LLM repair attempts used per scenario |
| **Constraint Preservation Rate** | **{metrics.constraint_preservation_rate:.1f}%** | Percentage of previously satisfied constraints kept satisfied post-repair |

## Detailed Per-Case Benchmark Results

| Case ID | Name | Initial Status | Final Status | Iterations | Result |
| :--- | :--- | :---: | :---: | :---: | :---: |
"""
    for case, h in zip(cases, histories):
        icon = "PASSED" if h.success else "FAILED"
        md_content += f"| `{case.id}` | {case.name} | `{h.initial_report.overall_status}` | `{h.final_report.overall_status}` | {h.iterations_used} | **{icon}** |\n"

    md_path = os.path.join(out_dir, "repair_results.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # Save JSON data
    json_data = {
        "metrics": {
            "total_cases": metrics.total_cases,
            "initial_violations": metrics.initial_violations,
            "initial_violation_rate": metrics.initial_violation_rate,
            "repaired_successes": metrics.repaired_successes,
            "repair_success_rate": metrics.repair_success_rate,
            "residual_violations": metrics.residual_violations,
            "residual_violation_rate": metrics.residual_violation_rate,
            "average_iterations": metrics.average_iterations,
            "constraint_preservation_rate": metrics.constraint_preservation_rate,
        },
        "cases": [
            {
                "id": c.id,
                "name": c.name,
                "initial_status": h.initial_report.overall_status,
                "final_status": h.final_report.overall_status,
                "iterations_used": h.iterations_used,
                "success": h.success,
            }
            for c, h in zip(cases, histories)
        ],
    }

    json_path = os.path.join(out_dir, "repair_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2)

    print(f"\nSaved evaluation outputs to:")
    print(f"  {os.path.abspath(md_path)}")
    print(f"  {os.path.abspath(json_path)}")


def main():
    out_dir = os.path.join(os.path.dirname(__file__))
    run_repair_evaluation(out_dir)


if __name__ == "__main__":
    main()
