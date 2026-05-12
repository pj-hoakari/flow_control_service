"""Integration-style detect() scenarios (module design v1 §12.1)."""

from __future__ import annotations

from datetime import timedelta

from flow_control.detection import detect
from flow_control.models import (
    ArcHistoryStat,
    ArcStagnation,
    TriggerSource,
    VerdictHint,
)

from tests.conftest import linear_window, make_history, make_observations


def test_cold_start_returns_no_trigger(
    base_time, basic_graph, baseline_config, long_term_tenant, empty_reference, empty_state
):
    result = detect(
        graph=basic_graph,
        observations=make_observations(observed_at=base_time),
        history_digest=make_history(),
        previous_state=empty_state,
        events=(),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    assert result.verdict_hint is VerdictHint.NO_TRIGGER
    assert result.triggered_edges == ()
    assert result.evidences == ()


def test_surge_and_high_stagnation_fire_together(
    base_time, basic_graph, baseline_config, long_term_tenant, empty_reference, empty_state
):
    # e1 で急増、e2 で高停滞両方継続
    window = linear_window(
        "e1",
        start=base_time - timedelta(minutes=10),
        samples=11,
        start_value=0.0,
        slope_per_min=10.0,
    )
    hist = make_history(
        stats=(
            ArcHistoryStat("e2", p90_stagnation=20.0, baseline_stagnation=10.0),
        ),
        window_series=(window,),
    )
    # 「両方継続」を成立させるため、watch_state を先に作る
    from dataclasses import replace
    from flow_control.models import ArcWatchState

    state = replace(
        empty_state,
        arc_watch_states={
            "e2": ArcWatchState(
                edge_id="e2",
                percentile_satisfied=True,
                delta_satisfied=True,
                started_at=base_time - timedelta(minutes=baseline_config.high_stagnation_duration_min + 1),
            ),
        },
    )
    obs = make_observations(
        observed_at=base_time,
        arc_stagnations=(ArcStagnation("e2", 50.0),),
    )

    result = detect(
        graph=basic_graph,
        observations=obs,
        history_digest=hist,
        previous_state=state,
        events=(),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    assert result.verdict_hint is VerdictHint.TRIGGERED
    assert set(result.triggered_edges) == {"e1", "e2"}
    sources = {ev.source for ev in result.evidences}
    assert TriggerSource.SURGE in sources
    assert TriggerSource.HIGH_STAGNATION in sources


def test_deterministic_for_same_input(
    base_time, basic_graph, baseline_config, long_term_tenant, empty_reference, empty_state
):
    obs = make_observations(
        observed_at=base_time,
        arc_stagnations=(ArcStagnation("e1", 50.0),),
    )
    hist = make_history(
        stats=(ArcHistoryStat("e1", 20.0, 10.0),),
    )
    args = dict(
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
    r1 = detect(**args)
    r2 = detect(**args)
    assert r1 == r2
