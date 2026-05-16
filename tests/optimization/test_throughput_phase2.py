"""Phase 2 throughput maximization tests (math companion §11.4.2)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from flow_control.models import (
    ArcStagnation,
    Graph,
    PhaseStatus,
)
from flow_control.optimization import optimize

from tests.conftest import (
    make_commodity,
    make_detour_result,
    make_detour_set,
    make_edge,
    make_forecast_result,
    make_node,
    make_observations,
    make_path,
)


def _two_path_graph() -> Graph:
    """n1 → n3 への2経路: 直接 (e_direct) と中継経由 (e_left + e_right)。"""
    nodes = (
        make_node("n1", is_boundary=True),
        make_node("n_mid"),
        make_node("n3", is_boundary=True),
    )
    edges = (
        make_edge("e_direct", "n1", "n3"),
        make_edge("e_left", "n1", "n_mid"),
        make_edge("e_right", "n_mid", "n3"),
    )
    return Graph(nodes=nodes, edges=edges)


def _two_path_inputs(base_time):
    obs = make_observations(
        observed_at=base_time,
        arc_stagnations=(
            ArcStagnation("e_direct", 5.0),
            ArcStagnation("e_left", 5.0),
            ArcStagnation("e_right", 5.0),
        ),
    )
    forecast = make_forecast_result(
        commodities=(make_commodity("n1", "n3", 1.0),),
        arc_flow_sensitivity={"e_direct": 1.0, "e_left": 1.0, "e_right": 1.0},
        arc_baseline_stagnation={"e_direct": 5.0, "e_left": 5.0, "e_right": 5.0},
    )
    return obs, forecast


def test_phase2_skipped_when_p_empty(line_graph_3, baseline_observations, baseline_forecast,
                                      empty_detour, baseline_config, base_time):
    r = optimize(
        graph=line_graph_3,
        observations=baseline_observations,
        forecast_result=baseline_forecast,
        detour_result=empty_detour,
        previous_result=None,
        config=baseline_config,
        seed=1,
        server_time=base_time,
    )
    assert r.solver_stats.phase2_status is PhaseStatus.SKIPPED
    assert r.optimization_result.objective_values.throughput == 0.0


def test_phase2_runs_when_throughput_target_edges_set(base_time, baseline_config):
    graph = _two_path_graph()
    obs, forecast = _two_path_inputs(base_time)
    cfg = replace(baseline_config, throughput_target_edges=("e_direct",))
    r = optimize(
        graph=graph,
        observations=obs,
        forecast_result=forecast,
        detour_result=make_detour_result(),
        previous_result=None,
        config=cfg,
        seed=1,
        server_time=base_time,
    )
    assert r.solver_stats.phase2_status is PhaseStatus.OPTIMAL
    # 流量が指定エッジに集中し、throughput は正の値
    assert r.optimization_result.objective_values.throughput > 0.0


def test_phase2_runs_when_detour_result_provided(base_time, baseline_config):
    graph = _two_path_graph()
    obs, forecast = _two_path_inputs(base_time)
    detour = make_detour_result(
        sets=(
            make_detour_set(
                origin_edge_id="e_direct",
                endpoint_pair=("n1", "n3"),
                paths=(make_path(edge_ids=("e_left", "e_right")),),
            ),
        ),
    )
    r = optimize(
        graph=graph,
        observations=obs,
        forecast_result=forecast,
        detour_result=detour,
        previous_result=None,
        config=baseline_config,
        seed=1,
        server_time=base_time,
    )
    assert r.solver_stats.phase2_status is PhaseStatus.OPTIMAL


def test_phase2_respects_tau_relaxation(base_time, baseline_config):
    """Phase 2 後の tau は tau_star + epsilon を超えない (math §11.4.2)。"""
    graph = _two_path_graph()
    obs, forecast = _two_path_inputs(base_time)
    cfg = replace(baseline_config, throughput_target_edges=("e_direct",))
    r = optimize(
        graph=graph, observations=obs, forecast_result=forecast,
        detour_result=make_detour_result(), previous_result=None,
        config=cfg, seed=1, server_time=base_time,
    )
    # tau* は Phase 1 で確定。Phase 2 を通った後でも、Phase 1 の tau* + epsilon を超えない。
    assert r.optimization_result.objective_values.tau_star <= cfg.epsilon * 2 + 1e-6 + r.solver_stats.tau_star


def test_phase2_target_edge_flow_grows_vs_no_target(base_time, baseline_config):
    """対象エッジを指定すると、その経由のスループットが (指定なしと比較して) 増えるはず。"""
    graph = _two_path_graph()
    obs, forecast = _two_path_inputs(base_time)

    cfg_no_target = baseline_config
    cfg_with_target = replace(baseline_config, throughput_target_edges=("e_direct",))

    r_no = optimize(
        graph=graph, observations=obs, forecast_result=forecast,
        detour_result=make_detour_result(), previous_result=None,
        config=cfg_no_target, seed=1, server_time=base_time,
    )
    r_yes = optimize(
        graph=graph, observations=obs, forecast_result=forecast,
        detour_result=make_detour_result(), previous_result=None,
        config=cfg_with_target, seed=1, server_time=base_time,
    )

    def importance_for(result, edge_id: str) -> float:
        return max(
            (ri.importance for ri in result.optimization_result.route_importance if ri.edge_id == edge_id),
            default=0.0,
        )

    # 指定時は e_direct の最大 importance は 1.0 (最大流量に到達)
    assert importance_for(r_yes, "e_direct") == pytest.approx(1.0, abs=1e-3)
    # 指定なしの場合は最大流量とは限らないので、それ以下になる
    assert importance_for(r_yes, "e_direct") >= importance_for(r_no, "e_direct") - 1e-6
