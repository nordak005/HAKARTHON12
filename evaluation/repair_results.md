# ConstraintGuard — Repair Layer Evaluation Report

**Benchmark Dataset**: ConstraintBench-Repair (Offline Reproducible Set)  
**Provider**: `DeterministicMockProvider` (100% Reproducible, No API Key Required)  
**Max Iterations Budget**: 2

## Summary Metrics

| Metric | Value | Definition |
| :--- | :---: | :--- |
| **Total Benchmark Cases** | **5** | Total multi-turn repair test scenarios |
| **Initial Violation Rate** | **100.0%** | Percentage of initial code snippets violating active constraints |
| **Repair Success Rate** | **100.0%** | Percentage of initially violated cases resolved to `VERIFIED` |
| **Residual Violation Rate** | **0.0%** | Percentage of cases remaining violated after repair budget |
| **Average Repair Iterations** | **1.00** | Mean LLM repair attempts used per scenario |
| **Constraint Preservation Rate** | **100.0%** | Percentage of previously satisfied constraints kept satisfied post-repair |

## Detailed Per-Case Benchmark Results

| Case ID | Name | Initial Status | Final Status | Iterations | Result |
| :--- | :--- | :---: | :---: | :---: | :---: |
| `R1_NO_BUILTIN` | Repair prohibited max() built-in usage | `FAIL` | `PASS` | 1 | **PASSED** |
| `R2_RECURSION` | Repair superseded recursion constraint violation | `FAIL` | `PASS` | 1 | **PASSED** |
| `R3_NAMING` | Repair function name mismatch | `FAIL` | `PASS` | 1 | **PASSED** |
| `R4_STRUCTURE` | Repair missing class wrapper constraint | `FAIL` | `PASS` | 1 | **PASSED** |
| `R5_MULTI_VIOLATION` | Repair combined max() ban and function naming violation | `FAIL` | `PASS` | 1 | **PASSED** |
