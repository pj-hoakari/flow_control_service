"""Public `optimize` entry point for the Optimization module (module design v1 §7)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..models import (
    ConstraintReport,
    DetourResult,
    ForecastResult,
    Graph,
    Observations,
    OptimizationResult,
    PhaseStatus,
    ResolvedConfig,
    SolverStats,
    SolverStatus,
)
from .arc_index import build_arc_index
from .fallback import (
    fallback_no_boundary,
    fallback_phase1_infeasible,
    fallback_phase2_failed,
)
from .model_builder import (
    add_phase2_constraints_and_objective,
    build_phase1_model,
    collect_p_arc_ids,
)
from .result_builder import (
    build_constraint_report,
    build_direction_proposal,
    build_objective_values,
    build_route_importance,
)
from .solver import SolveOutcome, solve_phase1, solve_phase2


MIN_PHASE2_SEC = 5.0


@dataclass(frozen=True)
class OptimizeResult:
    """`optimize()` returns this — bag of the OptimizationResult + diagnostics."""

    optimization_result: OptimizationResult
    solver_stats: SolverStats
    constraint_report: ConstraintReport


def optimize(
    graph: Graph,
    observations: Observations,
    forecast_result: ForecastResult,
    detour_result: DetourResult,
    previous_result: OptimizationResult | None,
    config: ResolvedConfig,
    seed: int,
    server_time: datetime,
) -> OptimizeResult:
    """Run the Optimization step.

    純粋関数: 外部 I/O なし。`seed` を明示的に受け取りソルバー乱数を固定する。
    Open モード前提 (`graph` に boundary ノード必須)。Closed モードはサイレントに
    切り替えず `SolverStatus.ERROR` を返す。
    """
    arc_index = build_arc_index(graph)

    # Open モード前提チェック
    if not arc_index.entry_nodes:
        fb = fallback_no_boundary(server_time, seed)
        return OptimizeResult(
            optimization_result=fb.optimization_result,
            solver_stats=fb.solver_stats,
            constraint_report=fb.constraint_report,
        )

    # 有効アークが 0 の場合は解くものがない
    if not arc_index.arcs:
        fb = fallback_no_boundary(server_time, seed)
        return OptimizeResult(
            optimization_result=fb.optimization_result,
            solver_stats=fb.solver_stats,
            constraint_report=fb.constraint_report,
        )

    # Phase 1
    built = build_phase1_model(graph, observations, forecast_result, config, arc_index)
    phase1 = solve_phase1(built, config, seed)

    if phase1.status in (PhaseStatus.INFEASIBLE, PhaseStatus.ERROR):
        fb = fallback_phase1_infeasible(previous_result, server_time, seed, phase1)
        return OptimizeResult(
            optimization_result=fb.optimization_result,
            solver_stats=fb.solver_stats,
            constraint_report=fb.constraint_report,
        )

    tau_star = phase1.objective_value if phase1.objective_value is not None else 0.0

    # Phase 2 対象アーク集合 P
    p_edge_ids = tuple(
        set(config.throughput_target_edges) | detour_result.all_path_edge_ids()
    )
    p_arc_ids = collect_p_arc_ids(arc_index, p_edge_ids)

    if not p_arc_ids:
        phase2 = SolveOutcome(status=PhaseStatus.SKIPPED, elapsed_ms=0, objective_value=0.0)
    else:
        add_phase2_constraints_and_objective(built, p_arc_ids, tau_star, config)
        remaining = max(
            MIN_PHASE2_SEC,
            config.milp_time_limit_sec - phase1.elapsed_ms / 1000.0,
        )
        phase2 = solve_phase2(built, config, seed, remaining)

    if phase2.status in (PhaseStatus.TIMEOUT, PhaseStatus.INFEASIBLE, PhaseStatus.ERROR):
        # Phase 1 解で確定 (math §11.6)
        fb = fallback_phase2_failed(built, phase1, phase2, arc_index, config, server_time, seed)
        return OptimizeResult(
            optimization_result=fb.optimization_result,
            solver_stats=fb.solver_stats,
            constraint_report=fb.constraint_report,
        )

    # 通常成功パス (Phase 2 OPTIMAL/FEASIBLE/SKIPPED いずれも Phase 1 の解空間内)
    route_importance = build_route_importance(built, config)
    direction_proposal = build_direction_proposal(built)
    objective = build_objective_values(phase1, phase2)
    constraint_report = build_constraint_report(
        built, phase1, arc_index, fallback_to_previous=False
    )
    solver_stats = SolverStats(
        solver_name="highs",
        phase1_status=phase1.status,
        phase2_status=phase2.status,
        phase1_ms=phase1.elapsed_ms,
        phase2_ms=phase2.elapsed_ms,
        tau_star=objective.tau_star,
        throughput=objective.throughput,
    )
    optimization_result = OptimizationResult(
        route_importance=route_importance,
        direction_proposal=direction_proposal,
        objective_values=objective,
        solver_status=SolverStatus.OPTIMAL,
        solved_at=server_time,
        seed=seed,
    )
    return OptimizeResult(
        optimization_result=optimization_result,
        solver_stats=solver_stats,
        constraint_report=constraint_report,
    )
