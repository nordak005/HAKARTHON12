# ConstraintGuard — 90-Minute MVP Development Plan
## Round 1 | Engineers' Day LLM Engineering Challenge | Problem Statement 02

---

## 0 · Situation Summary

| Item | Detail |
|---|---|
| **Python** | 3.13.14 |
| **Repo state** | Empty `Project/` folder — everything must be built from scratch |
| **Available data** | No pre-downloaded dataset; MBPP and HumanEval are public references |
| **Key deps installed** | `networkx 3.6.1`, `sentence-transformers 5.5.1`, `scikit-learn 1.9.0`, `numpy 2.4.6`, `rich 15.0.0`, `transformers 5.11.0`, `fastapi 0.128.0`, `streamlit 1.58.0`, `pydantic 2.12.5` |
| **Banned approach** | Reference solution: AST-only verification + explicit flat constraint state |

---

## 1 · Our Differentiated Architecture

```
Conversation (multi-turn)
        |
        v
+-----------------------------+
|  Constraint Extraction       |  Rule-based + embedding-based (NO LLM call needed)
|  (hybrid: regex + semantic)  |
+-------------+---------------+
              |  raw Constraint objects (id, text, turn, type)
              v
+-----------------------------+
|  Versioned Constraint Graph  |  NetworkX DiGraph
|  (VCG)                       |  Nodes = constraints, Edges = supersedes / conflicts / depends
+-------------+---------------+
              |
              v
+-----------------------------+
|  Lifecycle & Relationship    |  Semantic similarity (sentence-transformers all-MiniLM-L6-v2)
|  Resolver                    |  + keyword heuristics to detect SUPERSEDE / CONFLICT / ACTIVE
+-------------+---------------+
              |  classified ConstraintNode states
              v
+-----------------------------+
|  Hybrid Verification Engine  |  Three lanes run in parallel:
|  (1) Lexical (2) Structural  |   1. Token/regex scan of code text
|  (3) Behavioral              |   2. Python AST visitor (stdlib ast)
+-------------+---------------+   3. Lightweight execution trace (exec with sandbox + event hooks)
              |  per-constraint Evidence objects
              v
+-----------------------------+
|  Evidence Aggregator         |  Weighted voting across the three verifier lanes
+-------------+---------------+
              |
              v
+-----------------------------+
|  Explainable Report          |  JSON + Rich terminal table + (optional) Streamlit UI
|  (VerificationReport)        |  Shows: active / superseded / conflicting / violated + evidence
+-----------------------------+
```

### Why this beats the reference
| Dimension | Reference | ConstraintGuard |
|---|---|---|
| Constraint state | Flat list | Versioned Directed Graph with lifecycle edges |
| Constraint extraction | Prompt / keyword | Hybrid: regex patterns + semantic embedding clustering |
| Verification | AST only | Lexical + Structural AST + Behavioral (sandboxed exec) |
| Conflict detection | None | Graph-based cycle/contradiction detection |
| Explainability | Yes/No flags | Per-constraint evidence chain with verifier provenance |

---

## 2 · File Layout

```
Project/
+-- constraint_guard/
|   +-- __init__.py
|   +-- models.py            # Pydantic dataclasses: Constraint, ConstraintEdge, Evidence, VerificationReport
|   +-- extractor.py         # Hybrid constraint extraction (regex + semantic)
|   +-- graph.py             # VersionedConstraintGraph (NetworkX DiGraph)
|   +-- resolver.py          # Lifecycle & relationship resolution
|   +-- verifier/
|   |   +-- __init__.py
|   |   +-- lexical.py       # Regex / token-level verifier
|   |   +-- structural.py    # AST visitor verifier
|   |   +-- behavioral.py    # Sandboxed execution verifier
|   +-- aggregator.py        # Weighted evidence aggregation
|   +-- reporter.py          # Report rendering (JSON + Rich)
+-- tests/
|   +-- test_extractor.py
|   +-- test_graph.py
|   +-- test_verifier.py
|   +-- test_end_to_end.py
+-- demo.py                  # CLI demo script with 3 example conversations
+-- app.py                   # Streamlit UI (stretch goal)
+-- requirements.txt
+-- DEVELOPMENT_PLAN.md
```

---

## 3 · Constraint Types Supported

| Type tag | Example instruction | Detection method |
|---|---|---|
| `NO_BUILTIN` | "Do not use max()" | regex + AST Call node check |
| `ALGORITHM` | "Use recursion" / "no recursion" | regex + AST FunctionDef recursion check |
| `SIGNATURE` | "Accept a list, return int" | AST arguments + Return type hint |
| `STRUCTURE` | "Use a class" / "single function" | AST ClassDef / FunctionDef count |
| `ERROR_HANDLING` | "Handle empty list" | AST If / Try on empty check |
| `NAMING` | "Name it calculate_max" | AST FunctionDef.name |
| `COMPLEXITY` | "O(n) time" | Heuristic loop-nesting depth |
| `GENERAL` | Catch-all | Semantic embedding comparison |

---

## 4 · Lifecycle States (Constraint Graph Node Attributes)

```python
class ConstraintStatus(str, Enum):
    ACTIVE      = "active"       # still in force
    SUPERSEDED  = "superseded"   # explicitly replaced by a later turn
    CONFLICTING = "conflicting"  # contradicts another active constraint
    VIOLATED    = "violated"     # active but code does not satisfy it
    SATISFIED   = "satisfied"    # active and code satisfies it
```

Edge types in the graph:
- `SUPERSEDES` — later constraint replaces earlier one of same type
- `CONFLICTS`  — two active constraints are semantically contradictory
- `REINFORCES` — later turn confirms / strengthens an earlier constraint

---

## 5 · Execution Timeline (90 minutes)

| # | Task | ETA |
|---|---|---|
| 1 | `models.py` — all Pydantic models | T+10 min |
| 2 | `extractor.py` — regex + embedding extraction | T+20 min |
| 3 | `graph.py` — VCG build + NetworkX | T+30 min |
| 4 | `resolver.py` — lifecycle + conflict detection | T+40 min |
| 5 | `verifier/lexical.py` + `verifier/structural.py` | T+55 min |
| 6 | `verifier/behavioral.py` (sandboxed exec) | T+65 min |
| 7 | `aggregator.py` + `reporter.py` | T+75 min |
| 8 | `demo.py` + `tests/` end-to-end | T+85 min |
| 9 | Polish + README | T+90 min |

---

## 6 · Test Conversations (Hardcoded for Demo)

### Conversation A — "max() ban + empty-list handling"
```
Turn 1: "Write a function that finds the max of a list. Do not use max()."
Turn 2: "Also handle an empty list gracefully."
Turn 3: "Keep the previous restrictions."
Code:   def find_max(lst): return max(lst)   # violates NO_BUILTIN
```

### Conversation B — "Supersession"
```
Turn 1: "Use recursion."
Turn 2: "Do not use recursion."
Code:   def fact(n): return n * fact(n-1) if n > 0 else 1  # violates now-ACTIVE "no recursion"
```

### Conversation C — "Conflict detection"
```
Turn 1: "Return None for empty input."
Turn 2: "Raise ValueError for empty input."
Code:   def process(lst): return None if not lst else lst[0]
```

---

## 7 · Evaluation Targets

| Metric | Target for demo |
|---|---|
| Constraint identification accuracy | >= 0.85 on hardcoded test suite |
| Constraint-state accuracy (active/superseded) | >= 0.90 |
| Violation detection precision | >= 0.90 |
| Violation detection recall | >= 0.85 |
| End-to-end verification accuracy | >= 0.80 |

> **Note:** All metrics are measured on our own hand-labeled test cases derived from
> MBPP-style conversations. No numbers are fabricated — metrics are printed live from `demo.py`.

---

## 8 · How to Run

```powershell
# Install any extra deps (most are already present)
pip install -r Project/requirements.txt

# Run the demo (3 conversations, full terminal report)
python Project/demo.py

# Run all tests
python -m pytest Project/tests/ -v

# (Stretch) Launch Streamlit UI
streamlit run Project/app.py
```

---

## 9 · What We DO NOT Do

- No external LLM API call (offline, zero API key needed)
- No copy of the reference flat-AST-only approach
- No fabricated datasets or benchmark numbers
- No single-lane verification — all three lanes must contribute evidence

---

## 10 · Key Design Decisions and Novelty Claims

1. **Versioned Constraint Graph** — constraints are nodes; temporal evolution is an edge
   property. Graph traversal determines which constraints are still "reachable" (active)
   after supersession chains.

2. **Semantic Supersession Detection** — sentence-transformers embeddings detect when
   "Use recursion" is superseded by "Do not use recursion" even with no explicit
   "instead of" marker.

3. **Three-Lane Hybrid Verification** — lexical (fast, catches obvious cases), structural
   AST (catches code structure), behavioral (catches runtime violations invisible to static
   analysis). Weighted evidence aggregation prevents single-lane false positives.

4. **Conflict Graph Cycles** — two ACTIVE constraints that are semantically opposed form
   a directed conflict edge in the VCG; the resolver flags both as `CONFLICTING` and the
   report surfaces the ambiguity explicitly.

5. **Evidence Provenance** — every verdict carries which verifier lane produced it, what
   evidence was found (line number, AST node type, token), and a confidence score.
