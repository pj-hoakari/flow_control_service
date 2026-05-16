"""Convert MILP solution into OptimizationResult (math companion §11.5)."""

from __future__ import annotations

from ..models import (
    ConstraintReport,
    DirectionProposal,
    FlowDirection,
    ImportanceDirection,
    ObjectiveValues,
    PhaseStatus,
    ProposedDirection,
    ResolvedConfig,
    RouteImportance,
)
from .arc_index import ArcIndex
from .model_builder import BuiltModel
from .solver import SolveOutcome


_INT_THRESHOLD = 0.5


def build_route_importance(
    built: BuiltModel,
    config: ResolvedConfig,
) -> tuple[RouteImportance, ...]:
    """w_a = f_a* / (max f_a'* + ε₀)。x_a*=0 のときは NONE / 0.0。"""
    arc_index = built.arc_index
    f_values = {arc.arc_id: float(built.f_total.solution.sel(arc=arc.arc_id).item())
                for arc in arc_index.arcs}
    x_values = {arc.arc_id: float(built.x.solution.sel(arc=arc.arc_id).item())
                for arc in arc_index.arcs}
    max_flow = max(f_values.values(), default=0.0)
    denom = max_flow + config.epsilon_0

    results: list[RouteImportance] = []
    for edge_id, (a2b, b2a) in arc_index.by_edge.items():
        for arc in (a2b, b2a):
            x_val = x_values.get(arc.arc_id, 0.0)
            f_val = f_values.get(arc.arc_id, 0.0)
            if x_val < _INT_THRESHOLD:
                direction = ImportanceDirection.NONE
                importance = 0.0
            else:
                direction = (
                    ImportanceDirection.A_TO_B
                    if arc.flow_direction is FlowDirection.A_TO_B
                    else ImportanceDirection.B_TO_A
                )
                importance = max(0.0, f_val) / denom
            results.append(
                RouteImportance(
                    edge_id=edge_id,
                    direction=direction,
                    importance=importance,
                )
            )
    return tuple(results)


def build_direction_proposal(
    built: BuiltModel,
) -> tuple[DirectionProposal, ...]:
    """(x_A2B, x_B2A) を丸めて方向提案に変換。"""
    arc_index = built.arc_index
    x_values = {arc.arc_id: float(built.x.solution.sel(arc=arc.arc_id).item())
                for arc in arc_index.arcs}

    results: list[DirectionProposal] = []
    for edge_id, (a2b, b2a) in arc_index.by_edge.items():
        x_ab = x_values[a2b.arc_id] >= _INT_THRESHOLD
        x_ba = x_values[b2a.arc_id] >= _INT_THRESHOLD
        if x_ab and x_ba:
            proposed = ProposedDirection.BIDIRECTIONAL
        elif x_ab:
            proposed = ProposedDirection.A_TO_B
        elif x_ba:
            proposed = ProposedDirection.B_TO_A
        else:
            proposed = ProposedDirection.BLOCKED
        results.append(
            DirectionProposal(edge_id=edge_id, proposed_direction=proposed, confidence=1.0)
        )
    return tuple(results)


def build_objective_values(
    phase1: SolveOutcome,
    phase2: SolveOutcome,
) -> ObjectiveValues:
    tau = phase1.objective_value if phase1.objective_value is not None else 0.0
    throughput = phase2.objective_value if phase2.objective_value is not None else 0.0
    return ObjectiveValues(tau_star=tau, throughput=throughput)


def build_constraint_report(
    built: BuiltModel,
    phase1: SolveOutcome,
    arc_index: ArcIndex,
    *,
    fallback_to_previous: bool,
) -> ConstraintReport:
    success = phase1.status in (PhaseStatus.OPTIMAL, PhaseStatus.FEASIBLE)
    violations: list[str] = []
    if success:
        x_values = {arc.arc_id: float(built.x.solution.sel(arc=arc.arc_id).item())
                    for arc in arc_index.arcs}
        for arc in arc_index.arcs:
            if arc.beta == 1:
                want = 1 if arc.alpha == 1 else 0
                got = 1 if x_values[arc.arc_id] >= _INT_THRESHOLD else 0
                if got != want:
                    violations.append(arc.arc_id)
    return ConstraintReport(
        local_reachability_satisfied=success,
        boundary_reachability_satisfied=success,  # Open モード前提、制約に組み込まれている
        legal_fixed_violations=tuple(violations),
        fallback_to_previous=fallback_to_previous,
    )
