"""
scripts/run_evaluation.py
===========================
Entry point for the ConstraintBench-Small evaluation.

Usage:
    python scripts/run_evaluation.py

Output:
    - Printed report to stdout
    - evaluation/results.md   (human-readable)
    - evaluation/results.json (machine-readable)
"""

import sys
import os

# Allow imports from the Project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from constraint_guard.evaluation.cases import load_cases
from constraint_guard.evaluation.runner import run_evaluation
from constraint_guard.evaluation.report import save_and_print
from constraint_guard.evaluation.metrics import aggregate_metrics


def main():
    print("Loading ConstraintBench-Small benchmark cases...")
    cases = load_cases()
    print(f"Loaded {len(cases)} cases.")
    print()
    print("Running evaluation (this includes subprocess behavioral tests)...")

    eval_result = run_evaluation(cases)

    # Compute metrics
    metrics = aggregate_metrics(
        eval_result.cases,
        eval_result.comparisons,
        eval_result.cg_results,
    )

    # Determine output directory relative to this script's location
    out_dir = os.path.join(os.path.dirname(__file__), "..", "evaluation")
    os.makedirs(out_dir, exist_ok=True)

    # Save and print
    text, data = save_and_print(eval_result, output_dir=out_dir)

    print()
    print(f"Results saved to:")
    print(f"  {os.path.abspath(os.path.join(out_dir, 'results.md'))}")
    print(f"  {os.path.abspath(os.path.join(out_dir, 'results.json'))}")

    # Return exit code 0 always (evaluation itself never "fails" as a script)
    return 0


if __name__ == "__main__":
    sys.exit(main())
