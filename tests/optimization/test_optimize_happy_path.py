"""Happy-path scenarios for optimize() on a 3-node line graph (math companion §11)."""

from __future__ import annotations

import pytest

from flow_control.models import PhaseStatus, SolverStatus
from flow_control.optimization import optimize


def _call(line_graph_3, baseline_observations, baseline_forecast, empty_detour, baseline_config, base_time):
    return optimize(
        graph=line_graph_3,
        observations=baseline_observations,
        forecast_result=baseline_forecast,
        detour_result=empty_detour,
        previous_result=None,
        config=baseline_config,
        seed=42,
        server_time=base_time,
    )


def test_phase1_optimal_status(line_graph_3, baseline_observations, baseline_forecast,
                                empty_detour, baseline_config, base_time):
    r = _call(line_graph_3, baseline_observations, baseline_forecast, empty_detour, baseline_config, base_time)
    assert r.solver_stats.phase1_status is PhaseStatus.OPTIMAL
    assert r.optimization_result.solver_status is SolverStatus.OPTIMAL


def test_tau_star_is_nonnegative(line_graph_3, baseline_observations, baseline_forecast,
                                  empty_detour, baseline_config, base_time):
    r = _call(line_graph_3, baseline_observations, baseline_forecast, empty_detour, baseline_config, base_time)
    assert r.optimization_result.objective_values.tau_star >= 0.0


def test_route_importance_two_rows_per_edge(line_graph_3, baseline_observations, baseline_forecast,
                                              empty_detour, baseline_config, base_time):
    r = _call(line_graph_3, baseline_observations, baseline_forecast, empty_detour, baseline_config, base_time)
    # 2 edges × 2 directions = 4 rows
    assert len(r.optimization_result.route_importance) == 4
    edge_ids = {ri.edge_id for ri in r.optimization_result.route_importance}
    assert edge_ids == {"e1", "e2"}


def test_max_importance_normalized_to_one(line_graph_3, baseline_observations, baseline_forecast,
                                            empty_detour, baseline_config, base_time):
    """math §11.5: w_a = f_a / (max f_a + ε₀) — 流量が正なら最大は 1.0 に近づく。"""
    r = _call(line_graph_3, baseline_observations, baseline_forecast, empty_detour, baseline_config, base_time)
    max_w = max(ri.importance for ri in r.optimization_result.route_importance)
    assert max_w == pytest.approx(1.0, abs=1e-3)


def test_tau_star_reduces_observed_stagnation(line_graph_3, baseline_observations,
                                                baseline_forecast, empty_detour, baseline_config, base_time):
    """η・demand により観測停滞 s_obs=10 が緩和されるはずなので τ* < 1.0。"""
    r = _call(line_graph_3, baseline_observations, baseline_forecast, empty_detour, baseline_config, base_time)
    # tau * (s_bar + eps) >= s_obs - eta*f
    # s_obs=10, eta=5, s_bar=10, f >= 1 (demand) → tau >= (10-5*f)/(10+eps)
    # 最小は f=1 で tau=5/10=0.5
    assert r.optimization_result.objective_values.tau_star == pytest.approx(0.5, abs=1e-2)


def test_phase2_skipped_when_no_target(line_graph_3, baseline_observations, baseline_forecast,
                                         empty_detour, baseline_config, base_time):
    r = _call(line_graph_3, baseline_observations, baseline_forecast, empty_detour, baseline_config, base_time)
    assert r.solver_stats.phase2_status is PhaseStatus.SKIPPED
    assert r.optimization_result.objective_values.throughput == 0.0


def test_solved_at_and_seed_propagated(line_graph_3, baseline_observations, baseline_forecast,
                                         empty_detour, baseline_config, base_time):
    r = _call(line_graph_3, baseline_observations, baseline_forecast, empty_detour, baseline_config, base_time)
    assert r.optimization_result.solved_at == base_time
    assert r.optimization_result.seed == 42
