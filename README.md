# ConstraintGuard

ConstraintGuard is a model-agnostic verification layer for AI-generated Python code in multi-turn conversations.

## Problem
In multi-turn developer conversations with LLMs, requirements evolve dynamically. AI models frequently fail to maintain constraint state across turns—forgetting previous constraints, attempting to adhere to superseded instructions, or ignoring conflicting rules. Standard code evaluation tools treat instructions as flat prompts or rely on simple AST checks, leading to inaccurate safety and quality verdicts.

## Solution
ConstraintGuard implements a **Track → Resolve → Verify** architecture:
1. **Track**: Extract constraints and model relationships in a Versioned Constraint Graph.
2. **Resolve**: Perform graph traversal to isolate active requirements, supersede obsolete instructions, and detect contradictions.
3. **Verify**: Route active constraints through a multi-lane hybrid engine (Lexical, AST, and Behavioral subprocess testing).

## Key Differentiators
- **Versioned Constraint Graph**: Models `SUPERSEDES`, `CONFLICTS`, `REINFORCES`, and `DEPENDS_ON` relationships.
- **Lifecycle Resolution**: Separates active constraints from superseded history and flags unresolved conflicts without guessing developer intent.
- **Hybrid Multi-Lane Verification**: Combines Python tokenization, AST inspection, and isolated subprocess sandbox execution.
- **Grounded Evidence**: Returns exact line numbers, verifier sources, and execution evidence for every verdict.

## Evaluation
Evaluated on **ConstraintBench-Small** (18 multi-turn benchmark cases):
- **ConstraintGuard Accuracy**: **100.0%**
- **Baseline (Flat AST-Only) Accuracy**: **94.4%**
- **Automated Unit Tests**: **286/286 passed** (`pytest -q`)

*Disclaimer*: ConstraintBench-Small is a small manually labeled benchmark used for evaluating multi-turn constraint lifecycle scenarios and should not be interpreted as a general coding accuracy benchmark.

## Quickstart & Execution Commands

### 1. Run Automated Test Suite
```bash
pytest -q
```

### 2. Run Reproducible Evaluation Harness
```bash
python scripts/run_evaluation.py
```

### 3. Run Live Interactive Hackathon Demo
```bash
python scripts/demo.py
```

## Known Technical Limitations
- **Behavioral Sandbox**: Uses isolated subprocesses; designed as a lightweight hackathon sandbox rather than a containerized environment.
- **Function Signatures**: Behavioral verifier currently targets standard list/single-parameter functions for automated edge testing.
- **Static Complexity Bounds**: `COMPLEXITY` constraints (e.g. `O(n)`) evaluate to `UNCERTAIN` as algorithmic time complexity cannot be statically proven via AST analysis.
- **General Rules**: Open-ended natural language prompts without specific patterns yield `UNCERTAIN`.
