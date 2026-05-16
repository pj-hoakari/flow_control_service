"""Determinism tests for optimize() (math companion §11)."""

from __future__ import annotations

import pytest

from flow_control.optimization import optimize


def test_same_input_same_result_strict(line_graph_3, baseline_observations, baseline_forecast,
                                          empty_detour, baseline_config, base_time):
    r1 = optimize(
        graph=line_graph_3,
        observations=baseline_observations,
        forecast_result=baseline_forecast,
        detour_result=empty_detour,
        previous_result=None,
        config=baseline_config,
        seed=7,
        server_time=base_time,
    )
    r2 = optimize(
        graph=line_graph_3,
        observations=baseline_observations,
        forecast_result=baseline_forecast,
        detour_result=empty_detour,
        previous_result=None,
        config=baseline_config,
        seed=7,
        server_time=base_time,
    )
    # OptimizeResult.solver_stats は経過時間 (ms) が揺れるので除いた比較を行う
    assert r1.optimization_result == r2.optimization_result
    assert r1.constraint_report == r2.constraint_report
    assert r1.solver_stats.phase1_status == r2.solver_stats.phase1_status
    assert r1.solver_stats.phase2_status == r2.solver_stats.phase2_status
    assert r1.solver_stats.tau_star == pytest.approx(r2.solver_stats.tau_star, abs=1e-9)
    assert r1.solver_stats.throughput == pytest.approx(r2.solver_stats.throughput, abs=1e-9)


def test_different_seed_same_objective(line_graph_3, baseline_observations, baseline_forecast,
                                         empty_detour, baseline_config, base_time):
    """Phase 1 の最適値 (tau*) は決定的なので seed が変わっても等しい。"""
    r1 = optimize(
        graph=line_graph_3,
        observations=baseline_observations,
        forecast_result=baseline_forecast,
        detour_result=empty_detour,
        previous_result=None,
        config=baseline_config,
        seed=1,
        server_time=base_time,
    )
    r2 = optimize(
        graph=line_graph_3,
        observations=baseline_observations,
        forecast_result=baseline_forecast,
        detour_result=empty_detour,
        previous_result=None,
        config=baseline_config,
        seed=99,
        server_time=base_time,
    )
    assert r1.solver_stats.tau_star == pytest.approx(r2.solver_stats.tau_star, abs=1e-6)
