"""
constraint_guard.models
=======================
Core Pydantic data models for ConstraintGuard.

All runtime state is represented here so that every other module
can import from a single, stable location.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator
import uuid


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class ConstraintStatus(str, Enum):
    """Lifecycle state of a single constraint node in the graph."""
    ACTIVE      = "active"       # still in force, not yet verified
    SUPERSEDED  = "superseded"   # explicitly replaced by a later-turn constraint
    CONFLICTING = "conflicting"  # contradicts another currently active constraint
    VIOLATED    = "violated"     # active but the generated code does not satisfy it
    SATISFIED   = "satisfied"    # active and the generated code satisfies it


class ConstraintType(str, Enum):
    """Semantic category of a constraint, used to select verifier strategies."""
    NO_BUILTIN     = "no_builtin"     # e.g. "Do not use max()"
    ALGORITHM      = "algorithm"      # e.g. "Use recursion" / "No recursion"
    SIGNATURE      = "signature"      # e.g. "Accept a list, return int"
    STRUCTURE      = "structure"      # e.g. "Use a class" / "single function only"
    ERROR_HANDLING = "error_handling" # e.g. "Handle empty list"
    NAMING         = "naming"         # e.g. "Name the function calculate_max"
    COMPLEXITY     = "complexity"     # e.g. "O(n) time complexity"
    GENERAL        = "general"        # catch-all for semantically matched constraints


class ConstraintEdgeType(str, Enum):
    """Directed relationship between two constraint nodes in the VCG."""
    SUPERSEDES  = "supersedes"   # source replaces target (same semantic category)
    CONFLICTS   = "conflicts"    # source contradicts target (both active → problem)
    REINFORCES  = "reinforces"   # source confirms / strengthens target
    DEPENDS_ON  = "depends_on"   # source is only meaningful if target is also active


# ---------------------------------------------------------------------------
# Core models
# ---------------------------------------------------------------------------

class Constraint(BaseModel):
    """
    A single extracted constraint from one conversation turn.

    Attributes
    ----------
    id          : Unique stable identifier (auto-generated if not supplied).
    text        : Raw text of the constraint as extracted from the instruction.
    type        : Semantic category.
    source_turn : 1-indexed turn number in which this constraint appeared.
    status      : Current lifecycle state (default ACTIVE on creation).
    target      : Optional specific identifier this constraint refers to
                  (e.g. a builtin name "max", a function name "calculate_max").
    confidence  : Extractor confidence in [0.0, 1.0].
    evidence    : Human-readable evidence strings collected during extraction.
    metadata    : Arbitrary key-value store for extractor-specific data.
    """
    id:          str            = Field(default_factory=lambda: str(uuid.uuid4()))
    text:        str            = Field(..., min_length=1)
    type:        ConstraintType = Field(default=ConstraintType.GENERAL)
    source_turn: int            = Field(..., ge=1)
    status:      ConstraintStatus = Field(default=ConstraintStatus.ACTIVE)
    target:      Optional[str]  = Field(default=None)
    confidence:  float          = Field(default=1.0)
    evidence:    list[str]      = Field(default_factory=list)
    metadata:    dict           = Field(default_factory=dict)

    @field_validator("confidence")
    @classmethod
    def confidence_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence must be in [0.0, 1.0], got {v}")
        return round(v, 6)

    model_config = {"use_enum_values": False}


class ConstraintEdge(BaseModel):
    """
    A directed edge between two Constraint nodes in the Versioned Constraint Graph.

    Attributes
    ----------
    source_id  : ID of the source constraint (the newer / acting constraint).
    target_id  : ID of the target constraint (the older / acted-upon constraint).
    edge_type  : Semantic relationship type.
    confidence : Resolver confidence in [0.0, 1.0].
    reason     : Human-readable explanation of why this edge was inferred.
    """
    source_id:  str                = Field(...)
    target_id:  str                = Field(...)
    edge_type:  ConstraintEdgeType = Field(...)
    confidence: float              = Field(default=1.0)
    reason:     str                = Field(default="")

    @field_validator("confidence")
    @classmethod
    def confidence_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence must be in [0.0, 1.0], got {v}")
        return round(v, 6)

    @model_validator(mode="after")
    def source_not_equal_target(self) -> "ConstraintEdge":
        if self.source_id == self.target_id:
            raise ValueError("source_id and target_id must be different")
        return self


class Evidence(BaseModel):
    """
    One piece of verification evidence produced by a single verifier lane.

    Attributes
    ----------
    constraint_id : ID of the constraint being verified.
    verifier      : Name of the verifier lane ("lexical", "structural", "behavioral").
    passed        : True if the constraint is satisfied according to this lane.
    confidence    : Verifier confidence in [0.0, 1.0].
    message       : Human-readable explanation of the finding.
    line_number   : Optional line number in the generated code where evidence was found.
    code_snippet  : Optional raw code excerpt relevant to the finding.
    metadata      : Arbitrary key-value store for verifier-specific data.
    """
    constraint_id: str           = Field(...)
    verifier:      str           = Field(..., min_length=1)
    passed:        bool          = Field(...)
    confidence:    float         = Field(default=1.0)
    message:       str           = Field(default="")
    line_number:   Optional[int] = Field(default=None)
    code_snippet:  Optional[str] = Field(default=None)
    metadata:      dict          = Field(default_factory=dict)

    @field_validator("confidence")
    @classmethod
    def confidence_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence must be in [0.0, 1.0], got {v}")
        return round(v, 6)

    @field_validator("line_number")
    @classmethod
    def line_number_positive(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 1:
            raise ValueError(f"line_number must be >= 1, got {v}")
        return v


class VerificationResult(BaseModel):
    """
    Aggregated verification outcome for a single constraint after all lanes vote.

    Attributes
    ----------
    constraint_id : ID of the constraint.
    status        : Final resolved ConstraintStatus after aggregation.
    evidences     : All Evidence objects collected across verifier lanes.
    final_pass    : True if the constraint is considered satisfied overall.
    confidence    : Aggregated confidence score in [0.0, 1.0].
    """
    constraint_id: str                = Field(...)
    status:        ConstraintStatus   = Field(...)
    evidences:     list[Evidence]     = Field(default_factory=list)
    final_pass:    bool               = Field(...)
    confidence:    float              = Field(default=1.0)

    @field_validator("confidence")
    @classmethod
    def confidence_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence must be in [0.0, 1.0], got {v}")
        return round(v, 6)


class VerificationReport(BaseModel):
    """
    Top-level report produced after verifying all active constraints
    in a conversation against the generated code.

    Attributes
    ----------
    total_constraints       : Total number of constraints extracted across all turns.
    active_constraints      : Constraints that are currently in force.
    superseded_constraints  : Constraints that were replaced by a later turn.
    conflicting_constraints : Active constraints that contradict each other.
    satisfied_constraints   : Active constraints that the code satisfies.
    violated_constraints    : Active constraints that the code violates.
    results                 : Per-constraint VerificationResult objects.
    overall_status          : "PASS" if no active constraint is violated, else "FAIL".
    """
    total_constraints:      int                     = Field(default=0, ge=0)
    active_constraints:     int                     = Field(default=0, ge=0)
    superseded_constraints: int                     = Field(default=0, ge=0)
    conflicting_constraints:int                     = Field(default=0, ge=0)
    satisfied_constraints:  int                     = Field(default=0, ge=0)
    violated_constraints:   int                     = Field(default=0, ge=0)
    results:                list[VerificationResult] = Field(default_factory=list)
    overall_status:         str                     = Field(default="PASS")

    @model_validator(mode="after")
    def derive_overall_status(self) -> "VerificationReport":
        # Recompute from results list if results are present
        if self.results:
            violated = sum(
                1 for r in self.results
                if r.status == ConstraintStatus.VIOLATED
            )
            self.overall_status = "FAIL" if violated > 0 else "PASS"
        return self

    @model_validator(mode="after")
    def count_consistency(self) -> "VerificationReport":
        # Ensure summary counts are internally consistent when results are present.
        # Callers should use VerificationReport.from_results() for auto-population.
        return self

    @classmethod
    def from_results(
        cls,
        all_constraints: list[Constraint],
        results: list[VerificationResult],
    ) -> "VerificationReport":
        """
        Factory: build a VerificationReport from the full constraint list and
        per-constraint results. This is the preferred construction path.
        """
        status_counts: dict[ConstraintStatus, int] = {s: 0 for s in ConstraintStatus}
        for c in all_constraints:
            status_counts[c.status] = status_counts.get(c.status, 0) + 1

        # Override ACTIVE counts with verified results
        for r in results:
            if r.status in (ConstraintStatus.SATISFIED, ConstraintStatus.VIOLATED):
                # subtract from active
                status_counts[ConstraintStatus.ACTIVE] = max(
                    0, status_counts[ConstraintStatus.ACTIVE] - 1
                )
            status_counts[r.status] = status_counts.get(r.status, 0) + 1

        violated = status_counts.get(ConstraintStatus.VIOLATED, 0)

        return cls(
            total_constraints=len(all_constraints),
            active_constraints=status_counts.get(ConstraintStatus.ACTIVE, 0),
            superseded_constraints=status_counts.get(ConstraintStatus.SUPERSEDED, 0),
            conflicting_constraints=status_counts.get(ConstraintStatus.CONFLICTING, 0),
            satisfied_constraints=status_counts.get(ConstraintStatus.SATISFIED, 0),
            violated_constraints=violated,
            results=results,
            overall_status="FAIL" if violated > 0 else "PASS",
        )
