# ConstraintGuard — Project Summary Report

## Project Identification
- **Project Name**: ConstraintGuard
- **Tagline**: Model-Agnostic Multi-Turn Python Code Verification Layer
- **Hackathon Round**: Round 1 MVP Implementation

## Problem Statement
In multi-turn LLM code generation, developer constraints evolve dynamically. Requirements introduced in early turns are frequently forgotten, modified, or contradicted by later turns. Standard static verifiers process only the latest turn prompt or treat all past instructions as a flat list, leading to false positives on obsolete rules, missing conflicting constraints, and ungrounded pass verdicts.

## Architecture & Implementation Overview
ConstraintGuard enforces a strict non-flat, evidence-grounded verification pipeline:

```
Multi-Turn Conversation
          │
          ▼
Hybrid Constraint Extractor (Rule-based & Regex Tokenizer)
          │
          ▼
Versioned Constraint Graph (NetworkX Directed Graph + Typed Edges)
          │
          ▼
Lifecycle Resolver (Graph Traversals for Supersession & Conflict Detection)
          │
          ▼
Hybrid Verification Engine (Constraint-routed Multi-Lane Verification)
 ┌────────┴─────────┬──────────────────┬─────────────────────┐
 │ Lexical Lane     │ Structural Lane  │ Behavioral Lane     │
 │ (Token Stream)   │ (Python AST)     │ (Subprocess Sandbox)│
 └────────┬─────────┴──────────────────┴─────────────────────┘
          │
          ▼
Evidence Aggregator & Final Verification Report
```

## Hybrid Verification Lanes
1. **Lexical Lane**: Uses Python's native `tokenize` module to check token-level occurrences (comments, strings, function calls) without AST scope hiding.
2. **Structural Lane**: Uses Python AST to check syntactic constructs, class definitions, function signatures, AST node call sites, and AST recursion trees.
3. **Behavioral Lane**: Executes code in an isolated subprocess sandbox with edge-case inputs (e.g., `[]`, `None`) to verify actual runtime error handling and return values.

## Benchmark & Evaluation Results
Evaluated on **ConstraintBench-Small** (18 multi-turn hand-labeled benchmark test cases):

| Metric | ConstraintGuard | AST-Only Flat Baseline |
| :--- | :---: | :---: |
| **Constraint Identification Accuracy** | **100.0%** | 100.0% |
| **Constraint State Resolution Accuracy** | **100.0%** | 100.0% |
| **Violation Detection Precision** | **100.0%** | 100.0% |
| **Violation Detection Recall** | **100.0%** | 85.7% |
| **End-to-End Verification Accuracy** | **100.0%** | **94.4%** |

*Key Result*: ConstraintGuard correctly identifies conflicting requirements (Case E1) and supersession chains where flat baselines fail.

## Test Suite Status
- **286 / 286** unit and integration tests passing cleanly (`pytest -q`).

## Honest Technical Limitations
1. **Sandbox Scope**: The behavioral sandbox is lightweight (isolated subprocess) designed for rapid hackathon execution; it is not a containerized sandbox.
2. **Signature Support**: Behavioral execution currently auto-probes single-list function parameter signatures.
3. **Complexity Verification**: `COMPLEXITY` constraints (e.g. `O(n)`) are flagged as `UNCERTAIN` because time/space complexity cannot be proven deterministically via static AST analysis.
4. **General Constraints**: Broad natural language guidelines without deterministic patterns remain `UNCERTAIN`.
5. **Benchmark Scope**: ConstraintBench-Small consists of 18 curated multi-turn scenarios tailored for core edge cases, not a replacement for full-scale MBPP/HumanEval benchmarks.
