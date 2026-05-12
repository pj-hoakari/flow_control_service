"""Surge trigger (math companion v1 §9.1)."""

from __future__ import annotations

from datetime import timedelta

from flow_control.detection import detect
from flow_control.models import TriggerSource, VerdictHint

from tests.conftest import linear_window, make_history, make_observations


def test_steady_flow_does_not_fire(
    base_time, basic_graph, baseline_config, long_term_tenant, empty_reference, empty_state
):
    window = linear_window(
        "e1",
        start=base_time - timedelta(minutes=29),
        samples=15,
        start_value=100.0,
        slope_per_min=0.0,
        step_minutes=2.0,
    )
    hist = make_history(window_series=(window,))
    obs = make_observations(observed_at=base_time)

    result = detect(
        graph=basic_graph,
        observations=obs,
        history_digest=hist,
        previous_state=empty_state,
        events=(),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    assert result.verdict_hint is VerdictHint.NO_TRIGGER


def test_surge_fires_when_slope_exceeds_threshold(
    base_time, basic_graph, baseline_config, long_term_tenant, empty_reference, empty_state
):
    # 平均流量 ~50, 傾き 10/分 → 約 20%/分 > 閾値 10
    window = linear_window(
        "e1",
        start=base_time - timedelta(minutes=10),
        samples=11,
        start_value=0.0,
        slope_per_min=10.0,
        step_minutes=1.0,
    )
    hist = make_history(window_series=(window,))
    obs = make_observations(observed_at=base_time)

    result = detect(
        graph=basic_graph,
        observations=obs,
        history_digest=hist,
        previous_state=empty_state,
        events=(),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    assert result.verdict_hint is VerdictHint.TRIGGERED
    assert result.triggered_edges == ("e1",)
    assert any(ev.source is TriggerSource.SURGE for ev in result.evidences)


def test_too_few_samples_skipped(
    base_time, basic_graph, baseline_config, long_term_tenant, empty_reference, empty_state
):
    window = linear_window(
        "e1",
        start=base_time - timedelta(minutes=1),
        samples=1,
        start_value=10.0,
        slope_per_min=100.0,
        step_minutes=1.0,
    )
    hist = make_history(window_series=(window,))
    obs = make_observations(observed_at=base_time)

    result = detect(
        graph=basic_graph,
        observations=obs,
        history_digest=hist,
        previous_state=empty_state,
        events=(),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    assert result.verdict_hint is VerdictHint.NO_TRIGGER


def test_zero_mean_avoids_zero_division(
    base_time, basic_graph, baseline_config, long_term_tenant, empty_reference, empty_state
):
    window = linear_window(
        "e1",
        start=base_time - timedelta(minutes=10),
        samples=10,
        start_value=0.0,
        slope_per_min=0.0,
        step_minutes=1.0,
    )
    hist = make_history(window_series=(window,))
    obs = make_observations(observed_at=base_time)

    result = detect(
        graph=basic_graph,
        observations=obs,
        history_digest=hist,
        previous_state=empty_state,
        events=(),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    assert result.verdict_hint is VerdictHint.NO_TRIGGER
