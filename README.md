# ConstraintGuard

**ConstraintGuard** is a model-agnostic verification and closed-loop repair layer for AI-generated Python code in multi-turn developer conversations.

---

## 1. Problem Statement
In multi-turn developer conversations with LLMs, requirements evolve dynamically. AI models frequently fail to maintain constraint state across turns—forgetting previous constraints, attempting to adhere to superseded instructions, or ignoring conflicting rules. Standard code evaluation tools treat instructions as flat prompts or rely on simple AST checks, leading to inaccurate safety and quality verdicts.

---

## 2. Official Expected Outcome & Our Solution
The expected outcome is a system that maintains active coding requirements throughout a conversation and verifies whether generated code satisfies them.

ConstraintGuard implements a **Track → Resolve → Verify → Repair** architecture:
1. **Track**: Extract constraints and model temporal relationships in a **Versioned Constraint Graph (VCG)**.
2. **Resolve**: Perform graph traversal to isolate active requirements, supersede obsolete instructions, and detect contradictions.
3. **Verify**: Route active constraints through a multi-lane hybrid engine (Lexical, AST, and Behavioral subprocess testing).
4. **Repair (Our Proposed Innovation)**: Pass line-numbered verification evidence back to the LLM to generate corrected code, re-verified independently by ConstraintGuard in a controlled loop.

---

## 3. Key Differentiators & Baseline Comparison

| Feature / Dimension | Flat AST Baseline | ConstraintGuard System |
| :--- | :--- | :--- |
| **Constraint State Model** | Flat List | **Versioned Constraint Graph (NetworkX)** |
| **Edge Relationships** | None | **SUPERSEDES, CONFLICTS, REINFORCES, DEPENDS_ON** |
| **Verification Engine** | AST Only | **3-Lane Hybrid: Lexical + Structural AST + Sandboxed Behavioral** |
| **Evidence Grounding** | Pass/Fail flags | **Line-numbered evidence, AST nodes, and execution traces** |
| **Repair Capability** | None | **Closed-Loop LLM Repair (Independent Verifier Authority)** |

---

## 4. Architecture Flow

```
USER CONVERSATION
       │
       ▼
CONSTRAINT EXTRACTION (Regex & Pattern Extractor)
       │
       ▼
VERSIONED CONSTRAINT GRAPH (NetworkX DiGraph)
       │
       ▼
LIFECYCLE RESOLVER (Active vs Superseded vs Conflicting)
       │
       ▼
LLM CODE GENERATION (OpenAI-compatible HTTP provider)
       │
       ▼
CONSTRAINTGUARD HYBRID VERIFICATION
 ├── Lexical Lane (Token stream)
 ├── Structural Lane (Python AST)
 └── Behavioral Lane (Subprocess Sandbox)
       │
       ▼
VERIFICATION REPORT (Line-numbered evidence)
       │
   Violations?
    /       \
  NO         YES
  ↓           ↓
PASS    LLM REPAIR ENGINE
              │
        Repaired Candidate Code
              │
        CONSTRAINTGUARD RE-VERIFICATION
              │
          PASS / FAIL
```

> **Independent Verifier Guarantee**: ConstraintGuard is the sole verification authority. The LLM proposes repair candidates, but is never trusted to self-verify.

---

## 5. Setup & Environment Variables

### Prerequisites
- Python 3.9+
- Standard libraries & dependencies in `requirements.txt`

### Environment Configuration (Optional)
Copy `.env.example` to `.env` if using live LLM endpoints:
```bash
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=your_openai_api_key_here
LLM_MODEL=gpt-4o-mini
```
*Note*: If no API key is set, ConstraintGuard automatically operates in **Offline Deterministic / Demo Mode** without crashing.

---

## 6. Execution Commands

### 1. Run Automated Test Suite
```bash
python -m pytest -v
```

### 2. Run Reproducible Baseline Evaluation
```bash
python scripts/run_evaluation.py
```

### 3. Run Offline Reproducible Repair Evaluation
```bash
python evaluation/run_repair_evaluation.py
```

### 4. Run Interactive Terminal Demo
```bash
python scripts/demo.py
```

### 5. Launch Streamlit Web UI
```bash
streamlit run app.py
```

---

## 7. Measured Evaluation Results

### A. Core Verification Benchmark (ConstraintBench-Small)
- **ConstraintGuard Accuracy**: **100.0%** (18/18 cases)
- **Baseline (Flat AST-Only) Accuracy**: **94.4%** (17/18 cases)
- **Violation Detection Recall**: **100.0%** (CG) vs **85.7%** (Baseline)

### B. Reproducible Repair Layer Benchmark (ConstraintBench-Repair)
- **Initial Violation Rate**: **100.0%** (5/5 initial violation scenarios)
- **Repair Success Rate**: **100.0%** (5/5 resolved to VERIFIED)
- **Residual Violation Rate**: **0.0%**
- **Average Repair Iterations**: **1.00**
- **Constraint Preservation Rate**: **100.0%**

---

## 8. Technical Limitations & Future Work
- **Behavioral Sandbox**: Uses isolated subprocesses; designed as a lightweight hackathon sandbox rather than a containerized environment (Docker/gVisor).
- **Function Signatures**: Behavioral verifier currently targets standard list/single-parameter functions for automated edge testing.
- **Static Complexity Bounds**: `COMPLEXITY` constraints (e.g. `O(n)`) evaluate to `UNCERTAIN` as algorithmic time complexity cannot be statically proven via AST analysis.
