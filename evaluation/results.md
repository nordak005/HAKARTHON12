============================================================
CONSTRAINTGUARD EVALUATION
============================================================

Dataset : ConstraintBench-Small (custom multi-turn benchmark)
NOTE    : This is NOT MBPP, HumanEval, or any official benchmark.
Cases   : 18
Expected constraint instances: 25

------------------------------------------------------------
METRICS COMPARISON
------------------------------------------------------------

Metric                                      ConstraintGuard     Baseline
------------------------------------------------------------------------
Constraint identification acc.                       100.0%       100.0%
Constraint state accuracy                            100.0%       100.0%
Violation detection precision                        100.0%       100.0%
Violation detection recall                           100.0%        85.7%
End-to-end verification accuracy                     100.0%        94.4%

------------------------------------------------------------
CONFUSION MATRIX (FAIL = positive class)
------------------------------------------------------------

                                ConstraintGuard     Baseline
True Positives (TP)                           7            6
False Positives (FP)                          0            0
False Negatives (FN)                          0            1
True Negatives (TN)                          11           11

------------------------------------------------------------
VERIFICATION SUMMARY (ConstraintGuard)
------------------------------------------------------------

  Violated constraints  : 6
  Satisfied constraints : 13
  Uncertain constraints : 1
  Conflicting pairs     : 2

------------------------------------------------------------
PER-CASE RESULTS
------------------------------------------------------------

ID    Cat                Expected   CG       BL       CG✓   BL✓  
--------------------------------------------------------------
A1    NO_BUILTIN         FAIL       FAIL     FAIL     ✓     ✓    
A2    NO_BUILTIN         PASS       PASS     PASS     ✓     ✓    
A3    NO_BUILTIN         FAIL       FAIL     FAIL     ✓     ✓    
A4    NO_BUILTIN         FAIL       FAIL     FAIL     ✓     ✓    
B1    SUPERSESSION       PASS       PASS     PASS     ✓     ✓    
B2    SUPERSESSION       FAIL       FAIL     FAIL     ✓     ✓    
C1    MULTI_SUPERSESSION PASS       PASS     PASS     ✓     ✓    
D1    REINFORCEMENT      PASS       PASS     PASS     ✓     ✓    
E1    CONFLICT           FAIL       FAIL     PASS     ✓     ✗    
F1    ERROR_HANDLING     PASS       PASS     PASS     ✓     ✓    
F2    ERROR_HANDLING     PASS       PASS     PASS     ✓     ✓    
G1    NAMING             PASS       PASS     PASS     ✓     ✓    
G2    NAMING             FAIL       FAIL     FAIL     ✓     ✓    
I1    STRUCTURE          PASS       PASS     PASS     ✓     ✓    
J1    COMPLEXITY         PASS       PASS     PASS     ✓     ✓    
K1    MIXED              FAIL       FAIL     FAIL     ✓     ✓    
K2    MIXED              PASS       PASS     PASS     ✓     ✓    
K3    MIXED              PASS       PASS     PASS     ✓     ✓    

------------------------------------------------------------
ERROR ANALYSIS (0 case(s) with CG errors)
------------------------------------------------------------

  No errors. All cases passed.
------------------------------------------------------------
KNOWN LIMITATIONS
------------------------------------------------------------

  1. COMPLEXITY constraints always produce UNCERTAIN (correct by design;
     static analysis cannot prove time/space complexity).
  2. Behavioral sandbox calls func([]) only; non-list signatures → UNCERTAIN.
  3. Identification is type-based (not text-exact); edge cases may slip through.
  4. This benchmark is NOT MBPP, HumanEval, or any standardized dataset.
     Results should be interpreted in the context of ConstraintBench-Small only.

============================================================