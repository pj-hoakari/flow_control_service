"""Fallback paths for the Optimization Step (module design v1 §7.5, math companion §11.6)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..models import (
    ConstraintReport,
    ObjectiveValues,
    OptimizationResult,
    PhaseStatus,
    ResolvedConfig,
    SolverStats,
    SolverStatus,
)
from .arc_index import ArcIndex
from .model_builder import BuiltModel
from .result_builder import build_route_importance, build_direction_proposal
from .solver import SolveOutcome


@dataclass(frozen=True)
class FallbackOutcome:
    optimization_result: OptimizationResult
    solver_stats: SolverStats
    constraint_report: ConstraintReport


def fallback_no_boundary(server_time: datetime, seed: int) -> FallbackOutcome:
    """Open モード前提だが境界ノードが存在しない場合。提案を返さず ERROR を表面化する。"""
    optimization_result = OptimizationResult(
        route_importance=(),
        direction_proposal=(),
        objective_values=ObjectiveValues(tau_star=0.0, throughput=0.0),
        solver_status=SolverStatus.ERROR,
        solved_at=server_time,
        seed=seed,
    )
    solver_stats = SolverStats(
        solver_name="highs",
        phase1_status=PhaseStatus.SKIPPED,
        phase2_status=PhaseStatus.SKIPPED,
        phase1_ms=0,
        phase2_ms=0,
        tau_star=0.0,
        throughput=0.0,
    )
    constraint_report = ConstraintReport(
        local_reachability_satisfied=False,
        boundary_reachability_satisfied=False,
        legal_fixed_violations=(),
        fallback_to_previous=False,
    )
    return FallbackOutcome(optimization_result, solver_stats, constraint_report)


def fallback_phase1_infeasible(
    previous_result: OptimizationResult | None,
    server_time: datetime,
    seed: int,
    phase1: SolveOutcome,
) -> FallbackOutcome:
    """MILP Phase 1 INFEASIBLE: 方向提案を出さず previous_result.direction_proposal をコピー。

    (module design §7.5)
    """
    proposal = previous_result.direction_proposal if previous_result is not None else ()
    optimization_result = OptimizationResult(
        route_importance=(),
        direction_proposal=proposal,
        objective_values=ObjectiveValues(tau_star=0.0, throughput=0.0),
        solver_status=SolverStatus.INFEASIBLE,
        solved_at=server_time,
        seed=seed,
    )
    solver_stats = SolverStats(
        solver_name="highs",
        phase1_status=phase1.status,
        phase2_status=PhaseStatus.SKIPPED,
        phase1_ms=phase1.elapsed_ms,
        phase2_ms=0,
        tau_star=0.0,
        throughput=0.0,
    )
    constraint_report = ConstraintReport(
        local_reachability_satisfied=False,
        boundary_reachability_satisfied=False,
        legal_fixed_violations=(),
        fallback_to_previous=True,
    )
    return FallbackOutcome(optimization_result, solver_stats, constraint_report)


def fallback_phase2_failed(
    built: BuiltModel,
    phase1: SolveOutcome,
    phase2: SolveOutcome,
    arc_index: ArcIndex,
    config: ResolvedConfig,
    server_time: datetime,
    seed: int,
) -> FallbackOutcome:
    """MILP Phase 2 TIMEOUT / INFEASIBLE: Phase 1 解で重要度・方向を出す (math §11.6)。"""
    route_importance = build_route_importance(built, config)
    direction_proposal = build_direction_proposal(built)
    tau_star = phase1.objective_value if phase1.objective_value is not None else 0.0
    optimization_result = OptimizationResult(
        route_importance=route_importance,
        direction_proposal=direction_proposal,
        objective_values=ObjectiveValues(tau_star=tau_star, throughput=0.0),
        solver_status=SolverStatus.FEASIBLE,  # Phase 1 は OK
        solved_at=server_time,
        seed=seed,
    )
    solver_stats = SolverStats(
        solver_name="highs",
        phase1_status=phase1.status,
        phase2_status=phase2.status,
        phase1_ms=phase1.elapsed_ms,
        phase2_ms=phase2.elapsed_ms,
        tau_star=tau_star,
        throughput=0.0,
    )
    constraint_report = ConstraintReport(
        local_reachability_satisfied=True,
        boundary_reachability_satisfied=True,
        legal_fixed_violations=(),
        fallback_to_previous=False,
    )
    return FallbackOutcome(optimization_result, solver_stats, constraint_report)
