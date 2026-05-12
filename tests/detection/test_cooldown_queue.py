"""Cooldown and queue handling (module design v1 §4.3 / math companion v1 §9.4)."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from flow_control.detection import detect
from flow_control.models import (
    ArcStagnation,
    Event,
    EventKind,
    VerdictHint,
)

from tests.conftest import make_history, make_observations


def _high_stag_obs(base_time, edge_id="e1", value=50.0):
    return make_observations(
        observed_at=base_time,
        arc_stagnations=(ArcStagnation(edge_id=edge_id, stagnation=value),),
    )


def _high_stag_hist(edge_id="e1"):
    from flow_control.models import ArcHistoryStat

    return make_history(
        stats=(ArcHistoryStat(edge_id=edge_id, p90_stagnation=20.0, baseline_stagnation=10.0),),
    )


def test_queued_during_cooldown(
    base_time, basic_graph, baseline_config, long_term_tenant, empty_reference, empty_state
):
    cooldown_until = base_time + timedelta(minutes=baseline_config.cooldown_duration_min)
    state = replace(empty_state, cooldown_until=cooldown_until)

    # 両方の高停滞条件が継続済みの状態を作る
    state = replace(
        state,
        arc_watch_states={
            "e1": __import__(
                "flow_control.models", fromlist=["ArcWatchState"]
            ).ArcWatchState(
                edge_id="e1",
                percentile_satisfied=True,
                delta_satisfied=True,
                started_at=base_time - timedelta(minutes=baseline_config.high_stagnation_duration_min + 1),
            )
        },
    )

    result = detect(
        graph=basic_graph,
        observations=_high_stag_obs(base_time),
        history_digest=_high_stag_hist(),
        previous_state=state,
        events=(),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    assert result.verdict_hint is VerdictHint.QUEUED
    assert len(result.new_state.trigger_queue) == 1
    assert result.new_state.trigger_queue[0].origin_edge_id == "e1"


def test_queue_score_exceeded_triggers(
    base_time, basic_graph, baseline_config, long_term_tenant, empty_reference, empty_state
):
    cooldown_until = base_time + timedelta(minutes=baseline_config.cooldown_duration_min)
    # 既にキューに溜まったスコアを使う: queue_score_threshold = 10
    from flow_control.models import QueuedTrigger, QueuedTriggerKind

    pre_queued = QueuedTrigger(
        kind=QueuedTriggerKind.HIGH_STAGNATION,
        first_fired_at=base_time - timedelta(minutes=1),
        last_fired_at=base_time - timedelta(minutes=1),
        accumulated_score=10.0,
        snapshot_ref="prior",
        origin_edge_id="e1",
    )
    state = replace(empty_state, cooldown_until=cooldown_until, trigger_queue=(pre_queued,))

    # 「両方継続済み」の watch_state を入れて発火可能にする
    from flow_control.models import ArcWatchState

    state = replace(
        state,
        arc_watch_states={
            "e1": ArcWatchState(
                edge_id="e1",
                percentile_satisfied=True,
                delta_satisfied=True,
                started_at=base_time - timedelta(minutes=baseline_config.high_stagnation_duration_min + 1),
            )
        },
    )

    result = detect(
        graph=basic_graph,
        observations=_high_stag_obs(base_time),
        history_digest=_high_stag_hist(),
        previous_state=state,
        events=(),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    assert result.verdict_hint is VerdictHint.TRIGGERED
    assert result.new_state.trigger_queue == ()


def test_queue_diversity_exceeded_triggers(
    base_time, baseline_config, long_term_tenant, empty_reference, empty_state
):
    # 3 つの edge をもつグラフを構築
    from flow_control.models import ArcHistoryStat, ArcStagnation, ArcWatchState, Graph
    from tests.conftest import make_edge, make_node

    graph = Graph(
        nodes=(make_node("n1"), make_node("n2"), make_node("n3"), make_node("n4")),
        edges=(
            make_edge("e1", "n1", "n2"),
            make_edge("e2", "n2", "n3"),
            make_edge("e3", "n3", "n4"),
        ),
    )

    cooldown_until = base_time + timedelta(minutes=baseline_config.cooldown_duration_min)
    started_at = base_time - timedelta(minutes=baseline_config.high_stagnation_duration_min + 1)
    state = replace(
        empty_state,
        cooldown_until=cooldown_until,
        arc_watch_states={
            "e1": ArcWatchState("e1", True, True, started_at),
            "e2": ArcWatchState("e2", True, True, started_at),
            "e3": ArcWatchState("e3", True, True, started_at),
        },
    )

    obs = make_observations(
        observed_at=base_time,
        arc_stagnations=(
            ArcStagnation("e1", 50.0),
            ArcStagnation("e2", 50.0),
            ArcStagnation("e3", 50.0),
        ),
    )
    hist = make_history(
        stats=(
            ArcHistoryStat("e1", 20.0, 10.0),
            ArcHistoryStat("e2", 20.0, 10.0),
            ArcHistoryStat("e3", 20.0, 10.0),
        ),
    )

    # queue_diversity_threshold = 2 なので 3 異なる edge_id 起点で diverse 超過
    result = detect(
        graph=graph,
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
    assert set(result.triggered_edges) == {"e1", "e2", "e3"}


def test_skipped_cooldown_when_no_normal_triggers(
    base_time, basic_graph, baseline_config, long_term_tenant, empty_reference, empty_state
):
    cooldown_until = base_time + timedelta(minutes=baseline_config.cooldown_duration_min)
    state = replace(empty_state, cooldown_until=cooldown_until)

    result = detect(
        graph=basic_graph,
        observations=make_observations(observed_at=base_time),
        history_digest=make_history(),
        previous_state=state,
        events=(),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    assert result.verdict_hint is VerdictHint.SKIPPED_COOLDOWN


def test_danger_overrides_cooldown(
    base_time, basic_graph, baseline_config, long_term_tenant, empty_reference, empty_state
):
    cooldown_until = base_time + timedelta(minutes=baseline_config.cooldown_duration_min)
    state = replace(empty_state, cooldown_until=cooldown_until)

    result = detect(
        graph=basic_graph,
        observations=make_observations(observed_at=base_time),
        history_digest=make_history(),
        previous_state=state,
        events=(Event(kind=EventKind.DANGER_FLAG_UP, target_id="e1", occurred_at=base_time),),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    assert result.verdict_hint is VerdictHint.TRIGGERED
    assert "e1" in result.triggered_edges
