"""Optimization module outputs (module design v1 §3.8, §7; math companion §11)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class SolverStatus(str, Enum):
    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    TIMEOUT = "TIMEOUT"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


class PhaseStatus(str, Enum):
    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    TIMEOUT = "TIMEOUT"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


class ProposedDirection(str, Enum):
    A_TO_B = "A_TO_B"
    B_TO_A = "B_TO_A"
    BIDIRECTIONAL = "BIDIRECTIONAL"
    BLOCKED = "BLOCKED"  # 防御: §11.2.1 制約上は本来出ない


class ImportanceDirection(str, Enum):
    A_TO_B = "A_TO_B"
    B_TO_A = "B_TO_A"
    NONE = "NONE"


@dataclass(frozen=True)
class RouteImportance:
    edge_id: str
    direction: ImportanceDirection
    importance: float
    valid_until_next_trigger: bool = True


@dataclass(frozen=True)
class DirectionProposal:
    edge_id: str
    proposed_direction: ProposedDirection
    confidence: float = 1.0


@dataclass(frozen=True)
class ObjectiveValues:
    tau_star: float
    throughput: float


@dataclass(frozen=True)
class SolverStats:
    solver_name: str
    phase1_status: PhaseStatus
    phase2_status: PhaseStatus
    phase1_ms: int
    phase2_ms: int
    tau_star: float
    throughput: float


@dataclass(frozen=True)
class ConstraintReport:
    local_reachability_satisfied: bool
    boundary_reachability_satisfied: bool
    legal_fixed_violations: tuple[str, ...] = ()
    fallback_to_previous: bool = False


@dataclass(frozen=True)
class OptimizationResult:
    """Core optimization output. Constraint #4: no `boundary_control` field in this PoC."""

    route_importance: tuple[RouteImportance, ...]
    direction_proposal: tuple[DirectionProposal, ...]
    objective_values: ObjectiveValues
    solver_status: SolverStatus
    solved_at: datetime
    seed: int
