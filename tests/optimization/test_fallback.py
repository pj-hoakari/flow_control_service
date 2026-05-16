"""Fallback path tests (module design v1 §7.5, math companion §11.6)."""

from __future__ import annotations

from datetime import datetime, timezone

from flow_control.models import (
    ArcStagnation,
    DirectionConstraint,
    DirectionProposal,
    Graph,
    ObjectiveValues,
    OptimizationResult,
    PhaseStatus,
    ProposedDirection,
    SolverStatus,
)
from flow_control.optimization import optimize

from tests.conftest import (
    make_commodity,
    make_detour_result,
    make_edge,
    make_forecast_result,
    make_node,
    make_observations,
)


def test_no_boundary_returns_error(base_time, baseline_config):
    """境界ノード無し → ERROR、空 proposal。"""
    nodes = (
        make_node("n1"),  # is_boundary=False
        make_node("n2"),
        make_node("n3"),
    )
    edges = (
        make_edge("e1", "n1", "n2"),
        make_edge("e2", "n2", "n3"),
    )
    graph = Graph(nodes=nodes, edges=edges)
    obs = make_observations(observed_at=base_time)
    forecast = make_forecast_result()
    r = optimize(
        graph=graph, observations=obs, forecast_result=forecast,
        detour_result=make_detour_result(), previous_result=None,
        config=baseline_config, seed=1, server_time=base_time,
    )
    assert r.optimization_result.solver_status is SolverStatus.ERROR
    assert r.optimization_result.direction_proposal == ()
    assert r.optimization_result.route_importance == ()
    assert r.constraint_report.boundary_reachability_satisfied is False
    assert r.constraint_report.fallback_to_previous is False


def _infeasible_graph() -> Graph:
    """無効化された端点ノード経由のみのグラフ → 有効アーク 0 で求解不能扱い。"""
    nodes = (
        make_node("n1", is_boundary=True),
        make_node("n2", enabled=False),
        make_node("n3", is_boundary=True),
    )
    edges = (
        make_edge("e1", "n1", "n2"),
        make_edge("e2", "n2", "n3"),
    )
    return Graph(nodes=nodes, edges=edges)


def test_infeasible_no_previous_returns_empty_proposal(base_time, baseline_config):
    """有効アーク 0 (実質 infeasible) かつ previous_result なし → 空 proposal。"""
    graph = _infeasible_graph()
    obs = make_observations(observed_at=base_time)
    forecast = make_forecast_result()
    r = optimize(
        graph=graph, observations=obs, forecast_result=forecast,
        detour_result=make_detour_result(), previous_result=None,
        config=baseline_config, seed=1, server_time=base_time,
    )
    assert r.optimization_result.direction_proposal == ()
    assert r.optimization_result.route_importance == ()


def _infeasible_by_demand_graph() -> Graph:
    """全エッジ LEGAL_FIXED_A_TO_B で、n1 が受け取れない構成 → ローカル可達違反で INFEASIBLE。"""
    nodes = (
        make_node("n1", is_boundary=True),
        make_node("n2"),
        make_node("n3", is_boundary=True),
    )
    edges = (
        # n1 → n2 のみ、n2 → n3 のみ。n1 への incoming が無い。
        make_edge("e1", "n1", "n2", direction_constraint=DirectionConstraint.LEGAL_FIXED_A_TO_B),
        make_edge("e2", "n2", "n3", direction_constraint=DirectionConstraint.LEGAL_FIXED_A_TO_B),
    )
    return Graph(nodes=nodes, edges=edges)


def test_phase1_infeasible_copies_previous_proposal(base_time, baseline_config):
    """Phase 1 infeasible + previous_result 提供 → previous の direction_proposal を採用。"""
    graph = _infeasible_by_demand_graph()
    obs = make_observations(
        observed_at=base_time,
        arc_stagnations=(ArcStagnation("e1", 1.0), ArcStagnation("e2", 1.0)),
    )
    forecast = make_forecast_result(
        commodities=(make_commodity("n1", "n3", 1.0),),
        arc_flow_sensitivity={"e1": 1.0, "e2": 1.0},
        arc_baseline_stagnation={"e1": 1.0, "e2": 1.0},
    )
    previous = OptimizationResult(
        route_importance=(),
        direction_proposal=(
            DirectionProposal(edge_id="e1", proposed_direction=ProposedDirection.A_TO_B),
            DirectionProposal(edge_id="e2", proposed_direction=ProposedDirection.A_TO_B),
        ),
        objective_values=ObjectiveValues(tau_star=0.0, throughput=0.0),
        solver_status=SolverStatus.OPTIMAL,
        solved_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        seed=0,
    )
    r = optimize(
        graph=graph, observations=obs, forecast_result=forecast,
        detour_result=make_detour_result(), previous_result=previous,
        config=baseline_config, seed=1, server_time=base_time,
    )
    assert r.optimization_result.solver_status is SolverStatus.INFEASIBLE
    assert r.optimization_result.direction_proposal == previous.direction_proposal
    assert r.constraint_report.fallback_to_previous is True
    assert r.solver_stats.phase1_status is PhaseStatus.INFEASIBLE
